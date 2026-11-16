"""
main.py — FastAPI Application Entry Point for YT-sub v3 Studio.

Features:
  - 300 MB Streaming Uploads
  - Asynchronous Job Model (POST /api/jobs returns job_id immediately)
  - Server-Sent Events (SSE) live progress & log streaming (GET /api/jobs/{id}/events)
  - Interactive Step-by-Step Workflow (download raw audio, import external enhanced audio)
  - Background Music Upload & Ducking Mix
  - Full Asset Export (MP4, WAV, SRT, ASS, TXT, JSON, ZIP)
  - Health & Diagnostics Dashboard (GET /api/health)
"""

from __future__ import annotations
import asyncio
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ass_generator import PRESETS
from audio_processor import clean_audio, extract_audio
from config import FFMPEG_PATH, FFPROBE_PATH, GEMINI_API_KEY, GEMINI_MODEL, JOBS_DIR, MAX_UPLOAD_BYTES
from transcriber import transcribe
from video_burner import extract_video_thumbnail, probe_video_duration, reformat_video_aspect
from job_manager import (
    attach_background_music,
    cancel_job_execution,
    create_job,
    delete_all_jobs_data,
    delete_job_data,
    execute_job,
    get_job,
    import_external_audio,
    list_all_jobs,
    log_job,
    subscribe_job_events,
    update_stage,
)

# ---------------------------------------------------------------------------
# App Initialization
# ---------------------------------------------------------------------------
app = FastAPI(
    title="YT-sub Studio v3 — AI Video Audio Cleaner & Auto-Subtitler",
    description="Prajwal's Personal YouTube Creator Studio & AI Video Production Pipeline.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health & Configuration Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health", tags=["system"])
async def system_health():
    """System health check for settings and header status dot."""
    ffmpeg_ok = False
    ffmpeg_version = "Unknown"
    try:
        res = subprocess.run([FFMPEG_PATH, "-version"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        ffmpeg_ok = res.returncode == 0
        if ffmpeg_ok and res.stdout:
            ffmpeg_version = res.stdout.splitlines()[0]
    except Exception:
        pass

    gemini_ok = bool(GEMINI_API_KEY and len(GEMINI_API_KEY) > 10)

    # Check free disk space
    free_gb = 0.0
    try:
        usage = shutil.disk_usage(JOBS_DIR)
        free_gb = round(usage.free / (1024 ** 3), 1)
    except Exception:
        pass

    # Check neural model availability
    models_dir = Path(__file__).parent / "models"
    has_rnnoise = (models_dir / "sh.rnnn").exists()

    return {
        "status": "healthy" if (ffmpeg_ok and gemini_ok) else "degraded",
        "gemini": {
            "configured": gemini_ok,
            "model": GEMINI_MODEL,
        },
        "ffmpeg": {
            "found": ffmpeg_ok,
            "version": ffmpeg_version,
            "path": FFMPEG_PATH,
        },
        "neural_models": {
            "rnnoise": has_rnnoise,
            "models_dir": str(models_dir),
        },
        "storage": {
            "free_gb": free_gb,
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "jobs_dir": str(JOBS_DIR),
        },
    }


@app.get("/api/presets", tags=["styling"])
async def list_presets():
    """Return the list of available viral subtitle presets."""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "font": p["font"],
            "primary": p["primary"],
            "highlight": p["highlight"],
            "outline_color": p["outline_color"],
            "border_style": p["border_style"],
            "uppercase": p["uppercase"],
            "pop": p["pop"],
        }
        for p in PRESETS.values()
    ]


