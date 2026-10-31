@echo off
rem refresh.bat 是历史入口名，功能与 update.bat 完全一致，这里直接转调
echo [提示] refresh.bat 已并入 update.bat，本次转调 update.bat
echo.
call "%~dp0update.bat" %*
exit /b %errorlevel%
