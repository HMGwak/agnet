@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0codex-login.ps1"
exit /b %errorlevel%