# ---------------------------------------------------------------------------
# Job Lifecycle Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/jobs", tags=["jobs"])
async def create_and_start_job(
    file: UploadFile = File(..., description="MP4 video file (up to 300 MB)"),
    preset_id: str = Form("hormozi-yellow"),
    voice_mode: str = Form("studio"),
    position: str = Form("default"),
    highlight_color: Optional[str] = Form(None),
    size_scale: float = Form(1.0),
    uppercase: bool = Form(True),
    pop_anim: bool = Form(True),
    auto_pilot: bool = Form(True),
    music_volume: float = Form(0.15),
):
    """
    Stream upload of MP4 file (up to 300 MB in 1 MB chunks) and initialize job.
    Returns { job_id: "..." } immediately.
    """
    filename = file.filename or "video.mp4"
    if not filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Only .mp4 video files are accepted.")

    options = {
        "preset": preset_id,
        "voice": voice_mode,
        "position": position,
        "highlight_color": highlight_color,
        "size_scale": size_scale,
        "uppercase": uppercase,
        "pop_anim": pop_anim,
        "auto_pilot": auto_pilot,
        "music_volume": music_volume,
    }

    # Initialize job in registry
    job_id = create_job(filename=filename, size_bytes=0, options=options)
    job_dir = JOBS_DIR / job_id
    input_path = job_dir / "input.mp4"

    # Stream file to disk in 1 MB chunks and enforce 300 MB cap
    total_bytes = 0
    try:
        with open(input_path, "wb") as f_out:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    f_out.close()
                    shutil.rmtree(job_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                    )
                f_out.write(chunk)

        job = get_job(job_id)
        if job:
            job["input"]["size_mb"] = round(total_bytes / (1024 * 1024), 2)
            job["status"] = "running"
            log_job(job_id, "upload", f"Upload completed ({job['input']['size_mb']} MB). Starting pipeline.")

        # Kick off background execution and thumbnail extraction
        asyncio.create_task(execute_job(job_id))
        try:
            asyncio.create_task(asyncio.to_thread(extract_video_thumbnail, str(input_path), str(job_dir / "thumbnail.jpg")))
        except Exception:
            pass
        return {"job_id": job_id, "status": "running"}

    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")


