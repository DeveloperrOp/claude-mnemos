@echo off
rem Manual start for the source/Python daemon (Smart-App-Control workaround).
rem Double-click to (re)start the daemon on http://127.0.0.1:5757.
cd /d "D:\code\claude-mnemos"
".venv\Scripts\python.exe" -m claude_mnemos daemon start
timeout /t 3 >nul
