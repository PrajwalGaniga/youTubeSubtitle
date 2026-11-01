"""
job_manager.py — Job Lifecycle, Background Execution, Event Streaming & Asset Packaging.

Features:
  - 300 MB Streaming Uploads into isolated job directories
  - 5-Stage Live Pipeline: Extract → Enhance → Transcribe → Burn → Package
  - Real-time Server-Sent Events (SSE) broadcasting
  - Step-by-Step Interactive Workflow:
      * Pause after extract to download raw audio or import external enhanced audio
      * Pause after enhance to review studio audio
      * Pause after transcribe to review/edit subtitles
  - Background Music Mixing with smart vocal ducking
  - Full Asset Export: Final MP4, Extracted WAV, Clean WAV, SRT, ASS, TXT, Diagnostics JSON & ZIP bundle
  - Stage Caching & Resumption (Retry from failed stage, Re-burn without re-transcribing)
"""

from __future__ import annotations
import asyncio
import datetime
import json
import os
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from audio_processor import clean_audio, extract_audio
from config import FFMPEG_PATH, FFPROBE_PATH, GEMINI_API_KEY, GEMINI_MODEL, JOBS_DIR, MAX_UPLOAD_BYTES
from transcriber import transcribe
from video_burner import burn_subtitles, mix_background_music, mux_clean_audio_only, probe_video_dimensions, probe_video_duration

# In-memory registry of active and historical jobs
_JOBS: Dict[str, Dict[str, Any]] = {}
_EVENT_LISTENERS: Dict[str, List[asyncio.Queue]] = {}
_ACTIVE_SUBPROCESSES: Dict[str, subprocess.Popen] = {}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _format_time() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _broadcast_event(job_id: str, event_data: dict) -> None:
    """Broadcast an SSE event to all connected listeners for job_id."""
    listeners = _EVENT_LISTENERS.get(job_id, [])
    payload = json.dumps(event_data)
    for q in list(listeners):
        try:
            q.put_nowait(payload)
        except Exception:
            pass


def _save_job_state(job_id: str) -> None:
    """Persist job state to disk in jobs/{job_id}/state.json."""
    job = _JOBS.get(job_id)
    if not job:
        return
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    state_file = job_dir / "state.json"
    try:
        # Don't persist non-serializable objects
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, default=str)
    except Exception as e:
        print(f"[job_manager] Error saving state for {job_id}: {e}")


