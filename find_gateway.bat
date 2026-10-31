@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   IPTV 找源（网关优先）
echo   流程：搜索 -> 提取 -> 验证 -> 写池
echo ============================================
echo.
python tools\find_gateway.py %*
if errorlevel 1 (
  echo.
  echo [提示] 没找到可用网关：先看上面哪一步没进度。
  echo   1) 搜索 0 命中 -^> 代理没开或 token 失效
  echo   2) 全部失效 -^> 换手机网络测：phone_speed.bat
)
echo.
echo 池文件：config\gateway_pool.txt
pause
