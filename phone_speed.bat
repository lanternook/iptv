@echo off
setlocal
cd /d "%~dp0"
set "ADB=E:/workbuddy/tmp/adb-tools/platform-tools/adb.exe"
if not exist "%ADB%" set "ADB=adb"
echo ============================================
echo   手机测速（目标机同网，通常是湖北移动）
echo ============================================
echo.
"%ADB%" devices
echo.
echo [1/4] 生成测速清单
python tools\find_gateway.py --phone
if errorlevel 1 goto :fail
echo.
echo [2/4] 推送脚本与清单
"%ADB%" push tools\phone_speed.sh /data/local/tmp/phone_speed.sh
"%ADB%" push output\phone_urls.txt /data/local/tmp/urls.txt
echo.
echo [3/4] 手机端串行测速（每条约 5 秒，请勿中途拔线）
"%ADB%" shell "sh /data/local/tmp/phone_speed.sh /data/local/tmp/urls.txt 3" > output\phone_result.txt
echo     结果行数：
find /c "|" output\phone_result.txt
echo.
echo [4/4] 回灌并重写网关池
python tools\find_gateway.py --ingest output\phone_result.txt
goto :done
:fail
echo 生成清单失败，先看 find_gateway.bat 的输出
:done
echo.
pause
