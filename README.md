# 开盘啦数据解析项目

## 项目目标

抓取开盘啦App(com.aiyu.kaipanla)的**267个板块行情数据**及**672个板块-个股关联数据**（477子板块+195无子板块主板块），保存为JSON。

---

## 1. 核心发现（已确认，勿重复验证）

### 1.1 267板块列表走Socket不走HTTP
- PlateTCConfig HTTP接口只返回58个行业板块
- 完整267板块（含概念板块）通过**TCP Socket + TLS + Protobuf**传输
- Socket服务器: `124.71.166.244:14000`, `1.94.128.64:14000`, `60.204.212.123:14000`
- IP获取接口: `getsockip.longhuvip.com/getIPList?UserID=...&Token=...` (HTTP, 已验证可用)
- 267板块ID→名称映射已保存至: `~/.hermes/skills/reverse-engineering/android-app-reverse/references/kaipanla-plates-267.json`

### 1.2 Socket协议栈
```
App → AES加密(protobuf数据) → TLS加密 → TCP → 服务器
```
- DEX中发现 `getSocketAESKey`/`getHttpAESKey` → Socket通信有AES加密层
- `libsockSign.so` 负责签名计算，AuthReq.signature字段需要此库生成

### 1.3 App加固
- `libzxprotect.so` 加固框架，导致：
  - Frida `Java.perform` 报 "Java is not defined" — **Java层hook完全不可用**
  - Frida Native hook（send/recv/SSL_write/BIO_write）全部0调用
  - classes.dex是壳，真正代码被加密
- **frida-dexdump运行时脱壳成功**：41/54个DEX已dump

### 1.4 App网络行为
- **不强制SSL pinning** — mitmproxy无需Frida bypass即可解密HTTPS
- **Socket连接绕过系统HTTP代理** — 不走CONNECT隧道，直连服务器
- iptables DNAT在MuMu模拟器上**不生效**
- **可行的Socket拦截方案**: mitmproxy劫持getIPList响应，把IP改为10.0.2.2:14000

---

## 2. 已尝试且失败的方案（勿重复尝试）

| 方案 | 结果 | 原因 |
|------|------|------|
| Frida Java.perform hook | ❌ | libzxprotect.so加固导致Java VM不可达 |
| Frida Native hook send/recv | ❌ | 加固替换libc函数指针 |
| Frida Native hook SSL_write/BIO_write | ❌ | App用内嵌BoringSSL |
| iptables DNAT重定向Socket | ❌ | MuMu模拟器QEMU用户模式网络不经过内核netfilter |
| Python直连Socket发AuthReq | ❌ | AES加密层+签名缺失，服务器关闭连接 |
| GetConceptJXBKw23 HTTP接口 | ❌ | 接口存在但返回空List |
| jadx反编译 | ❌ | classes.dex是壳无法静态分析 |

---

## 3. 已成功的方案

