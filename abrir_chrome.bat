@echo off
title Chrome Debug 9222

echo Iniciando Chrome em modo Remote Debugging...

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
--remote-debugging-port=9222 ^
--user-data-dir="C:\ChromeDebug"

exit