@app.get("/api/jobs/{job_id}", tags=["jobs"])
async def get_job_status(job_id: str):
    """Retrieve full snapshot of job state."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/jobs/{job_id}/events", tags=["jobs"])
async def job_events_stream(job_id: str):
    """Server-Sent Events (SSE) live progress & log stream."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return StreamingResponse(
        subscribe_job_events(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/jobs/{job_id}/resume", tags=["jobs"])
async def resume_job_step(
    job_id: str,
    target_stage: Optional[str] = Form(None),
):
    """Resume execution to the next stage when in step-by-step workflow."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    next_stage = target_stage
    if not next_stage:
        # Determine next stage based on current step_action
        if job.get("step_action") == "awaiting_audio_decision":
            next_stage = "enhance"
        elif job.get("step_action") == "awaiting_transcribe_proceed":
            next_stage = "transcribe"
        elif job.get("step_action") == "awaiting_burn_proceed":
            next_stage = "burn"
        else:
            next_stage = "extract"

    job["status"] = "running"
    job["step_action"] = "none"
    log_job(job_id, "workflow", f"User resumed pipeline -> {next_stage}")
    asyncio.create_task(execute_job(job_id, start_from_stage=next_stage))
    return {"status": "resumed", "stage": next_stage}


@app.post("/api/jobs/{job_id}/import-audio", tags=["jobs"])
async def upload_external_audio(
    job_id: str,
    file: UploadFile = File(..., description="External enhanced audio file (.wav, .mp3)"),
):
    """
    Allow user to replace the video's audio track with an external enhanced file
    (e.g. from Adobe Podcast, ElevenLabs, Audacity, or clean mic recording).
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    filename = file.filename or "enhanced_audio.wav"
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file too large (max 100 MB).")

    res = import_external_audio(job_id=job_id, audio_bytes=content, filename=filename)
    return res


@app.post("/api/jobs/{job_id}/music", tags=["jobs"])
async def upload_background_music(
    job_id: str,
    file: UploadFile = File(..., description="Background music track (.mp3, .wav)"),
    volume: float = Form(0.15, description="Music volume 0.05 to 0.40"),
):
    """
    Upload and mix a background music track under speech.
    Can be called before burning or added to an already burned video!
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    filename = file.filename or "music.mp3"
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Music file too large (max 100 MB).")

    res = attach_background_music(job_id=job_id, music_bytes=content, filename=filename, volume=volume)
    return res


@app.post("/api/jobs/{job_id}/reburn", tags=["jobs"])
async def reburn_subtitles(
    job_id: str,
    srt_text: Optional[str] = Form(None),
    preset_id: Optional[str] = Form(None),
    position: Optional[str] = Form(None),
    highlight_color: Optional[str] = Form(None),
    size_scale: Optional[float] = Form(None),
    uppercase: Optional[bool] = Form(None),
    pop_anim: Optional[bool] = Form(None),
):
    """
    Re-run Stage 4 (Burn) in seconds with updated caption text or style preset
    without re-doing audio cleaning or Gemini transcription!
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    job_dir = JOBS_DIR / job_id
    if srt_text:
        srt_path = job_dir / "subs.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_text)
        log_job(job_id, "burn", "Updated SRT caption text from user editor.")

    if preset_id:
        job["options"]["preset"] = preset_id
    if position:
        job["options"]["position"] = position
    if highlight_color is not None:
        job["options"]["highlight_color"] = highlight_color
    if size_scale is not None:
        job["options"]["size_scale"] = size_scale
    if uppercase is not None:
        job["options"]["uppercase"] = uppercase
    if pop_anim is not None:
        job["options"]["pop_anim"] = pop_anim

    log_job(job_id, "burn", "Re-burning video with updated styles...")
    asyncio.create_task(execute_job(job_id, start_from_stage="burn"))
    return {"status": "reburning"}


@app.post("/api/jobs/{job_id}/retry", tags=["jobs"])
async def retry_failed_job(job_id: str):
    """Retry from the failed stage, reusing all earlier completed stage outputs."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    failed_stage = "extract"
    for s in job["stages"]:
        if s["status"] in ("failed", "pending"):
            failed_stage = s["key"]
            break

    log_job(job_id, "retry", f"Retrying pipeline starting from stage: {failed_stage}")
    asyncio.create_task(execute_job(job_id, start_from_stage=failed_stage))
    return {"status": "retrying", "stage": failed_stage}


@app.post("/api/jobs/{job_id}/cancel", tags=["jobs"])
async def cancel_job(job_id: str):
    """Cancel a running job."""
    return cancel_job_execution(job_id)


@app.delete("/api/jobs/{job_id}", tags=["jobs"])
async def delete_job(job_id: str):
    """Permanently delete a project and purge its directory from disk."""
    job_dir = JOBS_DIR / job_id
    job = get_job(job_id)
    if not job and not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found.")
    res = delete_job_data(job_id)
    return res


@app.delete("/api/jobs", tags=["jobs"])
async def delete_all_jobs():
    """Permanently delete all projects and purge disk storage."""
    res = delete_all_jobs_data()
    return res


@app.post("/api/jobs/{job_id}/reformat", tags=["downloads"])
async def export_reformatted_video(
    job_id: str,
    target_aspect: str = Form("9:16"),
    mode: str = Form("letterbox"),
):
    """
    Reformat final subtitled video into target aspect ratio (9:16 Shorts or 16:9 Landscape)
    using letterbox (black bars, preserving 100% frames) or crop.
    Caches the exported video on disk in jobs/{job_id}/.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    job_dir = JOBS_DIR / job_id
    burned_mp4 = job_dir / "final_output.mp4"
    if not burned_mp4.exists() or burned_mp4.stat().st_size == 0:
        raise HTTPException(status_code=400, detail="Final subtitled video is not ready yet.")

    aspect_slug = "9_16" if target_aspect == "9:16" else "16_9"
    mode_slug = "crop" if mode == "crop" else "letterbox"
    out_filename = f"final_{aspect_slug}_{mode_slug}.mp4"
    out_path = job_dir / out_filename

    # If already generated and non-empty, return immediately (cached!)
    if out_path.exists() and out_path.stat().st_size > 0:
        return {
            "status": "ready",
            "filename": out_filename,
            "download_url": f"/api/jobs/{job_id}/files/{out_filename}",
            "cached": True,
            "size_mb": round(out_path.stat().st_size / (1024 * 1024), 2),
        }

    # Offload reformatting to thread pool
    log_job(job_id, "export", f"Reformatting video for download: {target_aspect} ({mode})...")
    try:
        await asyncio.to_thread(
            reformat_video_aspect,
            input_video=str(burned_mp4),
            output_video=str(out_path),
            target_aspect=target_aspect,
            mode=mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reformatting failed: {exc}")

    log_job(job_id, "export", f"Reformatted video ready: {out_filename}")
    return {
        "status": "ready",
        "filename": out_filename,
        "download_url": f"/api/jobs/{job_id}/files/{out_filename}",
        "cached": False,
        "size_mb": round(out_path.stat().st_size / (1024 * 1024), 2),
    }


@app.post("/api/jobs/{job_id}/save-to-folder", tags=["downloads"])
async def save_job_file_to_folder(
    job_id: str,
    target_aspect: str = Form("original"),
    mode: str = Form("letterbox"),
    folder_path: str = Form(...),
    custom_filename: Optional[str] = Form(None),
):
    """
    Export and save a video or asset directly into the user's specified local folder path on their PC.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job directory not found.")

    base_name = "video"
    if job.get("input") and job["input"].get("name"):
        base_name = os.path.splitext(job["input"]["name"])[0]

    # Validate destination folder
    dest_dir_str = folder_path.strip().strip('"').strip("'")
    if not dest_dir_str:
        raise HTTPException(status_code=400, detail="Destination folder path is required.")

    try:
        dest_dir = Path(dest_dir_str).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot create or access folder '{dest_dir_str}': {exc}")

    # Determine source file
    if target_aspect == "original":
        source_file = job_dir / "final_output.mp4"
        if not source_file.exists() or source_file.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="Final subtitled video is not ready yet.")
        out_filename = custom_filename or f"{base_name}_sub.mp4"
    else:
        aspect_slug = "9_16" if target_aspect == "9:16" else "16_9"
        mode_slug = "crop" if mode == "crop" else "letterbox"
        source_filename = f"final_{aspect_slug}_{mode_slug}.mp4"
        source_file = job_dir / source_filename

        # If not already reformatted, reformat now
        if not source_file.exists() or source_file.stat().st_size == 0:
            burned_mp4 = job_dir / "final_output.mp4"
            if not burned_mp4.exists() or burned_mp4.stat().st_size == 0:
                raise HTTPException(status_code=400, detail="Final subtitled video is not ready yet.")
            try:
                await asyncio.to_thread(
                    reformat_video_aspect,
                    input_video=str(burned_mp4),
                    output_video=str(source_file),
                    target_aspect=target_aspect,
                    mode=mode,
                )
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Reformatting failed: {exc}")

        out_filename = custom_filename or f"{base_name}_sub_{aspect_slug}_{mode_slug}.mp4"

    dest_file = dest_dir / out_filename
    try:
        shutil.copy2(source_file, dest_file)
        log_job(job_id, "export", f"Exported file saved directly to folder: {dest_file}")
        return {
            "success": True,
            "filename": out_filename,
            "folder_path": str(dest_dir),
            "full_path": str(dest_file),
            "size_mb": round(dest_file.stat().st_size / (1024 * 1024), 2),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to copy file to '{dest_dir}': {exc}")


@app.get("/api/system/common-folders", tags=["system"])
async def get_system_common_folders():
    """Return common user folders (Desktop, Videos, Downloads, Documents) for quick export selection."""
    home = Path.home()
    folders = {
        "desktop": str(home / "Desktop"),
        "videos": str(home / "Videos"),
        "downloads": str(home / "Downloads"),
        "documents": str(home / "Documents"),
    }
    result = {k: v for k, v in folders.items() if os.path.isdir(v)}
    return {"home": str(home), "folders": result}


@app.post("/api/system/open-explorer", tags=["system"])
async def open_in_file_explorer(payload: dict = Body(...)):
    """Open Windows File Explorer with the saved file or folder selected."""
    target_path = payload.get("path", "").strip().strip('"').strip("'")
    if not target_path:
        raise HTTPException(status_code=400, detail="Path is required.")

    p = Path(target_path).resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail="File or folder does not exist.")

    try:
        if sys.platform.startswith("win"):
            if p.is_file():
                subprocess.Popen(["explorer", f"/select,{str(p)}"])
            else:
                subprocess.Popen(["explorer", str(p)])
        elif sys.platform.startswith("darwin"):
            subprocess.Popen(["open", "-R" if p.is_file() else "", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p.parent if p.is_file() else p)])
        return {"success": True, "opened": str(p)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not open explorer: {exc}")


@app.get("/api/jobs/{job_id}/files/{filename}", tags=["downloads"])
async def download_job_file(job_id: str, filename: str):
    """Download any output asset (MP4, WAV, SRT, ASS, TXT, JSON, ZIP)."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job directory not found.")

    # Determine base filename from original upload (e.g., FirstClip.mp4 -> FirstClip)
    job = get_job(job_id)
    base_name = "video"
    if job and job.get("input") and job["input"].get("name"):
        base_name = os.path.splitext(job["input"]["name"])[0]

    # Mapping logical asset names to physical files
    file_map = {
        "final_video.mp4": job_dir / "final_output.mp4",
        "final_output.mp4": job_dir / "final_output.mp4",
        f"{base_name}_sub.mp4": job_dir / "final_output.mp4",
        "input.mp4": job_dir / "input.mp4",
        "thumbnail.jpg": job_dir / "thumbnail.jpg",
        "cleaned_audio.wav": job_dir / "clean_audio.wav",
        "clean_audio.wav": job_dir / "clean_audio.wav",
        "extracted_audio.wav": job_dir / "extracted_audio.wav",
        "captions.srt": job_dir / "subs.srt",
        "subs.srt": job_dir / "subs.srt",
        "captions.ass": job_dir / "subs.ass",
        "subs.ass": job_dir / "subs.ass",
        "transcript.txt": job_dir / "transcript.txt",
        "diagnostics.json": job_dir / "state.json",
        "bundle.zip": job_dir / "bundle.zip",
    }

    target = file_map.get(filename)
    if not target or not target.exists():
        if filename.endswith("_sub.mp4") and (job_dir / "final_output.mp4").exists():
            target = job_dir / "final_output.mp4"
        else:
            # Check if it's a generated reformatted video in job_dir
            candidate = job_dir / filename
            if candidate.exists() and candidate.is_file() and candidate.parent.resolve() == job_dir.resolve():
                target = candidate
            else:
                raise HTTPException(status_code=404, detail=f"File '{filename}' not found for this job.")

    # Compute user-facing download filename
    download_filename = filename
    if filename in ("final_video.mp4", "final_output.mp4") or filename.endswith("_sub.mp4"):
        download_filename = f"{base_name}_sub.mp4"
    elif filename.startswith("final_") and filename.endswith(".mp4"):
        suffix = filename[len("final_"):-4]
        download_filename = f"{base_name}_sub_{suffix}.mp4"
    elif filename == "bundle.zip":
        download_filename = f"{base_name}_bundle.zip"

    media_types = {
        ".mp4": "video/mp4",
        ".wav": "audio/wav",
        ".srt": "text/plain",
        ".ass": "text/plain",
        ".txt": "text/plain",
        ".json": "application/json",
        ".zip": "application/zip",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    ext = os.path.splitext(filename)[1].lower()
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(target),
        media_type=media_type,
        filename=download_filename,
    )


@app.get("/api/jobs/{job_id}/thumbnail", tags=["projects"])
async def get_job_thumbnail(job_id: str):
    """
    Return video preview thumbnail (first frame).
    Generates on-demand if missing from disk.
    """
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found.")

    thumb_path = job_dir / "thumbnail.jpg"
    if not thumb_path.exists() or thumb_path.stat().st_size == 0:
        input_video = job_dir / "input.mp4"
        if input_video.exists() and input_video.stat().st_size > 0:
            ok = await asyncio.to_thread(extract_video_thumbnail, str(input_video), str(thumb_path))
            if not ok or not thumb_path.exists():
                raise HTTPException(status_code=404, detail="Could not extract video thumbnail.")
        else:
            raise HTTPException(status_code=404, detail="Input video not found for thumbnail.")

    return FileResponse(
        path=str(thumb_path),
        media_type="image/jpeg",
        filename=f"thumb_{job_id}.jpg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/jobs", tags=["projects"])
async def list_jobs_history():
    """List recent and historical projects."""
    return list_all_jobs()


# ---------------------------------------------------------------------------
# Audio to SRT Transcription Endpoints
# ---------------------------------------------------------------------------
AUDIO_JOBS_DIR = Path(__file__).parent / "audio_jobs"
AUDIO_JOBS_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".m4b", ".webm"
}


