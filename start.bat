@echo off
REM ==============================================================================
REM YT-sub Studio — 1-Click Startup Script (Windows)
REM ==============================================================================
cd /d "%~dp0"

echo ==================================================
echo  Starting YT-sub Studio
echo ==================================================

REM 1. Check for .env file
if not exist "backend\.env" (
    echo [!] backend\.env not found.
    if exist "backend\.env.example" (
        echo [+] Creating backend\.env from backend\.env.example...
        copy "backend\.env.example" "backend\.env" >nul
        echo [!] Please edit backend\.env and add your GEMINI_API_KEY before running.
    )
)

REM 2. Check/Install Python Dependencies
echo [+] Checking Python backend dependencies...
python -m pip install -r backend\requirements.txt -q

REM 3. Check/Install Frontend Dependencies
echo [+] Checking Frontend dependencies...
if not exist "frontend\node_modules\" (
    echo [+] Installing node_modules in frontend...
    cd frontend && npm install && cd ..
)

REM 4. Start Backend in separate window
echo [+] Starting FastAPI backend on http://localhost:8000...
start "YT-sub Backend" cmd /k "cd backend && python -m uvicorn main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

REM 5. Start Frontend
echo [+] Starting Vite frontend on http://localhost:5173...
start "YT-sub Frontend" cmd /k "cd frontend && npm run dev"

timeout /t 2 /nobreak >nul

REM 6. Open Browser
start http://localhost:5173

echo ==================================================
echo  YT-sub Studio is running!
echo  Browser opened at: http://localhost:5173
echo ==================================================
pause

