@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.8+ 并勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo ================================================
echo  直播源测速（本机网络实测，约 4 分钟）
echo  测速期间请不要看视频/下载，否则结果偏低
echo ================================================
echo.

python speedtest.py %*
set RC=%errorlevel%

echo.
if %RC%==0 (
    echo 完成，结果在 output 目录。
) else (
    echo 运行结束但未产出结果（退出码 %RC%），请查看上面的输出。
)
pause
