@echo off
REM ─────────────────────────────────────────────────────────────
REM AI-Native Self-Healing DevOps Platform — Demo Launcher (Windows)
REM ─────────────────────────────────────────────────────────────

echo.
echo ============================================================
echo   AI-Native Self-Healing DevOps Platform
echo ============================================================
echo.

REM Load .env if it exists
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1%"=="#" set %%A=%%B
    )
)

if "%ANTHROPIC_API_KEY%"=="" (
    echo ERROR: ANTHROPIC_API_KEY is not set.
    echo Copy .env.example to .env and fill in your key.
    pause
    exit /b 1
)
echo [OK] ANTHROPIC_API_KEY is set

echo.
echo Installing dependencies...
pip install -q -r requirements.txt
echo [OK] Dependencies ready

echo.
echo Killing any existing processes on ports 5000-5002...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000 " 2^>nul') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5001 " 2^>nul') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5002 " 2^>nul') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 /nobreak >nul

echo.
echo Starting services...
start "Webhook Receiver :5000" /min python webhook_receiver.py
timeout /t 1 /nobreak >nul
start "AI Agent :5001" /min python ai_agent.py
timeout /t 1 /nobreak >nul
start "Integrations :5002" /min python integrations.py
timeout /t 2 /nobreak >nul

echo.
echo ============================================================
echo   ALL SERVICES RUNNING
echo ============================================================
echo.
echo   1. Open dashboard:   http://localhost:5000/
echo   2. Trigger failure:  python demo_trigger.py
echo   3. List scenarios:   python demo_trigger.py list
echo   4. All scenarios:    python demo_trigger.py all
echo.
echo Services are running in background windows.
echo Close those windows or use Ctrl+C to stop them.
echo.
pause