@app.post("/api/audio/transcribe", tags=["audio"])
async def transcribe_audio_file(
    file: UploadFile = File(..., description="Audio file (.mp3, .wav, .m4a, .aac, .flac, etc.)"),
    clean_voice: bool = Form(True),
    voice_mode: str = Form("studio"),
):
    """
    Directly transcribe any uploaded audio file to a complete timestamped SRT subtitle file.
    Optionally applies RNNoise neural voice cleaning and studio EQ before transcribing.
    """
    filename = file.filename or "audio.mp3"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{ext}'. Accepted formats: {', '.join(sorted(AUDIO_EXTENSIONS))}",
        )

    task_id = uuid.uuid4().hex[:8]
    task_dir = AUDIO_JOBS_DIR / f"audio_{task_id}"
    task_dir.mkdir(parents=True, exist_ok=True)

    input_audio_path = task_dir / f"input{ext}"
    raw_wav_path = task_dir / "raw_audio.wav"
    clean_wav_path = task_dir / "clean_audio.wav"
    srt_path = task_dir / "subs.srt"
    transcript_path = task_dir / "transcript.txt"
    meta_path = task_dir / "meta.json"

    # Stream upload file to disk and enforce size limit
    total_bytes = 0
    try:
        with open(input_audio_path, "wb") as f_out:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    f_out.close()
                    shutil.rmtree(task_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Audio file exceeds maximum size limit of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                    )
                f_out.write(chunk)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")

    try:
        # Convert audio to mono 48 kHz 16-bit PCM WAV via FFmpeg
        await asyncio.to_thread(extract_audio, str(input_audio_path), str(raw_wav_path), 48000)
        dur = await asyncio.to_thread(probe_video_duration, str(raw_wav_path))

        # Optional audio cleaning (RNNoise + Studio EQ)
        audio_for_transcribe = str(raw_wav_path)
        if clean_voice and voice_mode != "off":
            try:
                await asyncio.to_thread(clean_audio, str(raw_wav_path), str(clean_wav_path), voice_mode)
                if clean_wav_path.exists() and clean_wav_path.stat().st_size > 0:
                    audio_for_transcribe = str(clean_wav_path)
            except Exception as clean_err:
                print(f"[audio_transcribe] Audio cleaning warning: {clean_err}")
                audio_for_transcribe = str(raw_wav_path)

        # Transcribe with Gemini
        await asyncio.to_thread(transcribe, audio_for_transcribe, str(srt_path))

        if not srt_path.exists() or srt_path.stat().st_size == 0:
            raise RuntimeError("Gemini did not generate an SRT file.")

        with open(srt_path, "r", encoding="utf-8", errors="replace") as f_srt:
            srt_content = f_srt.read()

        # Parse subtitle lines & words count
        lines_count = 0
        words_count = 0
        transcript_lines = []
        for line in srt_content.splitlines():
            l = line.strip()
            if l and not l.isdigit() and "-->" not in l:
                lines_count += 1
                words_count += len(l.split())
                transcript_lines.append(l)

        transcript_text = "\n".join(transcript_lines)
        with open(transcript_path, "w", encoding="utf-8") as f_txt:
            f_txt.write(transcript_text)

        base_name = os.path.splitext(filename)[0]
        meta = {
            "task_id": f"audio_{task_id}",
            "filename": filename,
            "base_name": base_name,
            "duration_s": round(dur, 1),
            "lines_count": lines_count,
            "words_count": words_count,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
            "cleaned": bool(clean_voice and voice_mode != "off"),
            "voice_mode": voice_mode if clean_voice else "off",
        }
        with open(meta_path, "w", encoding="utf-8") as f_meta:
            json.dump(meta, f_meta, indent=2)

        return {
            "success": True,
            "task_id": f"audio_{task_id}",
            "filename": filename,
            "base_name": base_name,
            "duration_s": round(dur, 1),
            "lines_count": lines_count,
            "words_count": words_count,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
            "srt": srt_content,
            "transcript": transcript_text,
            "cleaned": bool(clean_voice and voice_mode != "off"),
            "voice_mode": voice_mode if clean_voice else "off",
            "download_url": f"/api/audio/audio_{task_id}/download?format=srt",
            "txt_download_url": f"/api/audio/audio_{task_id}/download?format=txt",
            "audio_url": f"/api/audio/audio_{task_id}/audio",
        }

    except Exception as exc:
        print(f"[audio_transcribe] Transcription error: {exc}")
        err_msg = str(exc)
        if "503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower():
            err_msg = "Gemini AI servers are temporarily busy (503). Please try again in a few moments."
        elif "429" in err_msg or "quota" in err_msg.lower():
            err_msg = "Gemini API rate limit reached (429). Please wait a moment and retry."
        elif "valid SRT" in err_msg:
            err_msg = "Could not detect clear speech in this audio recording. Please verify that the audio contains spoken words."
        raise HTTPException(status_code=500, detail=f"Transcription failed: {err_msg}")


