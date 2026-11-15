@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\OptimizeSkinFilterCache.ps1" -GameRoot "%~dp0." -Apply
if errorlevel 1 echo Cache optimization failed. Close the game and check the message above.
pause
