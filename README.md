# youTubeSubtitle (YT-sub Studio)

A dark-mode creator studio for neural audio enhancement, AI Hinglish/English transcription, and viral animated captions (Hormozi, MrBeast, TikTok Box styles).

---

## Features

- **Neural Voice Cleaning**: Deep RNNoise recurrent neural network (60k params) + adaptive FFT filter + broadcast vocal EQ (-16 LUFS).
- **Hinglish/English AI Captions**: Powered by Google Gemini AI with automatic segment & word-level timing distribution.
- **6 Viral Typography Presets**: Hormozi Yellow, TikTok Box, MrBeast Hype, Cyber Neon, Minimal Apple, and Comic Pop.
- **Aspect Ratio Reformatting**: 9:16 Shorts letterbox (100% frames kept) and 9:16 center-crop downloads.
- **Step-by-Step & 1-Click Auto-Pilot**: Run everything end-to-end or pause at each stage to review audio, edit captions, or skip steps.
- **Lossless Audio-Only Export**: Fast-mux clean audio without subtitles in under 0.2s with zero video quality loss.

---

## Prerequisites on Your System

1. **Python 3.10+**: [python.org](https://www.python.org/)
2. **Node.js 18+ & npm**: [nodejs.org](https://nodejs.org/)
3. **FFmpeg with libass**:
   - **Windows**: `winget install Gyan.FFmpeg` or download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (add to PATH).
   - **macOS**: `brew install ffmpeg --with-libass` (or standard `brew install ffmpeg`).
   - **Linux (Ubuntu/Debian)**: `sudo apt update && sudo apt install -y ffmpeg libass-dev`.

---

## Quick Start on a New System

### 1. Clone the Repository
```bash
git clone https://github.com/PrajwalGaniga/youTubeSubtitle.git
cd youTubeSubtitle
```

### 2. Configure Your API Key
Copy the example environment file and add your Google Gemini API Key:
```bash
cp backend/.env.example backend/.env
```
Open `backend/.env` and paste your key:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Run with 1-Click Script

- **Linux / macOS / Git Bash:**
  ```bash
  chmod +x start.sh
  ./start.sh
  ```
- **Windows:**
  Double-click `start.bat` (or run `./start.bat` in CMD/PowerShell).

Both backend (`http://localhost:8000`) and frontend (`http://localhost:5173`) will start automatically!

---

## Manual Startup (Alternative)

If you prefer running terminals manually:

### Terminal 1: Backend
```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

### Terminal 2: Frontend
```bash
cd frontend
npm install
npm run dev
```
Open your browser at `http://localhost:5173`.
