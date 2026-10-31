@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请安装 Python 3.8+ 并勾选 Add Python to PATH
    pause
    exit /b 1
)

echo.
echo   iptv 维护：体检现有线路 - 换掉失效 - 补源 - 推送
echo   约 2 分钟。测速期间不要看视频或下载。
echo.

python tools\pipeline.py %*
set RC=%errorlevel%

echo.
if %RC%==0 (
    echo 完成。播放器里刷新订阅即可。
) else (
    echo 未完成，退出码 %RC%。详细日志见 output\logs\
)
pause
exit /b %RC%
