#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开盘啦数据爬虫 - 批量抓取版（并行）
独立运行：token 校验/刷新 + 交易日获取 + 并行抓取
反爬：随机延时 + 并发控制 + 失败重试
输出与原 crawler_copy.py 完全一致
"""
import os
os.environ['PYTHONWARNINGS'] = 'ignore'

import requests
import json
import time
import re
import sys
import random
import subprocess
import pandas as pd
import akshare as ak
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── 路径 ──────────────────────────────────────
# scripts_new/..  → 项目根目录 (开盘啦_数据解析/)
ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = ROOT / ".env"
# mitm 脚本位置
SCRIPTS = ROOT / "scripts"
CAPTURES = ROOT / "captures"
DATA_DIR = ROOT / "data"

# ── 认证参数（从 .env 加载） ───────────────────
DEVICE_ID = "80ca7d1b-2a24-3cd0-a915-99b61f6f88aa"
VERSION = "5.23.0.4"
API_VERSION = "w44"
PHONE_OS_NEW = "1"
USER_ID = ""
TOKEN = ""


def load_env():
    global USER_ID, TOKEN, DEVICE_ID
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().strip().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                key = k.strip()
                val = v.strip()
                if key == "KPL_USER_ID":
                    USER_ID = val
                elif key == "KPL_TOKEN":
                    TOKEN = val
                elif key == "KPL_DEVICE_ID":
                    DEVICE_ID = val


def save_env(key, value):
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


# ── API 常量 ───────────────────────────────────
API_URL = "https://apphis.longhuvip.com/w1/api/index.php"
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; ALN-AL00 Build/W528JS)",
    "Host": "apphis.longhuvip.com",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
}


# ── Token 相关 ─────────────────────────────────
API_HQ = "https://apphwshhq.longhuvip.com/w1/api/index.php"  # 实时行情端点（用于验证 token）


def validate_token():
    """用实时行情端点验证 token 是否过期（与原版 daily_grab_new.py 一致）"""
    params = {
        "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID,
        "VerSion": VERSION, "apiv": API_VERSION,
        "UserID": USER_ID, "Token": TOKEN,
        "a": "GetInfo", "c": "Index", "View": "1",
    }
    body = "&".join(f"{k}={v}" for k, v in params.items())
    # 验证用 HEADERS_HQ（不带 Host，与原版一致）
    headers_hq = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; ALN-AL00 Build/W528JS)",
        "Connection": "Keep-Alive",
    }
    try:
        r = requests.post(API_HQ, data=body, headers=headers_hq, timeout=10)
        resp = r.json()
        ec = str(resp.get("errcode", ""))
        if ec == "0":
            return True
        errmsg = resp.get("errmsg", "").lower()
        if any(kw in errmsg for kw in ["token", "expired", "invalid", "未登录", "过期"]):
            return False
        return ec == "0"
    except Exception:
        return False


def extract_token_from_captures():
    for f in sorted(CAPTURES.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            body = data.get("request_body", "")
            if "Token=" not in body:
                continue
            token = uid = None
            for part in body.split("&"):
                if part.startswith("Token="):
                    token = part.split("=", 1)[1]
                elif part.startswith("UserID="):
                    uid = part.split("=", 1)[1]
            if token and uid:
                return uid, token
        except Exception:
            continue
    return None, None


def refresh_token():
    print("\n=== Token 过期 ===")
    mitm_script = SCRIPTS / "mitm_capture.py"
    if mitm_script.exists():
        subprocess.Popen([sys.executable, str(mitm_script)])
        print("mitmproxy 已启动")
    else:
        print(f"找不到 {mitm_script}，请手动启动 mitmproxy 抓包")

    # 自动轮询捕获目录，不需要手动输入
    uid, token = None, None
    while True:
        uid, token = extract_token_from_captures()
        if token:
            break
        print("⏳ 等待新捕获...（在模拟器中打开开盘啦并登录）")
        time.sleep(5)

    if not token:
        print("未能获取新 Token，退出")
        sys.exit(1)

    save_env("KPL_TOKEN", token)
    if uid:
        save_env("KPL_USER_ID", uid)
    TOKEN = token
    USER_ID = uid or USER_ID
    print(f"✅ Token 已更新: {token[:8]}...\n")
    return USER_ID, TOKEN


# ── 交易日 ─────────────────────────────────────
def get_trading_days(start_date=None, end_date=None):
    df = ak.tool_trade_date_hist_sina()
    all_days = sorted(df["trade_date"].tolist())
    all_days = [v.strftime('%Y-%m-%d') for v in all_days
                if v.strftime('%Y-%m-%d') <= datetime.now().strftime('%Y-%m-%d')]
    today = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        return [all_days[-1]]
    if not end_date:
        end_date = today
    return [d for d in all_days if start_date <= d <= end_date]


# ── 响应解析 ───────────────────────────────────
def _parse_response(resp_text):
    decoded = resp_text.encode('utf-8').decode('raw_unicode_escape')
    cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', decoded)
    return json.loads(cleaned)


# ── 请求参数构建 ───────────────────────────────
def _build_params(**kwargs):
    """构建 form-urlencoded body 字符串（与原代码一致的尾部 &）"""
    return "&".join(f"{k}={v}" for k, v in kwargs.items()) + "&"


# ── 防爬参数 ───────────────────────────────────
_RETRY_MAX = 3
_DELAY_MIN = 0.05
_DELAY_MAX = 0.15


def do_request(params, label=""):
    body = _build_params(**params)
    last_err = None
    for attempt in range(1, _RETRY_MAX + 1):
        try:
            delay = random.uniform(_DELAY_MIN, _DELAY_MAX)
            time.sleep(delay)
            resp = requests.post(API_URL, data=body, headers=HEADERS, timeout=15)
            return _parse_response(resp.text)
        except Exception as e:
            last_err = e
            print(f"  [⚠ {label}] 第{attempt}/{_RETRY_MAX}次失败: {e}", flush=True)
            time.sleep(1.5)
    print(f"  [✗ {label}] 重试{_RETRY_MAX}次仍失败: {last_err}", flush=True)
    return None


# ── 单板块并发抓取 ────────────────────────────
def fetch_plate_data(parent_code, date):
    """并发获取一个板块的 4 组关联数据"""
    res_qj = do_request({
        "a": "GetPlate_Info_QJ", "c": "ZhiShuRanking",
        "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID,
        "VerSion": VERSION, "Date": date, "apiv": API_VERSION,
        "PlateID": parent_code, "RStart": "0925", "REnd": "1500",
    }, f"PlateInfo_QJ[{parent_code}]")

    res_pk = do_request({
        "a": "GetPanKou", "c": "ZhiShuL2Data",
        "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID,
        "VerSion": VERSION, "Token": TOKEN, "apiv": API_VERSION,
        "StockID": parent_code, "UserID": USER_ID, "Day": date,
    }, f"PanKou[{parent_code}]")

    res_br = do_request({
        "a": "GetDayBaseFaceListZDEvnArt", "c": "ZhiShuKLine",
        "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID,
        "VerSion": VERSION, "Token": TOKEN, "apiv": API_VERSION,
        "StockID": parent_code, "UserID": USER_ID,
        'Index': '0', 'st': '10', 'Type': '0', 'IsBoom': '0',
    }, f"BoomReason[{parent_code}]")

    res_sp = do_request({
        "a": "SonPlate_Info", "c": "ZhiShuRanking",
        "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID,
        "VerSion": VERSION, "IsShow": "1", "Date": date,
        "apiv": API_VERSION, "PlateID": parent_code,
    }, f"SonPlate[{parent_code}]")

    return {
        'qj': res_qj,
        'pankou': res_pk,
        'boomreason': res_br,
        'sonplate': res_sp,
    }


def fetch_stock_list(plate_id, son_plate_id, date):
    res = do_request({
        "Order": "1", "TSZB": "0", "a": "ZhiShuStockList_W8", "st": "30",
        "c": "ZhiShuRanking", "PhoneOSNew": PHONE_OS_NEW, "old": "1",
        "DeviceID": DEVICE_ID, "VerSion": VERSION, "IsZZ": "0",
        "Token": TOKEN, "Index": "0", "Date": date,
        "apiv": API_VERSION, "Type": "6", "IsKZZType": "0",
        "UserID": USER_ID, "PlateID": son_plate_id,
        "TSZB_Type": "0", "filterType": "0",
    }, f"StockList[{son_plate_id}]")
    return res


# ── 单日期抓取（与原 crawler_copy.py 输出完全一致） ─

def crawl_date(date, max_workers=10):
    DATA_DIR.mkdir(exist_ok=True)
    start_time = time.time()

    js_real_ranking_info = {}
    js_plate_info_qj = {}
    js_pan_kou = {}
    js_boomreason = {'boomreason': []}
    js_son_plate_info = {}
    js_zhishu_stock_list = {}

    # ── 阶段1：串行分页 RealRankingInfo ──
    all_plate_ids = []
    page = 0
    while True:
        res_i = do_request({
            "Order": "1", "a": "RealRankingInfo", "st": "30", "c": "ZhiShuRanking",
            "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID,
            "VerSion": VERSION, "Index": f"{page * 30}",
            "Date": date, "apiv": API_VERSION, "Type": "1", "ZSType": "7",
        }, f"RealRankingInfo[{date}@{page}]")

        if res_i is None or len(res_i.get("list", [])) == 0:
            break

        # 去重停止（与原代码一致：转为字符串做 substring 匹配）
        if js_real_ranking_info and res_i["list"][0][0] in str(js_real_ranking_info.get("list", [[]])[0][0]):
            break

        # 合并排行数据
        if js_real_ranking_info:
            js_real_ranking_info['list'].extend(res_i['list'])
        else:
            js_real_ranking_info = {k: v for k, v in res_i.items()}

        # 收集 plate_id
        for item in res_i["list"]:
            pid = item[0]
            if pid not in all_plate_ids:
                all_plate_ids.append(pid)

        page += 1
        time.sleep(random.uniform(0.3, 0.6))

    if not all_plate_ids:
        print(f"  [{date}] 无板块数据，跳过")
        return

    print(f"  [{date}] 共 {len(all_plate_ids)} 个板块")

    # ── 阶段2+3：并行抓取板块数据 + 成分股 ──
    all_stock_items = []
    all_sub_plates = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有板块数据请求
        future_to_pid = {
            executor.submit(fetch_plate_data, pid, date): pid
            for pid in all_plate_ids
        }

        for future in as_completed(future_to_pid):
            pid = future_to_pid[future]
            try:
                data = future.result()
            except Exception as e:
                print(f"  [✗ {pid}] 板块数据异常: {e}", flush=True)
                continue

            # -- QJ --
            res_qj = data.get('qj')
            if res_qj and 'List' in res_qj:
                row = list(res_qj['List'])
                row.insert(0, pid)
                if js_plate_info_qj:
                    js_plate_info_qj['List'].append(row)
                else:
                    js_plate_info_qj = {k: v for k, v in res_qj.items()}
                    js_plate_info_qj["List"] = [row]

            # -- PanKou --
            res_pk = data.get('pankou')
            if res_pk and 'pankou' in res_pk:
                row = list(res_pk['pankou'])
                row.insert(0, res_pk.get('code', pid))
                res_pk.pop('code', None)
                if js_pan_kou:
                    js_pan_kou['pankou'].append(row)
                else:
                    js_pan_kou = {k: v for k, v in res_pk.items()}
                    js_pan_kou["pankou"] = [row]

            # -- BoomReason --
            res_br = data.get('boomreason')
            if res_br and 'List' in res_br:
                for item in res_br.get('List', []):
                    if item.get('Date') == date:
                        reason = str(item.get('BoomReason', '')).strip()
                        is_boom = item.get('IsBoom')
                        js_boomreason['boomreason'].append([pid, reason, is_boom])
                        break

            # -- SonPlate --
            res_sp = data.get('sonplate')
            if res_sp and 'List' in res_sp:
                if len(res_sp["List"]) == 0:
                    a, b = None, None
                    for item in js_real_ranking_info.get("list", []):
                        if item[0] == pid:
                            a, b = item[1:3]
                            break
                    all_sub_plates.append([pid, pid, a, b])
                else:
                    for item in res_sp["List"]:
                        row = list(item)
                        row.insert(0, pid)
                        all_sub_plates.append(row)
            else:
                # 请求失败也走回退，不漏数据
                a, b = None, None
                for item in js_real_ranking_info.get("list", []):
                    if item[0] == pid:
                        a, b = item[1:3]
                        break
                all_sub_plates.append([pid, pid, a, b])

    # 聚合子板块
    if all_sub_plates:
        js_son_plate_info = {'List': all_sub_plates}

    # ── 阶段3：并行抓取成分股 ──
    if all_sub_plates:
        with ThreadPoolExecutor(max_workers=max_workers) as executor2:
            stock_futures = {
                executor2.submit(fetch_stock_list, row[0], row[1], date): row
                for row in all_sub_plates
                if len(row) >= 2
            }
            for future in as_completed(stock_futures):
                pid_key = stock_futures[future][0]
                son_key = stock_futures[future][1]
                try:
                    res_st = future.result()
                    if res_st and 'list' in res_st:
                        for item in res_st["list"]:
                            row = list(item)
                            row.insert(0, pid_key)
                            row.insert(1, son_key)
                            all_stock_items.append(row)
                except Exception as e:
                    print(f"  [✗ StockList({son_key})] 异常: {e}", flush=True)

    if all_stock_items:
        js_zhishu_stock_list = {'list': all_stock_items}

    # ── 阶段 4：构建 DataFrame（与原代码完全一致） ──

    # 原代码 lst_col
    lst_col = ['父代码', '父板块', '强度', '涨幅', '涨速', '成交额', '主力净额', '主力买', '主力卖', '量比', '流通市值', 'x1', '300 万大单净额', '总市值', '第一季度机构增仓', '2026 年平均 PE', '2027 年平均 PE', 'x2', 'x3']
    df_real_ranking_info = pd.DataFrame(js_real_ranking_info.get("list", []), columns=lst_col)
    df_real_ranking_info = df_real_ranking_info[[v for v in df_real_ranking_info.columns if v.find('x') != 0]]
    # 金额类字段转换为亿为单位
    for col in ['成交额', '主力净额', '主力买', '主力卖', '流通市值', '300 万大单净额', '总市值']:
        if col in df_real_ranking_info.columns:
            df_real_ranking_info[col] = pd.to_numeric(df_real_ranking_info[col], errors='coerce') / 1e8

    lst_col = ['父代码', '排名', '强度', '成交额', '主力净额', '涨幅', '涨停数', '涨停封单', '大额封单']
    df_plate_info_qj = pd.DataFrame(js_plate_info_qj.get("List", []), columns=lst_col)
    df_plate_info_qj = df_plate_info_qj[['父代码', '排名', '涨停数', '涨停封单', '大额封单']]
    # 金额类字段转换为亿为单位
    for col in ['成交额', '主力净额', '涨停封单', '大额封单']:
        if col in df_plate_info_qj.columns:
            df_plate_info_qj[col] = pd.to_numeric(df_plate_info_qj[col], errors='coerce') / 1e8

    lst_col = ['父代码', '成交额', '换手率', '市盈率', '主力买', '主力卖', '主力净额', '上涨', '下跌', '平盘', '流通市值', '总市值']
    df_pan_kou = pd.DataFrame(js_pan_kou.get("pankou", []), columns=lst_col)
    df_pan_kou = df_pan_kou[['父代码', '换手率', '市盈率', '上涨', '下跌', '平盘']]
    # 金额类字段转换为亿为单位（虽然这些列最终被过滤，但保持一致性）
    for col in ['成交额', '主力买', '主力卖', '主力净额', '流通市值', '总市值']:
        if col in df_pan_kou.columns:
            df_pan_kou[col] = pd.to_numeric(df_pan_kou[col], errors='coerce') / 1e8

    lst_col = ['父代码', '爆发原因', '是否爆发']
    df_boomreason = pd.DataFrame(js_boomreason.get("boomreason", []), columns=lst_col)

    lst_col = ['父代码', '子代码', '子板块', '子板块强度']
    df_son_plate_info = pd.DataFrame(js_son_plate_info.get("List", []), columns=lst_col)

    lst_col = ['父代码', '子代码', '代码', '名称', 'x2', 'x3', '所属板块标签', '价格', '涨幅', '成交额', '实际换手率', '涨速', '实际流通', '主力买', '主力卖', '主力净额', 'x15', 'x16', 'x17', 'x18', '卖流占比', '净流占比', '区间涨幅', '量比', 'x23', '几天几板', 'x8', '换手率', 'x27', 'x28', '收盘封单', '最大封单', 'x31', 'x32', 'x33', '振幅', 'x35', 'x36', 'x37', '总市值', '流通市值',    'x40', '领涨次数', 'x42', '机构增仓 Q1', 'x44', 'x45', 'x46', 'x47', 'x48', 'x49','x50', '300 万以上大单净额', 'x52', 'x53', '市净率', 'x55', 'x56', 'x57', 'x58', '人气值', '人气排名变化', '市盈率动', '市盈率 TTM', 'PE 静']
    df_zhishu_stock_list = pd.DataFrame(js_zhishu_stock_list.get('list', []), columns=lst_col)
    df_zhishu_stock_list = df_zhishu_stock_list[[v for v in df_zhishu_stock_list.columns if v.find('x') != 0]]
    # 金额类字段转换为亿为单位
    for col in ['成交额', '主力买', '主力卖', '主力净额', '收盘封单', '最大封单', '总市值', '流通市值', '300 万以上大单净额']:
        if col in df_zhishu_stock_list.columns:
            df_zhishu_stock_list[col] = pd.to_numeric(df_zhishu_stock_list[col], errors='coerce') / 1e8

    # merge（与原代码完全一致）
    df_plate_info = df_real_ranking_info.merge(df_plate_info_qj, how='left', on='父代码')
    df_plate_info = df_plate_info.merge(df_pan_kou, how='left', on='父代码')
    df_plate_info = df_plate_info.merge(df_boomreason, how='left', on='父代码')

    # 写 CSV（与原代码完全一致：index=False，无 encoding 参数）
    df_plate_info.to_csv(f'{DATA_DIR}/main_plate_info_{date}.csv', index=False)
    df_son_plate_info.to_csv(f'{DATA_DIR}/sub_plate_info_{date}.csv', index=False)
    df_zhishu_stock_list.to_csv(f'{DATA_DIR}/stock_info_{date}.csv', index=False)

    elapsed = time.time() - start_time
    print(f"  [{date}] ✅ 抓取完成，耗时 {int(elapsed//60)}分{int(elapsed%60)}秒。")


# ── 主入口 ─────────────────────────────────────
def main(start_date=None, end_date=None, delay=None, workers=None):
    # 如果未传参，从命令行解析
    if start_date is None and end_date is None:
        args = sys.argv[1:]
        i = 0
        while i < len(args):
            if args[i] == "--start" and i + 1 < len(args):
                start_date = args[i + 1]; i += 2
            elif args[i] == "--end" and i + 1 < len(args):
                end_date = args[i + 1]; i += 2
            elif args[i] == "--delay" and i + 1 < len(args):
                delay = float(args[i + 1]); i += 2
            elif args[i] == "--workers" and i + 1 < len(args):
                workers = int(args[i + 1]); i += 2
            else:
                i += 1

    if delay is None:
        delay = float(os.environ.get("CRAWL_DELAY", "0.05"))
    if workers is None:
        workers = int(os.environ.get("CRAWL_WORKERS", "10"))

    global _DELAY_MIN, _DELAY_MAX
    _DELAY_MIN = delay
    _DELAY_MAX = delay * 3

    if start_date or end_date:
        dates = get_trading_days(start_date, end_date)
    else:
        dates = get_trading_days()

    if not dates:
        print("无交易日，退出")
        return

    print(f"抓取区间: {dates[0]} ~ {dates[-1]} 共 {len(dates)} 天\n")

    load_env()

    if not validate_token():
        refresh_token()

    for date in dates:
        print(f"\n{'=' * 60}")
        print(f"📅 抓取日期: {date}")
        crawl_date(date, max_workers=workers)

    print(f"\n{'=' * 60}")
    print("✅ 全部抓取完成!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main(start_date="2026-05-01", end_date="2026-05-15")

