@echo off
chcp 65001 > nul 2>&1

echo ================================================================
echo    4CUT STUDIO - Backend + ngrok Tunnel Launcher
echo    FastAPI(port 8000) + ngrok HTTPS fixed domain
echo ================================================================
echo.

REM --- Kill existing ngrok processes to prevent duplicates ---
taskkill /f /im ngrok.exe >nul 2>&1

REM --- Step 1: Start ngrok tunnel with fixed domain ---
echo [1/2] Starting ngrok HTTPS tunnel...
start "ngrok Tunnel" /min "%~dp0ngrok.exe" http 8000 --domain=seducing-issue-overflow.ngrok-free.dev --log=stdout

timeout /t 4 /nobreak > nul

echo.
echo ================================================================
echo   ngrok tunnel is ACTIVE!
echo   Backend HTTPS : https://seducing-issue-overflow.ngrok-free.dev
echo   Local Admin   : http://127.0.0.1:8000/
echo   Tablet Vercel : https://4cut-pjt.vercel.app/
echo ================================================================
echo.

REM --- Step 2: Start FastAPI backend (foreground with logs) ---
echo [2/2] Starting FastAPI AI Engine...
cd /d "%~dp0local-server"
C:\Python313\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

pause
