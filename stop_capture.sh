#!/bin/bash
# 开盘啦 App 停止抓包脚本 - 正确版本
# 用法：./stop_capture.sh

set -e

ADB="/Applications/MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"
PID_FILE="/tmp/mitm_capture.pid"
CAPTURES_DIR="/Users/yixin/agent_project/开盘啦_数据解析/captures"

echo "=========================================="
echo "  停止开盘啦 App 抓包"
echo "=========================================="
echo ""

# 1. 停止 mitmproxy
echo "[1/2] 停止 mitmproxy..."

if [ -f "$PID_FILE" ]; then
    MITM_PID=$(cat "$PID_FILE")
    if ps -p $MITM_PID > /dev/null 2>&1; then
        kill $MITM_PID 2>/dev/null || true
        echo "  ✅ mitmproxy 已停止 (PID: $MITM_PID)"
    else
        echo "  ⚠️  mitmproxy 未运行"
    fi
    rm -f "$PID_FILE"
else
    # 尝试查找并杀死
    MITM_PID=$(pgrep -f "mitmdump.*mitm_simple" | head -1)
    if [ -n "$MITM_PID" ]; then
        kill $MITM_PID 2>/dev/null || true
        echo "  ✅ mitmproxy 已停止 (PID: $MITM_PID)"
    else
        echo "  ⚠️  未找到运行中的 mitmproxy"
    fi
fi

# 2. 关闭 MuMu 代理
echo ""
echo "[2/2] 清除 MuMu 代理配置..."

DEVICES=$($ADB devices 2>/dev/null | grep "127.0.0.1:" | awk '{print $1}' | head -1)
if [ -n "$DEVICES" ]; then
    $ADB -s "$DEVICES" shell settings put global http_proxy ":0" 2>/dev/null || true
    echo "  ✅ 代理已关闭 (设备：$DEVICES)"
else
    echo "  ⚠️  未找到 MuMu 设备，跳过代理清理"
fi

echo ""
echo "=========================================="
echo "  ✅ 抓包已停止"
echo "=========================================="
echo ""
echo "  📁 抓包数据位置："
echo "     $CAPTURES_DIR"
echo ""
echo "  📊 最新抓包文件："
ls -lht "$CAPTURES_DIR"/*.json 2>/dev/null | head -5 || echo "     (无新文件)"
echo ""
echo "  📈 文件总数："
ls -1 "$CAPTURES_DIR"/*.json 2>/dev/null | wc -l | xargs -I {} echo "     {} 个 JSON 文件"
echo ""