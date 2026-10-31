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
echo ============================================================
echo   体检当前订阅：只测现有线路，不建池、不合并、不上传
echo   约 1 分钟。测速期间不要看视频或下载。
echo ============================================================
echo.

python check_speed.py --pull %*
set RC=%errorlevel%

echo.
echo ------------------------------------------------------------
if %RC%==0 (
    echo 完成。把这两个文件拷回维护机：
    echo   measured.txt  -^>  E:\workbuddy\iptv\output\measured.txt
    echo   report.tsv    -^>  仅供查看，不用拷
    echo 然后在维护机上跑: python tools\pipeline.py --apply output\measured.txt
) else (
    echo 未产出结果，退出码 %RC%。检查是否断网或走了代理。
)
echo ------------------------------------------------------------
pause
exit /b %RC%
