#!/bin/sh
# 直播源测速（Linux / macOS）
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[错误] 未找到 python3，请先安装 Python 3.8+"
    exit 1
fi

echo "================================================"
echo " 直播源测速（本机网络实测，约 4 分钟）"
echo " 测速期间请不要看视频/下载，否则结果偏低"
echo "================================================"
echo

exec "$PY" speedtest.py "$@"
