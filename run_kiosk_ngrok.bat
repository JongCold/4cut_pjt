@echo off
chcp 65001 > nul
title [청년 4컷] AI 백엔드 엔진 & ngrok 터널 동시 기동 스크립트

echo ================================================================
echo    [서울청년센터 영등포 X 놀면뭐AI] 청년 4컷 키오스크 시스템
echo    FastAPI 백엔드(포트 8000) 및 ngrok 고정 HTTPS 터널 동시 기동
echo ================================================================
echo.

cd /d "%~dp0local-server"

:: 1. 기존에 실행 중인 uvicorn 프로세스 및 ngrok 정리 (중복 방지)
taskkill /f /im ngrok.exe >nul 2>&1

:: 2. ngrok 고정 도메인 터널 백그라운드 기동
echo [1/2] ngrok HTTPS 보안 터널을 생성하고 있습니다...
start "ngrok Tunnel" /min "%~dp0ngrok.exe" http 8000 --log=stdout

timeout /t 3 /nobreak > nul

echo.
echo ================================================================
echo   ✅ ngrok 터널 고정 도메인 활성화 완료!
echo   • 백엔드 공용 HTTPS: https://seducing-issue-overflow.ngrok-free.dev
echo   • 로컬 관리자 페이지: http://127.0.0.1:8000/
echo   • 태블릿 Vercel 접속: https://4cut-pjt.vercel.app/
echo ================================================================
echo.

:: 3. FastAPI 백엔드 엔진 기동 (포어그라운드 로그 표시)
echo [2/2] FastAPI AI 엔진을 기동합니다...
C:\Python313\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

pause