@app.get("/api/audio/{task_id}/download", tags=["audio"])
async def download_audio_srt(task_id: str, format: str = "srt"):
    """Download the generated SRT or TXT transcript."""
    task_dir = AUDIO_JOBS_DIR / task_id
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="Audio transcription task not found.")

    meta_file = task_dir / "meta.json"
    base_name = "audio"
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
                base_name = meta.get("base_name", "audio")
        except Exception:
            pass

    if format == "txt":
        target = task_dir / "transcript.txt"
        out_name = f"{base_name}_transcript.txt"
        media_type = "text/plain; charset=utf-8"
    else:
        target = task_dir / "subs.srt"
        out_name = f"{base_name}_subtitles.srt"
        media_type = "text/plain; charset=utf-8"

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found for format '{format}'.")

    return FileResponse(
        path=str(target),
        media_type=media_type,
        filename=out_name,
    )


@app.get("/api/audio/{task_id}/audio", tags=["audio"])
async def stream_task_audio(task_id: str):
    """Stream audio file for playback in the web player."""
    task_dir = AUDIO_JOBS_DIR / task_id
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="Audio transcription task not found.")

    candidates = list(task_dir.glob("input.*"))
    if candidates and candidates[0].exists():
        target = candidates[0]
    else:
        target = task_dir / "raw_audio.wav"

    if not target.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")

    ext = target.suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    media_type = media_types.get(ext, "audio/mpeg")

    return FileResponse(
        path=str(target),
        media_type=media_type,
        filename=target.name,
    )


