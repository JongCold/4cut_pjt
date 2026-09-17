@echo off
chcp 65001 > nul 2>&1
title 4CUT AI STUDIO - Tablet UX/UI & ngrok Launcher

echo =======================================================================
echo    ★ 인생4컷 AI 스튜디오 - 태블릿 전용 UX/UI & ngrok 런처 ★
echo    기기 최적화: Galaxy Tab S7+ (16:10 가로 모드 / 2560x1600)
echo    동작 엔진: FastAPI Backend (Port 8000) + ngrok 고정 HTTPS 도메인
echo =======================================================================
echo.

REM --- 기존 프로세스 정리 ---
taskkill /f /im ngrok.exe >nul 2>&1

REM --- 1단계: ngrok 고정 도메인 터널 실행 ---
echo [1/2] ngrok 보안 HTTPS 터널 가동 중...
start "ngrok Tunnel (Tablet Link)" /min "%~dp0ngrok.exe" http 8000 --domain=seducing-issue-overflow.ngrok-free.dev --log=stdout

timeout /t 3 /nobreak > nul

echo.
echo =======================================================================
echo   ✅ ngrok 보안 터널이 활성화되었습니다!
echo   -------------------------------------------------------------------
echo   * 백엔드 HTTPS API : https://seducing-issue-overflow.ngrok-free.dev
echo   * 로컬 관리자 패널 : http://127.0.0.1:8000/
echo   * 태블릿 Vercel 앱 : https://4cut-pjt.vercel.app/
echo =======================================================================
echo.

REM --- 2단계: FastAPI AI 엔진 실행 ---
echo [2/2] FastAPI AI 엔진 구동 시작 (스튜디오 보정/조선/픽셀/시간여행)...
set NGROK_PUBLIC_URL=https://seducing-issue-overflow.ngrok-free.dev
cd /d "%~dp0local-server"

python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

pause