| 方案 | 结果 | 产出 |
|------|------|------|
| mitmproxy抓包HTTPS API | ✅ | captures/ 800+个JSON |
| frida-dexdump运行时脱壳 | ✅ | 41个DEX（已清理） |
| 从脱壳DEX提取Protobuf定义 | ✅ | proto/*.proto |
| getIPList劫持+TCP代理拦截Socket | ✅ | tcp_proxy_raw.py收到TLS ClientHello |
| HTTP API获取267板块数据 | ✅ | data/plates/ (267板块, 含盘口/爆发原因) |
| HTTP API获取子板块+个股数据 | ✅ | data/sub_plates/ (672板块, 含个股列表) |

---

## 4. API接口文档

### 4.1 域名
| 域名 | 用途 |
|------|------|
| apphwshhq.longhuvip.com | 行情数据(板块/指数/盘口) |
| applhb.longhuvip.com | 题材/概念/龙虎榜 |
| apphis.longhuvip.com | 历史数据(个股列表) ⚠️ ZhiShuStockList_W8必须用这个域名 |
| apparticle.longhuvip.com | 文章/资讯 |
| applog.longhuvip.com | 日志 |
| getsockip.longhuvip.com | Socket服务器IP列表 |

### 4.2 通用请求参数
```
PhoneOSNew=1&DeviceID={did}&VerSion=5.23.0.4&apiv=w44&UserID={uid}&Token={token}
```
- **⚠️ 必须使用Dalvik User-Agent！** 服务器校验UA，非Dalvik UA返回空数据
  ```
  User-Agent: Dalvik/2.1.0 (Linux; U; Android 12; ALN-AL00 Build/W528JS)
  Connection: Keep-Alive
  ```
- 认证信息从抓包获取，Token可能过期需重新抓包
- 非交易时间需传 `Date=交易日期`（如2026-05-08）

### 4.3 板块数据接口

#### GetPlate_Info_QJ (c=ZhiShuRanking)
- 参数: PlateID=801159, Date=2026-05-08
- **概念板块(267个)和行业板块(58个)字段映射不同！**

概念板块格式（267个，PlateID以8010-8018开头）:
```
List[0] = 涨跌家数差/强度排名 (如1)
List[1] = 强度 (如16304)
List[2] = 成交额(元) (如812032290529 → 8120亿)
List[3] = 主力净额(元) (如8437255508 → 84亿)
List[4] = 未知 (如1.98) ⚠️ 含义待确认
List[5] = 涨停数 (如24)
List[6] = 涨停封单(元) (如2123483126 → 21.23亿)
List[7] = 大单封单(元) (如1347672506 → 13.48亿)
```

**涨跌幅不在GetPlate_Info_QJ中！** 需从 `Index/GetInfo` → `BaceFaceList` 获取:
```
BaceFaceList = [[板块名称, 涨幅%, PlateID], ...]
例: ["机器人概念", "1.67", 801159]
```

行业板块格式（58个，PlateID以8019/803/880开头）:
```
List[0] = 强度 (如239, 或'--'表示无数据)
List[1] = 涨跌幅*100 (如-38 → -0.38%)
List[2] = 成交额(元)
List[3] = 主力净额(元)
List[4] = 量比 (如0.16)
List[5-7] = 通常为0
```

#### GetPanKou (c=ZhiShuL2Data, 参数用StockID不是PlateID!)
- 参数: StockID=801159, Date=2026-05-08
- ⚠️ 控制器是 **ZhiShuL2Data** 不是 ZhiShuRanking！之前用错控制器导致返回空
- 返回盘口数据（12字段数组）:
```
pankou[0]  = 成交额(元)
pankou[1]  = 换手率(%) (如3.994)
pankou[2]  = 未知(220.505)
pankou[3]  = 未知(615.74亿)
pankou[4]  = 未知(-531.37亿)
pankou[5]  = 主力净额(元)
pankou[6]  = 上涨家数 (如872)
pankou[7]  = 下跌家数 (如295)
pankou[8]  = 未知(18)
pankou[9]  = 未知(203298.83亿)
pankou[10] = 未知(258127.24亿)
pankou[11] = 强度 (16304.42)
```

#### GetBaseFaceListZDEvnArtNew (c=ZhiShuL2Data)
- 参数: StockID=801159
- ⚠️ 控制器是 **ZhiShuL2Data** 不是 ZhiShuRanking！
- 返回当日爆发原因

#### BKFenShiZhiBo (c=ConceptionPoint)
- 参数: PlateID=801159
- ⚠️ 控制器是 **ConceptionPoint** 不是 ZhiShuRanking！
- 返回分时直播事件（涨停股等）

#### SonPlate_Info (c=ZhiShuRanking)
- 参数: PlateID=801159
- 返回子板块列表: [[代码, 名称, 强度], ...]

#### ZhiShuStockList_W8 (c=ZhiShuRanking, 域名=apphis)
- 参数: PlateID=801821, Date=2026-05-08, Type=0~19
- **⚠️ 域名必须是 apphis.longhuvip.com，不能用apphwshhq！**
- **⚠️ 响应key是小写 `list` 不是大写 `List`！** 之前用大写取一直显示0
- **⚠️ Type参数是排序标签，每种Type返回9只个股（Top9），需遍历Type 0~19合并去重才是完整列表！**
- Type对应GetGPCPHBTS_Tag的排序标签（机构增仓TSZB=20、低PE=7、高股息=8等）
- 个股字段(63个) — 2026-05-10v4 用户确认:
```
[0]=代码, [1]=名称, [4]=所属板块标签,
[5]=价格, [6]=涨幅%, [7]=成交额(元),
[8]=实际换手率%, [9]=涨速, [10]=实际流通(元),
[11]=主力买(元), [12]=主力卖(元), [13]=主力净额(元),
[18]=卖流占比, [19]=净流占比, [20]=区间涨幅,
[21]=量比, [23]=几天几板, [25]=换手率%,
[28]=收盘封单(元), [29]=最大封单(元),
[33]=振幅, [37]=总市值(元), [38]=流通市值(元),
[40]=领涨次数, [42]=机构增仓Q1(元), [50]=300万以上大单净额(元),
[53]=市净率,
[58]=人气值, [59]=人气排名变化,
[60]=市盈率动, [61]=市盈率TTM, [62]=PE静
```
- 字段名来源: PaiHangBangOption/GetUserOptionB的Bind数组含字段名→arrayPosition映射

#### GetGPCPHBTS_Tag (c=ZhiShuRanking)
- 参数: PlateID=801821
- 返回标签配置（最正宗、机构增仓等排序选项）

#### GetDayBaseFaceListZDEvnArt (c=ZhiShuKLine)
- 参数: PlateID=801159
- 返回爆发原因历史列表

#### Theme/InfoBKR (c=Theme, 域名=applhb)
- 参数: ZSCode=801159
- 返回子概念列表

### 4.4 首页接口

#### Index/GetInfo (c=Index)
- 返回首页聚合数据，含BaceFaceList活跃板块（涨跌幅来源）

#### Index/NewGetList (c=Index, 域名=applhb)
- 返回Theme.List热门板块

---

## 5. Socket协议（Protobuf）

### 5.1 服务定义（从classes05.dex提取）
```protobuf
service HQ {
  rpc SubThemeList(Empty) returns (themeListResp);
  rpc SubPlateTypeQuotasList(PlateTypeQuotasListReq) returns (PlateTypeQuotasListResp);
  rpc SubAuth(AuthReq) returns (AuthResp);
}
```

### 5.2 消息定义

#### AuthReq
```
deviceId(1,string), platformId(2,int), versionName(3,string),
channelId(4,int), signature(5,string), userId(6,string),
token(7,string), connType(8,int), curTime(9,int)
```

#### themeListResp.Item（267板块列表）
```
id(1), name(2), desc(3), pinyin(4), isHot(5),
ztNum(6), ratio(7), sortType(8), conceptType(9),
codeSwitch(10), state(11)
```

#### PlateTypeQuotasListResp.Item（板块行情）
```
plateId(1), plateName(2), strength(3), incRate(4),
tur(5), mainNetAmount(6), volRatio(7), institutionIncrease(8),
circularCaptital(9), yearPE(10), nextYearPE(11)
```
- **volRatio=量比, institutionIncrease=机构增仓** — 这两个字段在HTTP API中找不到，只在Socket推送中

### 5.3 Proto文件
- `proto/kpl.proto` — 合并后的完整protobuf定义
- `proto/kpl_pb2.py` — 编译后的Python模块（需protobuf v6运行时）

---

## 6. 当前数据资产

| 路径 | 内容 |
|------|------|
| data/plates/plates_2026-05-08.json | **267个板块完整数据**(强度/成交额/主力/涨停封单/大单封单/换手率/上涨下跌/爆发原因/子板块) |
| data/plates/plates_2026-05-08_summary.csv | 267板块汇总CSV |
| data/sub_plates/sub_plates_2026-05-08.json | **672个板块-个股数据**(477子板块+195无子板块主板块, 含个股列表) |
| data/sub_plates/sub_plates_2026-05-08_summary.csv | 板块-个股汇总CSV |
| data/index/ | 首页/58板块历史数据 |
| captures/ | mitmproxy抓包原始数据 |

---

## 7. 环境配置

### MuMu模拟器
- ADB路径: `/Applications/MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb`
- ADB端口: **不稳定**，每次重启后需扫描
- 网关: 10.0.2.2 = Mac主机
- 默认root
- **极不稳定** — 频繁操作后容易崩溃，ADB断连

### Frida
- 版本: 17.9.1
- Server路径: /data/local/tmp/frida-server
- **必须用attach模式(-p PID)**，spawn模式(-f)会导致libzxprotect.so crash
- **必须adb forward tcp:27042**
- Java.perform不可用 / Native hook不可用

### mitmproxy
- 版本: 9.0.1
- 虚拟环境: `/Users/yixin/.openclaw/workspace/tcp_grabber/venv_tcp/`
- CA证书: `~/.mitmproxy/mitmproxy-ca.pem`
- **⚠️ protobuf版本冲突**: 修复: `pip install protobuf==4.25.9 typing-extensions==4.4.0`

### Python
- 系统Python: 3.9
- venv: `/Users/yixin/.openclaw/workspace/tcp_grabber/venv_tcp/` (含frida+mitmproxy)

---

## 8. 脚本清单

### 8.1 调度脚本（推荐）

| 脚本 | 用途 | 状态 |
|------|------|------|
| daily_grab.py | **统一调度脚本**：按天循环抓取 plates+sub_plates，自动检测 token 过期，断点续传 | ✅ 新增 |

### 8.2 核心抓取脚本

| 脚本 | 用途 | 状态 |
|------|------|------|
| scripts/grab_plates.py | 267 板块批量抓取 (含盘口/爆发原因) | ✅ 267/267 成功 |
| scripts/grab_sub_plates.py | 672 板块 - 个股批量抓取 (477 子板块 +195 主板块，含个股列表，Type 0~19 遍历合并去重) | 🔄 进行中 |
| scripts/fetch_index.py | 首页数据爬虫 | ✅ 可用 |

### 8.3 抓包/代理脚本（推荐）

**一键启动/停止（推荐）：**

| 脚本 | 用途 | 状态 |
|------|------|------|
| `scripts/start_capture.sh` | **一键启动抓包**：自动配置代理 (10.0.2.2:8080) + 启动 mitmproxy | ✅ 终极正确版 |
| `scripts/stop_capture.sh` | **一键停止抓包**：清理进程 + 关闭代理 | ✅ 终极正确版 |

**使用方法：**
```bash
# 启动抓包
cd /Users/yixin/agent_project/开盘啦_数据解析/scripts
./start_capture.sh

# 在 MuMu 模拟器中打开 开盘啦 App 并操作

# 停止抓包
./stop_capture.sh
```

**⚠️ 关键配置：**
- 代理地址必须是 `10.0.2.2:8080`（MuMu 网关 = Mac 主机）
- **不能用** `127.0.0.1:8080`（模拟器内 127.0.0.1 指向自己，会导致网络受限）

---

### 8.4 抓包/代理脚本（底层）

| 脚本 | 用途 | 状态 |
|------|------|------|
| scripts/mitm_simple.py | **简化版抓包脚本**：保存所有 HTTP/HTTPS 流量，无过滤 | ✅ 推荐 |
| scripts/mitm_capture.py | mitmproxy 抓包 (HTTPS API) | ✅ 可用 |
| scripts/mitm_intercept.py | mitmproxy 劫持 getIPList+ 抓包 | ✅ 可用 |
| scripts/tcp_proxy_raw.py | 纯 TCP 转发代理 | ✅ 已验证 |
| scripts/tcp_proxy_mitm.py | TLS 中间人代理 | ⚠️ 待测试 |

---

## 8.5 daily_grab.py 使用说明

### 前置配置

在 `.env` 文件中配置认证参数（已自动生成）：
```
KPL_USER_ID=7079210
KPL_TOKEN=你的 token 值
KPL_DEVICE_ID=你的设备 ID
```

### 基本用法

```bash
# 抓取今天的数据（推荐）
python3 daily_grab.py --date 2026-05-14

# 批量抓取日期范围（自动跳过周末）
python3 daily_grab.py --start-date 2026-05-01 --end-date 2026-05-14

# 强制重新抓取（覆盖已有数据）
python3 daily_grab.py --force --date 2026-05-08

# 只抓 plates 不抓 sub_plates
python3 daily_grab.py --skip-sub-plates --date 2026-05-14

# 自定义并发线程数和请求间隔
python3 daily_grab.py --workers 5 --delay 0.1 --date 2026-05-14
```

### 工作流程

```
daily_grab.py 按天循环:
├── 检查 token 是否过期 → 过期则暂停并提示手动更新
├── 检查该日期数据是否已存在 → 存在则跳过
├── 执行 grab_plates.py (267 板块)
│   └── 输出：data/plates/plates_{date}.json
└── 执行 grab_sub_plates.py (子板块 + 个股)
    └── 输出：data/sub_plates/sub_plates_{date}.json
```

### Token 过期处理

脚本会自动检测 token 是否过期。如果过期，会：
1. 打印错误信息
2. 暂停执行
3. 提示你手动更新 `.env` 文件中的 `KPL_TOKEN`
4. 询问是否继续（输入 y 继续，其他退出）

**如何获取新 token：**
1. 在 MuMu 模拟器中打开 App 并登录
2. 启动 mitmproxy 抓包
3. 从抓包数据中找到新的 Token 值
4. 更新 `.env` 文件
5. 重新运行 `python3 daily_grab.py`

### 断点续传

脚本会自动检查 `data/{plates,sub_plates}/plates_{date}.json` 是否存在：
- 已存在 → 自动跳过
- 使用 `--force` 参数可强制覆盖

### 日志输出

每天抓取完成后会生成独立日志文件：
```
logs/daily_grab_2026-05-14.log
```

日志包含：日期、token 状态、抓取结果、时间戳等。

---

## 9. 已踩过的坑（勿重复）

1. **Dalvik UA 必须** — 不用则 API 返回 errcode=0 但 List=[]
2. **概念板块 vs 行业板块字段映射不同** — GetPlate_Info_QJ 两种板块格式不同
3. **List[4] 不是涨跌幅** — 涨跌幅在 Index/GetInfo 的 BaceFaceList 中
4. **List[6] 是涨停封单不是主力流入** — List[7] 是大单封单不是主力流出
5. **GetPanKou 控制器是 ZhiShuL2Data 不是 ZhiShuRanking** — 参数用 StockID 不是 PlateID
6. **BKFenShiZhiBo 控制器是 ConceptionPoint** — 不是 ZhiShuRanking
7. **ZhiShuStockList_W8 域名是 apphis 不是 apphwshhq** — 用错域名返回 0
8. **ZhiShuStockList_W8 响应 key 是小写 list 不是 List** — 用大写取一直显示 0
9. **mitmproxy 需放行非 longhuvip 域名** — 否则 DNS 失败返回 502 阻断 App 网络
10. **非交易时间 Index/GetInfo 的 BaceFaceList 返回空** — 涨跌幅列暂为空
11. **ZhiShuStockList_W8 只返回 9 只** — 需遍历 Type 0~19 合并去重才是完整个股列表
12. **[5] 是价格不是涨幅** — 之前误以为是涨幅导致数据错乱
13. **[11] 是主力买不是流通市值** — 之前映射错误
14. **[28]=收盘封单 [29]=最大封单 [50]=300 万以上大单净额** — 从 PaiHangBangOption/GetUserOptionB 的 Bind 数组确认
15. **子板块个股数据 App 走 Socket 不走 HTTP** — App 进入子板块时不请求个股列表接口，数据通过 Socket 推送
16. **⚠️ MuMu 代理必须用 10.0.2.2:8080** — 127.0.0.1 在模拟器内指向自己，会导致 App 网络受限

---

## 10. 项目文件结构
```
开盘啦_数据解析/
├── README.md                    # 本文件（项目文档）
├── daily_grab.py                # 统一调度脚本（按天循环抓取，自动检测 token）
├── .env                         # 认证配置（KPL_TOKEN/KPL_USER_ID/KPL_DEVICE_ID）
├── scripts/                     # 所有脚本
│   ├── start_capture.sh         # **一键启动抓包**（推荐）
│   ├── stop_capture.sh          # **一键停止抓包**（推荐）
│   ├── mitm_simple.py           # 简化版抓包脚本（保存所有流量）
│   ├── mitm_intercept.py        # 劫持 getIPList+ 抓包
│   ├── mitm_capture.py          # mitmproxy 抓包 (HTTPS)
│   ├── grab_plates.py           # 267 板块批量抓取 (核心脚本)
│   ├── grab_sub_plates.py       # 672 板块 - 个股批量抓取 (含个股，Type 遍历)
│   ├── fetch_index.py           # 首页数据爬虫
│   ├── tcp_proxy_raw.py         # 纯 TCP 转发代理
│   └── tcp_proxy_mitm.py        # TLS 中间人代理
├── proto/                       # Protobuf 协议定义
│   ├── kpl.proto                # 合并后的 protobuf 定义
│   └── kpl_pb2.py               # 编译后的 Python 模块
├── data/                        # 输出数据
│   ├── plates/                  # 267 板块数据
│   │   ├── plates_{date}.json
│   │   └── plates_{date}_summary.csv
│   ├── sub_plates/              # 672 板块 - 个股数据
│   │   ├── sub_plates_{date}.json
│   │   └── sub_plates_{date}_summary.csv
│   └── index/                   # 首页/58板块数据
├── captures/                    # mitmproxy原始抓包
└── _remove/                     # 待删除(278MB)
```