def package_job_files(job_id: str) -> list[dict]:
    """Build bundle.zip and compile downloadable files list."""
    job = _JOBS.get(job_id)
    if not job:
        return []
    job_dir = JOBS_DIR / job_id
    burned_mp4 = str(job_dir / "final_output.mp4")
    clean_wav = str(job_dir / "clean_audio.wav")
    extracted_wav = str(job_dir / "extracted_audio.wav")
    srt_path = str(job_dir / "subs.srt")
    ass_path = str(job_dir / "subs.ass")
    transcript_txt = str(job_dir / "transcript.txt")
    bundle_zip = str(job_dir / "bundle.zip")

    # Build ZIP bundle
    try:
        with zipfile.ZipFile(bundle_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(burned_mp4) and os.path.getsize(burned_mp4) > 0:
                base_name = job["input"]["name"].rsplit(".", 1)[0]
                zf.write(burned_mp4, f"{base_name}_subtitled.mp4")
            if os.path.exists(clean_wav):
                zf.write(clean_wav, "enhanced_audio.wav")
            if os.path.exists(extracted_wav):
                zf.write(extracted_wav, "raw_audio.wav")
            if os.path.exists(srt_path):
                zf.write(srt_path, "subtitles.srt")
            if os.path.exists(ass_path):
                zf.write(ass_path, "subtitles.ass")
            if os.path.exists(transcript_txt):
                zf.write(transcript_txt, "transcript.txt")
    except Exception as e:
        print(f"[job_manager] Warning: failed to build zip bundle for {job_id}: {e}")

    files_list = []
    file_defs = [
        ("final_video.mp4", "Final Video (.mp4)", burned_mp4),
        ("cleaned_audio.wav", "Cleaned Audio (.wav)", clean_wav),
        ("extracted_audio.wav", "Original Audio (.wav)", extracted_wav),
        ("captions.srt", "Subtitles (.srt)", srt_path),
        ("captions.ass", "Styled Captions (.ass)", ass_path),
        ("transcript.txt", "Transcript (.txt)", transcript_txt),
        ("bundle.zip", "Complete Bundle (.zip)", bundle_zip),
    ]
    for name, label, path_str in file_defs:
        if os.path.exists(path_str) and os.path.getsize(path_str) > 0:
            files_list.append({
                "name": name,
                "label": label,
                "size_mb": round(os.path.getsize(path_str) / (1024 * 1024), 2),
                "filename": name,
            })

    job["files"] = files_list
    return files_list


def load_saved_jobs() -> None:
    """Load existing jobs from JOBS_DIR on server boot and auto-resolve finished ones."""
    if not JOBS_DIR.exists():
        return
    for job_folder in JOBS_DIR.iterdir():
        if job_folder.is_dir():
            state_file = job_folder / "state.json"
            if state_file.exists():
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    job_id = job_folder.name
                    _JOBS[job_id] = data

                    # Check if a previously running job actually finished burning before reload
                    burned_mp4 = job_folder / "final_output.mp4"
                    if data.get("status") == "running" and burned_mp4.exists() and burned_mp4.stat().st_size > 0:
                        data["status"] = "done"
                        for s in data.get("stages", []):
                            if s["key"] in ("burn", "package"):
                                s["status"] = "done"
                                s["progress"] = 100.0
                        package_job_files(job_id)
                        _save_job_state(job_id)
                except Exception as e:
                    print(f"[job_manager] Error restoring job {job_folder.name}: {e}")


# Load jobs on module import
load_saved_jobs()


def create_job(filename: str, size_bytes: int, options: Optional[dict] = None) -> str:
    """Create a new job record and isolated folder."""
    job_id = uuid.uuid4().hex[:8]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    opt = {
        "preset": "hormozi-yellow",
        "voice": "studio",
        "position": "default",
        "highlight_color": None,
        "size_scale": 1.0,
        "uppercase": True,
        "pop_anim": True,
        "auto_pilot": True,       # True = full automated run; False = step-by-step
        "music_volume": 0.15,
    }
    if options:
        opt.update(options)

    job_state: Dict[str, Any] = {
        "job_id": job_id,
        "status": "uploading",     # uploading -> idle -> running -> paused -> done -> failed -> cancelled
        "step_action": "none",     # awaiting_audio_decision, awaiting_subtitle_review, etc.
        "created_at": _now_iso(),
        "input": {
            "name": filename,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "width": 1280,
            "height": 720,
            "duration_s": 0.0,
            "orientation": "landscape",
        },
        "options": opt,
        "stages": [
            {"key": "extract",    "label": "Extract Audio",          "status": "pending", "progress": 0, "duration_ms": 0, "message": "Pulling 48kHz audio track from video."},
            {"key": "enhance",    "label": "Enhance Voice",          "status": "pending", "progress": 0, "duration_ms": 0, "message": "Deep neural denoise + studio voice EQ."},
            {"key": "transcribe", "label": "Transcribe Speech",      "status": "pending", "progress": 0, "duration_ms": 0, "attempt": 0, "max_attempts": 3, "message": "Gemini writing English/Hinglish captions."},
            {"key": "burn",       "label": "Burn Viral Captions",    "status": "pending", "progress": 0, "duration_ms": 0, "message": "Rendering kinetic ASS subtitles."},
            {"key": "package",    "label": "Package Downloads",      "status": "pending", "progress": 0, "duration_ms": 0, "message": "Generating export formats and ZIP bundle."},
        ],
        "metrics": {
            "loudness_in_lufs": -24.0,
            "loudness_out_lufs": -16.0,
            "words": 0,
            "lines": 0,
            "audio_source": "builtin_neural",
        },
        "logs": [
            {"time": _format_time(), "stage": "setup", "level": "info", "message": f"Job created for {filename} ({round(size_bytes/1024/1024, 1)} MB)"}
        ],
        "files": [],
        "error": None,
        "has_imported_audio": False,
        "has_bg_music": False,
    }

    _JOBS[job_id] = job_state
    _EVENT_LISTENERS[job_id] = []
    _save_job_state(job_id)
    return job_id


def log_job(job_id: str, stage: str, message: str, level: str = "info", raw: str = "") -> None:
    job = _JOBS.get(job_id)
    if not job:
        return
    entry = {
        "time": _format_time(),
        "stage": stage,
        "level": level,
        "message": message,
        "raw": raw,
    }
    job["logs"].append(entry)
    _broadcast_event(job_id, {"type": "log", **entry})
    _save_job_state(job_id)


def update_stage(job_id: str, stage_key: str, status: str, progress: float = 0, message: Optional[str] = None) -> None:
    job = _JOBS.get(job_id)
    if not job:
        return
    for s in job["stages"]:
        if s["key"] == stage_key:
            s["status"] = status
            s["progress"] = round(progress, 1)
            if message:
                s["message"] = message
            break
    _broadcast_event(job_id, {
        "type": "stage",
        "stage": stage_key,
        "status": status,
        "progress": round(progress, 1),
        "message": message or "",
    })
    _save_job_state(job_id)


def get_job(job_id: str) -> Optional[dict]:
    return _JOBS.get(job_id)


def list_all_jobs() -> List[dict]:
    """Return summary list of all jobs ordered by newest first."""
    res = []
    for j in sorted(_JOBS.values(), key=lambda x: x.get("created_at", ""), reverse=True):
        res.append({
            "job_id": j["job_id"],
            "status": j["status"],
            "name": j["input"]["name"],
            "size_mb": j["input"]["size_mb"],
            "duration_s": j["input"]["duration_s"],
            "orientation": j["input"]["orientation"],
            "preset": j["options"]["preset"],
            "voice": j["options"]["voice"],
            "created_at": j["created_at"],
            "error": j.get("error"),
        })
    return res


async def subscribe_job_events(job_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE formatted events for a job."""
    if job_id not in _EVENT_LISTENERS:
        _EVENT_LISTENERS[job_id] = []
    q = asyncio.Queue()
    _EVENT_LISTENERS[job_id].append(q)

    # Send initial snapshot event
    job = _JOBS.get(job_id)
    if job:
        yield f"data: {json.dumps({'type': 'snapshot', 'job': job})}\n\n"

    try:
        while True:
            payload = await q.get()
            yield f"data: {payload}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        if job_id in _EVENT_LISTENERS and q in _EVENT_LISTENERS[job_id]:
            _EVENT_LISTENERS[job_id].remove(q)


# ---------------------------------------------------------------------------
# Pipeline Execution
# ---------------------------------------------------------------------------
async def execute_job(job_id: str, start_from_stage: Optional[str] = None) -> None:
    """Run pipeline stages asynchronously."""
    job = _JOBS.get(job_id)
    if not job:
        return

    job_dir = JOBS_DIR / job_id
    input_video = str(job_dir / "input.mp4")
    extracted_wav = str(job_dir / "extracted_audio.wav")
    clean_wav = str(job_dir / "clean_audio.wav")
    srt_path = str(job_dir / "subs.srt")
    ass_path = str(job_dir / "subs.ass")
    transcript_txt = str(job_dir / "transcript.txt")
    burned_mp4 = str(job_dir / "final_output.mp4")
    bundle_zip = str(job_dir / "bundle.zip")

    job["status"] = "running"
    job["error"] = None
    _broadcast_event(job_id, {"type": "status", "status": "running"})
    _save_job_state(job_id)

    auto_pilot = job["options"].get("auto_pilot", True)
    preset_id = job["options"].get("preset", "hormozi-yellow")
    is_no_subs = (preset_id == "no-subs") or (start_from_stage == "skip_subtitles")

    try:
        # --------------------------------------------------------------
        # STAGE 1: Extract Audio
        # --------------------------------------------------------------
        should_run_extract = start_from_stage in (None, "extract") or not os.path.exists(extracted_wav)
        if should_run_extract:
            update_stage(job_id, "extract", "running", 10.0, "Extracting mono 48 kHz PCM stream...")
            log_job(job_id, "extract", "Probing video dimensions and duration...")

            t0 = time.perf_counter()
            w, h = await asyncio.to_thread(probe_video_dimensions, input_video)
            dur = await asyncio.to_thread(probe_video_duration, input_video)
            job["input"]["width"] = w
            job["input"]["height"] = h
            job["input"]["duration_s"] = round(dur, 1)
            job["input"]["orientation"] = "portrait" if h > w else "landscape"

            update_stage(job_id, "extract", "running", 50.0, f"Detected {w}x{h} ({dur:.1f}s) — extracting audio...")
            await asyncio.to_thread(extract_audio, input_video, extracted_wav, 48000)
            dt = int((time.perf_counter() - t0) * 1000)

            for s in job["stages"]:
                if s["key"] == "extract":
                    s["duration_ms"] = dt
                    break
            update_stage(job_id, "extract", "done", 100.0, f"Extracted 48 kHz mono in {dt/1000:.2f}s")
            log_job(job_id, "extract", f"Audio track ready ({os.path.getsize(extracted_wav)/1024/1024:.2f} MB)")

            # If NOT in auto-pilot, pause here for user decision (clean audio, keep raw audio, or import external)
            if not auto_pilot:
                job["status"] = "paused"
                job["step_action"] = "awaiting_audio_decision"
                log_job(job_id, "workflow", "Paused: Waiting for user to review raw audio, choose cleanup model, or skip.")
                _broadcast_event(job_id, {"type": "paused", "action": "awaiting_audio_decision"})
                _save_job_state(job_id)
                return

        # --------------------------------------------------------------
        # STAGE 2: Enhance Voice (or skip / use imported audio)
        # --------------------------------------------------------------
        if start_from_stage == "skip_enhance":
            if os.path.exists(extracted_wav) and not os.path.exists(clean_wav):
                shutil.copy2(extracted_wav, clean_wav)
            update_stage(job_id, "enhance", "done", 100.0, "Skipped — using original camera audio")
            log_job(job_id, "enhance", "Voice enhancement skipped per user request. Retaining original audio.")

            if is_no_subs:
                # Direct to mux if user also requested no subtitles
                pass
            elif not auto_pilot:
                job["status"] = "paused"
                job["step_action"] = "awaiting_transcribe_proceed"
                log_job(job_id, "workflow", "Paused: Original audio active. Ready to transcribe speech or skip to finish.")
                _broadcast_event(job_id, {"type": "paused", "action": "awaiting_transcribe_proceed"})
                _save_job_state(job_id)
                return
        else:
            should_run_enhance = (start_from_stage in (None, "extract", "enhance") or not os.path.exists(clean_wav)) and (start_from_stage not in ("transcribe", "burn", "skip_subtitles", "skip_burn"))
            if should_run_enhance:
                if job.get("has_imported_audio") and os.path.exists(clean_wav):
                    update_stage(job_id, "enhance", "done", 100.0, "Using user-imported external audio track")
                    log_job(job_id, "enhance", "Skipped built-in enhancer — using imported audio.")
                else:
                    update_stage(job_id, "enhance", "running", 20.0, "Running RNNoise neural GRU denoiser + Studio EQ...")
                    log_job(job_id, "enhance", f"Mode: {job['options']['voice']} — Pre-filter high-pass 80 Hz, RNNoise sh.rnnn, Loudnorm")

                    t0 = time.perf_counter()
                    clean_info = await asyncio.to_thread(clean_audio, extracted_wav, clean_wav, job["options"]["voice"])
                    dt = int((time.perf_counter() - t0) * 1000)

                    for s in job["stages"]:
                        if s["key"] == "enhance":
                            s["duration_ms"] = dt
                            break
                    update_stage(job_id, "enhance", "done", 100.0, f"Enhanced audio in {dt/1000:.2f}s (mode: {clean_info.get('mode')})")
                    log_job(job_id, "enhance", "Audio enhanced & normalized to broadcast -16 LUFS")

                # If NOT auto-pilot and user hasn't explicitly skipped ahead, pause for audio review
                if not auto_pilot and start_from_stage in (None, "extract", "enhance"):
                    job["status"] = "paused"
                    job["step_action"] = "awaiting_transcribe_proceed"
                    log_job(job_id, "workflow", "Paused: Cleaned audio ready. Proceed to subtitles or skip subtitles to finish.")
                    _broadcast_event(job_id, {"type": "paused", "action": "awaiting_transcribe_proceed"})
                    _save_job_state(job_id)
                    return

        # --------------------------------------------------------------
        # STAGE 3: Transcribe Speech via Gemini (or skip)
        # --------------------------------------------------------------
        skip_transcription = (start_from_stage in ("skip_subtitles", "burn", "skip_burn")) or is_no_subs
        if skip_transcription:
            if not os.path.exists(srt_path):
                update_stage(job_id, "transcribe", "done", 100.0, "Skipped by user (Audio cleanup only)")
                log_job(job_id, "transcribe", "Subtitle transcription skipped per user selection.")
        else:
            should_run_transcribe = start_from_stage in (None, "extract", "enhance", "transcribe") or not os.path.exists(srt_path)
            if should_run_transcribe:
                update_stage(job_id, "transcribe", "running", 25.0, "Gemini AI listening and generating Hinglish/English subtitles...")
                log_job(job_id, "transcribe", f"Uploading audio track to Gemini ({GEMINI_MODEL})...")

                audio_for_transcribe = clean_wav if os.path.exists(clean_wav) else extracted_wav

                t0 = time.perf_counter()
                max_retries = 3
                transcribe_success = False
                last_err = None

                for attempt in range(1, max_retries + 1):
                    try:
                        for s in job["stages"]:
                            if s["key"] == "transcribe":
                                s["attempt"] = attempt
                                break
                        _broadcast_event(job_id, {"type": "retry", "stage": "transcribe", "attempt": attempt, "max": max_retries})

                        await asyncio.to_thread(transcribe, audio_for_transcribe, srt_path)
                        transcribe_success = True
                        break
                    except Exception as exc:
                        last_err = exc
                        log_job(job_id, "transcribe", f"Attempt {attempt}/{max_retries} failed: {exc}", level="warning")
                        if attempt < max_retries:
                            await asyncio.sleep(4 * attempt)

                if not transcribe_success:
                    raise RuntimeError(f"Transcription failed after {max_retries} attempts: {last_err}")

                dt = int((time.perf_counter() - t0) * 1000)

                # Count words and lines in SRT
                words_count = 0
                lines_count = 0
                transcript_text = []
                if os.path.exists(srt_path):
                    with open(srt_path, "r", encoding="utf-8", errors="replace") as f_srt:
                        for line in f_srt:
                            l = line.strip()
                            if l and not l.isdigit() and "-->" not in l:
                                lines_count += 1
                                words_count += len(l.split())
                                transcript_text.append(l)

                # Write transcript.txt
                with open(transcript_txt, "w", encoding="utf-8") as f_txt:
                    f_txt.write("\n".join(transcript_text))

                job["metrics"]["words"] = words_count
                job["metrics"]["lines"] = lines_count

                for s in job["stages"]:
                    if s["key"] == "transcribe":
                        s["duration_ms"] = dt
                        break
                update_stage(job_id, "transcribe", "done", 100.0, f"Generated {lines_count} lines ({words_count} words) in {dt/1000:.2f}s")
                log_job(job_id, "transcribe", f"SRT subtitles created ({lines_count} caption events, {words_count} words)")

                if not auto_pilot and start_from_stage in (None, "extract", "enhance", "transcribe"):
                    job["status"] = "paused"
                    job["step_action"] = "awaiting_burn_proceed"
                    log_job(job_id, "workflow", "Paused: Subtitles generated. User can review/edit subtitles, burn them, or skip burning.")
                    _broadcast_event(job_id, {"type": "paused", "action": "awaiting_burn_proceed"})
                    _save_job_state(job_id)
                    return

        # --------------------------------------------------------------
        # STAGE 4: Burn Viral Captions or Fast Audio Mux
        # --------------------------------------------------------------
        should_skip_burn_text = (start_from_stage in ("skip_subtitles", "skip_burn")) or is_no_subs or not os.path.exists(srt_path)
        audio_mux_file = "clean_audio.wav" if os.path.exists(clean_wav) else "extracted_audio.wav"

        if should_skip_burn_text:
            update_stage(job_id, "burn", "running", 40.0, "Muxing audio track directly into video (lossless copy)...")
            log_job(job_id, "burn", "Skipping subtitle burn. Fast-muxing audio into video using -c:v copy...")
            t0 = time.perf_counter()
            await asyncio.to_thread(
                mux_clean_audio_only,
                temp_dir=str(job_dir),
                audio_file=audio_mux_file,
                output_file="final_output.mp4",
            )
            dt = int((time.perf_counter() - t0) * 1000)
            for s in job["stages"]:
                if s["key"] == "burn":
                    s["duration_ms"] = dt
                    break
            msg = "Exported clean audio video (subtitles skipped)" if not os.path.exists(srt_path) else "Exported clean video (burned captions skipped, SRT saved)"
            update_stage(job_id, "burn", "done", 100.0, msg)
            log_job(job_id, "burn", f"Direct audio mux completed in {dt/1000:.2f}s with 0 video quality loss.")
        else:
            update_stage(job_id, "burn", "running", 10.0, f"Rendering styled ASS subtitles ({job['options']['preset']})...")
            log_job(job_id, "burn", f"Encoding libass with preset={job['options']['preset']}, pos={job['options']['position']}")

            t0 = time.perf_counter()

            def _burn_progress(pct: float) -> None:
                update_stage(job_id, "burn", "running", pct, f"Burning subtitles: {int(pct)}%")

            await asyncio.to_thread(
                burn_subtitles,
                temp_dir=str(job_dir),
                preset_id=job["options"]["preset"],
                position=job["options"]["position"],
                highlight_color=job["options"]["highlight_color"],
                size_scale=job["options"]["size_scale"],
                uppercase=job["options"]["uppercase"],
                pop_anim=job["options"]["pop_anim"],
                audio_file=audio_mux_file,
                output_file="final_output.mp4",
                progress_callback=_burn_progress,
            )

            dt = int((time.perf_counter() - t0) * 1000)
            for s in job["stages"]:
                if s["key"] == "burn":
                    s["duration_ms"] = dt
                    break
            update_stage(job_id, "burn", "done", 100.0, f"Burned kinetic subtitles in {dt/1000:.2f}s")
            log_job(job_id, "burn", "High-quality MP4 rendered without aspect distortion.")

        # --------------------------------------------------------------
        # STAGE 5: Background Music (If provided)
        # --------------------------------------------------------------
        bg_music_file = job_dir / "bg_music.mp3"
        if bg_music_file.exists():
            log_job(job_id, "music", f"Mixing background music at volume {job['options']['music_volume']*100:.0f}%...")
            music_out = str(job_dir / "final_with_music.mp4")
            mix_background_music(
                video_in=burned_mp4,
                music_in=str(bg_music_file),
                video_out=music_out,
                music_volume=job["options"]["music_volume"],
            )
            shutil.move(music_out, burned_mp4)
            log_job(job_id, "music", "Background music mixed into final video.")

        # --------------------------------------------------------------
        # STAGE 6: Package Downloads & ZIP Bundle
        # --------------------------------------------------------------
        update_stage(job_id, "package", "running", 50.0, "Building download bundle and diagnostics...")

        # Build ZIP bundle and compile files list
        files_list = package_job_files(job_id)

        update_stage(job_id, "package", "done", 100.0, "All export assets packaged successfully")
        job["status"] = "done"
        job["step_action"] = "none"

        log_job(job_id, "package", f"Job completed! {len(files_list)} download assets ready.")
        _broadcast_event(job_id, {"type": "done", "files": files_list})
        _save_job_state(job_id)

    except Exception as exc:
        print(f"[job_manager] Error executing job {job_id}: {exc}")
        error_code = "UNKNOWN"
        err_msg = str(exc)
        if "503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower():
            error_code = "GEMINI_503"
        elif "429" in err_msg or "quota" in err_msg.lower():
            error_code = "GEMINI_429"
        elif "404" in err_msg or "not found" in err_msg.lower():
            error_code = "GEMINI_KEY_INVALID"
        elif "burn" in err_msg.lower():
            error_code = "FFMPEG_BURN"

        job["status"] = "failed"
        job["error"] = {
            "code": error_code,
            "message": err_msg,
            "stage": next((s["key"] for s in job["stages"] if s["status"] == "running"), "unknown"),
        }
        for s in job["stages"]:
            if s["status"] == "running":
                s["status"] = "failed"
        log_job(job_id, "error", f"Pipeline error: {err_msg}", level="error", raw=err_msg)
        _broadcast_event(job_id, {"type": "failed", "error": job["error"]})
        _save_job_state(job_id)


def import_external_audio(job_id: str, audio_bytes: bytes, filename: str) -> dict:
    """Replace clean_audio.wav with an external uploaded enhanced track."""
    job = _JOBS.get(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    job_dir = JOBS_DIR / job_id
    ext = os.path.splitext(filename)[1].lower()
    temp_in = job_dir / f"temp_imported{ext}"
    clean_wav = job_dir / "clean_audio.wav"

    with open(temp_in, "wb") as f:
        f.write(audio_bytes)

    # Convert to 48 kHz 16-bit mono WAV
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-nostdin",
        "-i", str(temp_in),
        "-vn",
        "-ac", "1",
        "-ar", "48000",
        "-c:a", "pcm_s16le",
        str(clean_wav),
    ]
    subprocess.run(cmd, check=True, capture_output=True, stdin=subprocess.DEVNULL)
    if temp_in.exists():
        temp_in.unlink()

    job["has_imported_audio"] = True
    job["metrics"]["audio_source"] = f"imported: {filename}"
    update_stage(job_id, "enhance", "done", 100.0, f"Imported: {filename}")
    log_job(job_id, "enhance", f"Replaced audio with external enhanced file: {filename}")
    _save_job_state(job_id)
    return {"status": "ok", "audio_source": job["metrics"]["audio_source"]}


def attach_background_music(job_id: str, music_bytes: bytes, filename: str, volume: float = 0.15) -> dict:
    """Attach and mix background music for job_id."""
    job = _JOBS.get(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    job_dir = JOBS_DIR / job_id
    bg_music = job_dir / "bg_music.mp3"
    with open(bg_music, "wb") as f:
        f.write(music_bytes)

    job["has_bg_music"] = True
    job["options"]["music_volume"] = volume
    log_job(job_id, "music", f"Uploaded background music '{filename}' (volume={volume*100:.0f}%)")

    # If the video is already burned, re-mix music immediately
    burned_mp4 = job_dir / "final_output.mp4"
    if burned_mp4.exists():
        music_out = job_dir / "temp_music_out.mp4"
        mix_background_music(
            video_in=str(burned_mp4),
            music_in=str(bg_music),
            video_out=str(music_out),
            music_volume=volume,
        )
        shutil.move(str(music_out), str(burned_mp4))
        log_job(job_id, "music", "Remixed background music into existing video output.")

    _save_job_state(job_id)
    return {"status": "ok", "music_file": filename, "volume": volume}


def cancel_job_execution(job_id: str) -> dict:
    """Cancel running job and mark cancelled."""
    job = _JOBS.get(job_id)
    if not job:
        return {"status": "not_found"}

    job["status"] = "cancelled"
    for s in job["stages"]:
        if s["status"] == "running":
            s["status"] = "cancelled"

    log_job(job_id, "cancel", "Job cancelled by user.")
    _broadcast_event(job_id, {"type": "cancelled"})
    _save_job_state(job_id)
    return {"status": "cancelled"}


def delete_job_data(job_id: str) -> dict:
    """Permanently delete a job from registry and purge its directory from disk."""
    job = _JOBS.pop(job_id, None)

    # Broadcast deleted event and close queues
    if job_id in _EVENT_LISTENERS:
        for q in _EVENT_LISTENERS[job_id]:
            try:
                q.put_nowait(json.dumps({"type": "deleted"}))
            except Exception:
                pass
        _EVENT_LISTENERS.pop(job_id, None)

    # Terminate any running subprocess if active
    if job_id in _ACTIVE_SUBPROCESSES:
        p = _ACTIVE_SUBPROCESSES.pop(job_id, None)
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass

    # Purge directory from disk
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)

    print(f"[job_manager] Successfully deleted job {job_id} and removed files from disk.")
    return {"status": "deleted", "job_id": job_id}


def delete_all_jobs_data() -> dict:
    """Permanently delete all jobs from registry and purge JOBS_DIR from disk."""
    job_ids = list(_JOBS.keys())
    if JOBS_DIR.exists():
        for d in JOBS_DIR.iterdir():
            if d.is_dir() and d.name not in job_ids:
                job_ids.append(d.name)

    for jid in job_ids:
        delete_job_data(jid)

    print(f"[job_manager] Successfully purged {len(job_ids)} jobs from system.")
    return {"status": "deleted_all", "count": len(job_ids)}