@app.post("/api/audio/{task_id}/save-to-folder", tags=["audio"])
async def save_audio_file_to_folder(
    task_id: str,
    folder_path: str = Form(...),
    custom_filename: Optional[str] = Form(None),
    format: str = Form("srt"),
):
    """Export and save the generated SRT or TXT directly into a specified local folder on PC."""
    task_dir = AUDIO_JOBS_DIR / task_id
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="Audio transcription task not found.")

    dest_dir_str = folder_path.strip().strip('"').strip("'")
    if not dest_dir_str:
        raise HTTPException(status_code=400, detail="Destination folder path is required.")

    dest_dir = Path(dest_dir_str).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    base_name = "audio"
    meta_file = task_dir / "meta.json"
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
                base_name = meta.get("base_name", "audio")
        except Exception:
            pass

    if format == "txt":
        source_file = task_dir / "transcript.txt"
        out_filename = custom_filename or f"{base_name}_transcript.txt"
    else:
        source_file = task_dir / "subs.srt"
        out_filename = custom_filename or f"{base_name}_subtitles.srt"

    if not source_file.exists():
        raise HTTPException(status_code=404, detail="Transcript file not found.")

    dest_file = dest_dir / out_filename
    shutil.copy2(source_file, dest_file)
    return {
        "success": True,
        "filename": out_filename,
        "folder_path": str(dest_dir),
        "full_path": str(dest_file),
        "size_kb": round(dest_file.stat().st_size / 1024, 2),
    }


# ---------------------------------------------------------------------------
# Serve Frontend Static Build (Production / Cloud Deployment)
# ---------------------------------------------------------------------------
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

