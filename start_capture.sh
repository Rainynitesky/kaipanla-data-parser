#!/bin/bash
# 开盘啦 App 终极抓包脚本 - 正确版本
# 用法：./start_capture.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MITM_SCRIPT="$SCRIPT_DIR/mitm_simple.py"
ADB="/Applications/MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"

# ⚠️ 关键：MuMu 模拟器访问 Mac 主机必须用 10.0.2.2，不能用 127.0.0.1
PROXY_HOST="10.0.2.2"
PROXY_PORT="8080"

echo "=========================================="
echo "  开盘啦 App 抓包工具"
echo "=========================================="
echo ""

# 检查脚本是否存在
if [ ! -f "$MITM_SCRIPT" ]; then
    echo "❌ 错误：mitm_simple.py 不存在：$MITM_SCRIPT"
    echo "   请先创建 scripts/mitm_simple.py"
    exit 1
fi

# 检查 ADB
if [ ! -f "$ADB" ]; then
    echo "❌ 错误：ADB 不存在：$ADB"
    exit 1
fi

# 1. 重启 ADB 服务器
echo "[1/5] 重启 ADB 服务器..."
$ADB kill-server 2>/dev/null || true
$ADB start-server 2>/dev/null
sleep 1

# 2. 连接 MuMu 模拟器
echo "[2/5] 连接 MuMu 模拟器..."
CONNECTED=""
for PORT in 5555 7555 16384 16416; do
    if $ADB connect 127.0.0.1:$PORT 2>/dev/null | grep -q "connected"; then
        CONNECTED="127.0.0.1:$PORT"
        echo "  ✅ 已连接：$CONNECTED"
        break
    fi
done

if [ -z "$CONNECTED" ]; then
    DEVICES=$($ADB devices 2>/dev/null | grep "127.0.0.1:" | awk '{print $1}' | head -1)
    if [ -n "$DEVICES" ]; then
        CONNECTED="$DEVICES"
        echo "  ✅ 使用已连接设备：$CONNECTED"
    else
        echo "❌ 错误：未找到 MuMu 模拟器，请先启动模拟器"
        exit 1
    fi
fi

DEVICE="$CONNECTED"

# 3. 清除旧代理
echo "[3/5] 清除旧代理配置..."
$ADB -s "$DEVICE" shell settings put global http_proxy ":0" 2>/dev/null || true
sleep 0.5

# 4. 启动 mitmproxy（后台运行）
echo "[4/5] 启动 mitmproxy (端口 $PROXY_PORT)..."
cd "$PROJECT_ROOT"

# 杀死旧的 mitmdump 进程
pkill -f "mitmdump.*mitm_simple" 2>/dev/null || true
sleep 1

# 后台启动 mitmdump
nohup mitmdump -s "$MITM_SCRIPT" --listen-port $PROXY_PORT > /tmp/mitm_capture.log 2>&1 &
MITM_PID=$!
echo $MITM_PID > /tmp/mitm_capture.pid

# 等待启动
sleep 2

# 检查是否成功启动
if ! ps -p $MITM_PID > /dev/null 2>&1; then
    echo "❌ 错误：mitmproxy 启动失败"
    cat /tmp/mitm_capture.log
    exit 1
fi

# 5. 配置代理（⚠️ 关键：用 10.0.2.2 不是 127.0.0.1）
echo "[5/5] 配置 MuMu 代理 → $PROXY_HOST:$PROXY_PORT..."
$ADB -s "$DEVICE" shell settings put global http_proxy "$PROXY_HOST:$PROXY_PORT"

# 验证
PROXY_SETTING=$($ADB -s "$DEVICE" shell settings get global http_proxy 2>/dev/null | tr -d '\r\n')
echo ""
echo "=========================================="
echo "  ✅ 抓包环境已就绪！"
echo "=========================================="
echo ""
echo "  mitmproxy PID: $MITM_PID"
echo "  代理地址：$PROXY_HOST:$PROXY_PORT  ⚠️ 不能用 127.0.0.1"
echo "  模拟器设备：$DEVICE"
echo "  数据保存：$PROJECT_ROOT/captures/"
echo ""
echo "  📱 现在请在 MuMu 模拟器中："
echo "     1. 打开 开盘啦 App"
echo "     2. 浏览页面产生流量"
echo ""
echo "  🛑 停止抓包："
echo "     ./stop_capture.sh"
echo ""
echo "  📊 查看实时日志："
echo "     tail -f /tmp/mitm_capture.log"
echo ""
echo "  📁 查看最新抓包："
echo "     ls -lht $PROJECT_ROOT/captures/*.json | head -10"
echo ""