@echo off
rem One-click installer for GRAPAI (Ductus). Installs for the current user only: no admin rights needed.
rem Everything goes to %LOCALAPPDATA%\GRAPAI. Run it again at any time to update or repair.
title GRAPAI installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1" %*
echo.
pause
