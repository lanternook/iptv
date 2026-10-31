@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set MODE=%~1
if "%MODE%"=="" set MODE=full

echo.
echo ============================================================
echo   iptv 订阅刷新   模式: %MODE%
echo   1 合并   2 校验   3 推送
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto NOPY
if not exist "tools\token.txt" goto NOTOKEN
if not exist "output\tv_result.txt" goto NOTV

echo [底表] output\tv_result.txt
for %%F in ("output\tv_result.txt") do echo        修改时间 %%~tF
echo        底表越新，合并结果越准。过期就重新在电视上跑 handoff 包。
echo.

if /i "%MODE%"=="test" (
    echo [1/3] 本机测速  约 5 分钟，结果写 local_result.txt，不覆盖精选
    python tools\local_speedtest.py --from-subscribe --extra config\extra_hubei.txt --seconds 3 --out output\local_result.txt
    if errorlevel 1 goto FAILSPEED
    echo.
)

echo [2/3] 合并  底表 + 网关 + 黑名单 + 卫视低速率过滤(2.0Mbps)
python tools\merge_tv.py --drop-group 凤凰频道 --drop-group 广东频道 --move 广州综合=卫视频道
if errorlevel 1 goto FAILMERGE
echo.

if /i "%MODE%"=="dry" (
    echo [跳过推送] output\curated.txt 已生成，未上传
    goto END
)

echo [3/3] 推送 GitHub
python tools\push_file.py output\curated.txt --message "curated: 刷新"
if errorlevel 1 goto FAILPUSH

echo.
echo ============================================================
echo  完成。镜像有约 5 分钟缓存，之后可执行:
echo    python tools\verify_feed.py
echo  再在播放器里刷新订阅。
echo ============================================================
goto END

:NOPY
echo [错误] 未找到 python，请安装 Python 3.8+ 并勾选 Add Python to PATH
goto ENDPAUSE

:NOTOKEN
echo [错误] 缺少 tools\token.txt，请把 GitHub PAT 写入该文件
goto ENDPAUSE

:NOTV
echo [错误] 缺少 output\tv_result.txt
echo        请先在电视/盒子上运行 handoff 包测速，把结果拷到这里
goto ENDPAUSE

:FAILSPEED
echo [失败] 测速未产出结果，请查看上方输出
goto ENDPAUSE

:FAILMERGE
echo [失败] 合并出错，请查看上方输出
goto ENDPAUSE

:FAILPUSH
echo [失败] 推送出错，请检查网络代理与 token 权限
goto ENDPAUSE

:ENDPAUSE
echo.
pause
exit /b 1

:END
echo.
pause
exit /b 0
