"""
config.py — Centralised configuration for the YT-sub backend.

FFmpeg resolution order:
  1. Explicit FFMPEG_PATH env var (set this in .env if you want to override)
  2. System PATH lookup via shutil.which("ffmpeg")
  3. Known WinGet install location (the user's current install)
"""

import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from backend directory or current directory
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()

# ---------------------------------------------------------------------------
# FFmpeg binary path
# ---------------------------------------------------------------------------
_WINGET_FFMPEG = (
    r"C:\Users\Prajwal\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
)

FFMPEG_PATH: str = (
    os.getenv("FFMPEG_PATH")          # 1. explicit env override
    or shutil.which("ffmpeg")         # 2. system PATH
    or _WINGET_FFMPEG                 # 3. known WinGet location
)

def _get_ffprobe_path(ffmpeg_exe: str) -> str:
    if os.getenv("FFPROBE_PATH"):
        return os.environ["FFPROBE_PATH"]
    try:
        p = shutil.which(ffmpeg_exe) or ffmpeg_exe
        candidate = os.path.join(os.path.dirname(p), "ffprobe.exe" if p.lower().endswith(".exe") else "ffprobe")
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    return shutil.which("ffprobe") or "ffprobe"

FFPROBE_PATH: str = _get_ffprobe_path(FFMPEG_PATH)

# ---------------------------------------------------------------------------
# Gemini API key
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    raise EnvironmentError(
        "GEMINI_API_KEY is not set. "
        "Copy backend/.env.example to backend/.env and add your key."
    )

# ---------------------------------------------------------------------------
# Processing constraints & Job storage
# ---------------------------------------------------------------------------
MAX_UPLOAD_BYTES: int = 300 * 1024 * 1024   # 300 MB

from pathlib import Path
JOBS_DIR: Path = Path(__file__).parent / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Gemini model
# ---------------------------------------------------------------------------
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


