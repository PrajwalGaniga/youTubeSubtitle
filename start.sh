#!/usr/bin/env bash
# ==============================================================================
# YT-sub Studio — 1-Click Startup Script (Linux / macOS / Git Bash)
# ==============================================================================

set -e

# Change to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo " Starting YT-sub Studio"
echo "=================================================="

# 1. Check for .env file
if [ ! -f "backend/.env" ]; then
    echo "[!] backend/.env not found."
    if [ -f "backend/.env.example" ]; then
        echo "[+] Creating backend/.env from backend/.env.example..."
        cp backend/.env.example backend/.env
        echo "[!] Please edit backend/.env and add your GEMINI_API_KEY before running."
    fi
fi

# 2. Check/Install Python Dependencies
echo "[+] Checking Python backend dependencies..."
python3 -m pip install -r backend/requirements.txt -q 2>/dev/null || python -m pip install -r backend/requirements.txt -q

# 3. Check/Install Frontend Dependencies
echo "[+] Checking Frontend dependencies..."
if [ ! -d "frontend/node_modules" ]; then
    echo "[+] Installing node_modules in frontend/..."
    (cd frontend && npm install)
fi

# 4. Trap exit signals to terminate child background processes
cleanup() {
    echo ""
    echo "[*] Shutting down YT-sub Studio..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 5. Start Backend (FastAPI on port 8000)
echo "[+] Launching FastAPI backend on http://localhost:8000..."
(cd backend && python3 -m uvicorn main:app --reload --port 8000 2>/dev/null || cd backend && python -m uvicorn main:app --reload --port 8000) &
BACKEND_PID=$!

# Wait briefly for backend to bind port
sleep 2

# 6. Start Frontend (Vite on port 5173)
echo "[+] Launching Vite frontend on http://localhost:5173..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo ""
echo "=================================================="
echo " YT-sub Studio is live!"
echo " Open in your browser: http://localhost:5173"
echo " Press Ctrl+C in this terminal to stop both servers"
echo "=================================================="

wait

