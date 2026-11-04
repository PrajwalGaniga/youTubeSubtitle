"""
video_burner.py — Burn styled ASS subtitles into video with clean audio via FFmpeg.

Features:
  - Video resolution & orientation probing via ffprobe
  - Resolution-matched kinetic ASS generation with 6 viral presets
  - Bundled font isolation in job directory (fontsdir=fonts)
  - Relative filename execution (cwd=temp_dir) preventing Windows libass path escaping bugs
  - High quality encoding: -crf 18, -preset medium, -b:a 192k, -movflags +faststart
  - Background music mixing with vocal ducking
  - Real-time progress monitoring via -progress pipe:1
"""

from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from ass_generator import generate_ass_from_srt
from config import FFMPEG_PATH, FFPROBE_PATH

FONTS_SRC_DIR = Path(__file__).parent / "fonts"


def probe_video_dimensions(video_path: str) -> tuple[int, int]:
    """Probe video for display width and height, accounting for rotation tags."""
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,sample_aspect_ratio:stream_side_data=rotation:stream_tags=rotate",
        "-of", "json",
        video_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
        data = json.loads(res.stdout)
        stream = data["streams"][0]
        w = int(stream["width"])
        h = int(stream["height"])

        # Check rotation metadata (e.g. mobile 9:16 recorded rotated)
        rotation = 0
        for sd in stream.get("side_data_list", []):
            if "rotation" in sd:
                rotation = int(float(sd["rotation"]))
                break
        if not rotation and "tags" in stream and "rotate" in stream["tags"]:
            rotation = int(float(stream["tags"]["rotate"]))

        if abs(rotation) % 180 == 90:
            w, h = h, w

        # Make dimensions even
        w = max(2, int(round(w / 2)) * 2)
        h = max(2, int(round(h / 2)) * 2)
        return w, h
    except Exception as e:
        print(f"[video_burner] Warning: ffprobe failed ({e}), attempting ffmpeg -i fallback...")
        try:
            chk = subprocess.run([FFMPEG_PATH, "-i", video_path], capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL)
            m = re.search(r"Stream.*Video:.*,\s*(\d{2,5})x(\d{2,5})", chk.stderr)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                print(f"[video_burner] Fallback detected: {w}x{h}")
                return max(2, int(round(w / 2)) * 2), max(2, int(round(h / 2)) * 2)
        except Exception as fb_err:
            print(f"[video_burner] Fallback failed: {fb_err}")
        return 1280, 720


def probe_video_duration(video_path: str) -> float:
    """Probe total duration in seconds."""
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
        return max(1.0, float(res.stdout.strip()))
    except Exception:
        return 60.0


def extract_video_thumbnail(video_path: str, thumbnail_path: str) -> bool:
    """
    Extract a high quality first frame preview thumbnail from video_path.
    Uses 0.5s offset to avoid initial black frames, falling back to 0.0s.
    Scales down max width to 640px for fast web display.
    """
    video_path_str = str(video_path)
    thumbnail_path_str = str(thumbnail_path)

    os.makedirs(os.path.dirname(os.path.abspath(thumbnail_path_str)), exist_ok=True)

    # Attempt at 0.5s
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-nostdin",
        "-loglevel", "error",
        "-ss", "00:00:00.500",
        "-i", video_path_str,
        "-vframes", "1",
        "-vf", "scale=min(640\\,iw):-2",
        "-q:v", "2",
        "-update", "1",
        thumbnail_path_str,
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, stdin=subprocess.DEVNULL)
        if os.path.exists(thumbnail_path_str) and os.path.getsize(thumbnail_path_str) > 0:
            return True
    except Exception:
        pass

    # Fallback to 0.0s (start frame)
    cmd_fb = [
        FFMPEG_PATH,
        "-y",
        "-nostdin",
        "-loglevel", "error",
        "-ss", "00:00:00.000",
        "-i", video_path_str,
        "-vframes", "1",
        "-vf", "scale=min(640\\,iw):-2",
        "-q:v", "2",
        "-update", "1",
        thumbnail_path_str,
    ]
    try:
        subprocess.run(cmd_fb, capture_output=True, check=True, stdin=subprocess.DEVNULL)
        return os.path.exists(thumbnail_path_str) and os.path.getsize(thumbnail_path_str) > 0
    except Exception as e:
        print(f"[video_burner] Failed to extract thumbnail: {e}")
        return False


def burn_subtitles(
    temp_dir: str,
    preset_id: str = "hormozi-yellow",
    position: str = "default",
    highlight_color: Optional[str] = None,
    size_scale: float = 1.0,
    uppercase: Optional[bool] = None,
    pop_anim: Optional[bool] = None,
    audio_file: str = "clean_audio.wav",
    output_file: str = "final_output.mp4",
    progress_callback: Optional[Callable[[float], None]] = None,
) -> None:
    """
    Generate styled ASS subtitles and burn them into output_file.

    Args:
        temp_dir: Directory containing input.mp4, audio file, and subs.srt.
        preset_id: Style preset ID (e.g. 'hormozi-yellow', 'tiktok-box', etc.)
        position: 'default', 'bottom', 'center', or 'upper'
        highlight_color: Optional custom hex highlight color (e.g. '#FFE600')
        size_scale: Font size multiplier (0.7 to 1.4)
        uppercase: Whether to force uppercase text
        pop_anim: Whether to apply the scale pop animation
        audio_file: Name of the audio file in temp_dir to mux
        output_file: Name of output video file to write
        progress_callback: Optional callback receiving progress percentage 0-100
    """
    input_video = os.path.join(temp_dir, "input.mp4")
    srt_path = os.path.join(temp_dir, "subs.srt")
    ass_path = os.path.join(temp_dir, "subs.ass")

    # 1. Probe video dimensions and duration
    w, h = probe_video_dimensions(input_video)
    duration = probe_video_duration(input_video)
    print(f"[video_burner] Probed video geometry: {w}x{h} ({'portrait' if h > w else 'landscape'}), duration: {duration:.1f}s")

    # 2. Copy fonts into temp_dir/fonts so fontsdir=fonts is guaranteed to find them
    temp_fonts_dir = os.path.join(temp_dir, "fonts")
    os.makedirs(temp_fonts_dir, exist_ok=True)
    if FONTS_SRC_DIR.exists():
        for font_file in FONTS_SRC_DIR.glob("*.ttf"):
            dest = os.path.join(temp_fonts_dir, font_file.name)
            if not os.path.exists(dest):
                shutil.copy2(font_file, dest)

    # 3. Generate ASS subtitles
    generate_ass_from_srt(
        srt_path=srt_path,
        ass_path=ass_path,
        width=w,
        height=h,
        preset_id=preset_id,
        position=position,
        highlight_color=highlight_color,
        size_scale=size_scale,
        uppercase=uppercase,
        pop_anim=pop_anim,
    )

    # 4. Burn ASS subtitles with audio track
    subtitle_filter = "ass=subs.ass:fontsdir=fonts"

    cmd = [
        FFMPEG_PATH,
        "-y",
        "-nostdin",
        "-loglevel", "error",
        "-progress", "pipe:1",
        "-nostats",
        "-i", "input.mp4",
        "-i", audio_file,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        output_file,
    ]

    print(f"[video_burner] Running ffmpeg in {temp_dir}: {' '.join(cmd[:9])}...")

    p = subprocess.Popen(
        cmd,
        cwd=temp_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        stdin=subprocess.DEVNULL,
        bufsize=1,
    )

    # Parse -progress pipe:1
    if p.stdout:
        for line in p.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    us = int(line.split("=")[1])
                    curr_sec = us / 1_000_000.0
                    pct = min(99.0, max(0.0, (curr_sec / duration) * 100.0))
                    if progress_callback:
                        progress_callback(pct)
                except Exception:
                    pass
            elif line == "progress=end":
                if progress_callback:
                    progress_callback(100.0)

    p.wait()
    if p.returncode != 0:
        err = p.stderr.read() if p.stderr else "Unknown FFmpeg error"
        raise RuntimeError(f"FFmpeg subtitle burn failed (code {p.returncode}): {err[-400:]}")

    if progress_callback:
        progress_callback(100.0)
    print(f"[video_burner] Subtitle burn-in completed successfully -> {output_file}")


def mux_clean_audio_only(
    temp_dir: str,
    audio_file: str = "clean_audio.wav",
    output_file: str = "final_output.mp4",
    progress_callback: Optional[Callable[[float], None]] = None,
) -> None:
    """
    Directly muxes an audio track into input.mp4 without burning any subtitles.
    Uses -c:v copy to make the export instantaneous (0 re-encoding) and 100% lossless.
    """
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-nostdin",
        "-loglevel", "error",
        "-i", "input.mp4",
        "-i", audio_file,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        output_file,
    ]

    print(f"[video_burner] Fast audio mux in {temp_dir}: audio={audio_file} -> {output_file}")
    res = subprocess.run(
        cmd,
        cwd=temp_dir,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg audio mux failed (code {res.returncode}): {res.stderr[-400:]}")

    if progress_callback:
        progress_callback(100.0)
    print(f"[video_burner] Clean audio mux completed -> {output_file}")


def mix_background_music(
    video_in: str,
    music_in: str,
    video_out: str,
    music_volume: float = 0.15,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> None:
    """
    Mix an optional background music track under video_in audio.
    Keeps speech volume at 1.0, applies music_volume to the music track,
    loops music seamlessly with -stream_loop -1, and uses -c:v copy for near-instant rendering.
    """
    # Safe volume clamp 0.02 - 0.60
    vol = max(0.02, min(0.60, float(music_volume)))

    cmd = [
        FFMPEG_PATH,
        "-y",
        "-nostdin",
        "-i", Path(video_in).resolve().as_posix(),
        "-stream_loop", "-1",
        "-i", Path(music_in).resolve().as_posix(),
        "-filter_complex", f"[1:a]volume={vol:.3f}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        Path(video_out).resolve().as_posix(),
    ]

    print(f"[video_burner] Mixing background music (vol={vol:.2f}) into {video_out}...")
    res = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
    if progress_callback:
        progress_callback(100.0)
    print("[video_burner] Background music mixed successfully.")


def reformat_video_aspect(
    input_video: str,
    output_video: str,
    target_aspect: str = "9:16",
    mode: str = "letterbox",
) -> None:
    """
    Reformat an already subtitled video into a target aspect ratio.

    Args:
        input_video: Path to the input subtitled video.
        output_video: Destination path for the reformatted video.
        target_aspect: '9:16' (Shorts/Reels) or '16:9' (YouTube Landscape).
        mode: 'letterbox' (pad with black bars, preserving 100% of video & subtitles)
              or 'crop' (center-crop to fill the entire frame).
    """
    if target_aspect == "9:16":
        tw, th = 1080, 1920
    elif target_aspect == "16:9":
        tw, th = 1920, 1080
    else:
        tw, th = 1080, 1920

    if mode == "crop":
        vf = f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}"
    else:
        # Default: letterbox / pad with pure black bars top/bottom or left/right
        vf = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black"

    cmd = [
        FFMPEG_PATH,
        "-y",
        "-nostdin",
        "-loglevel", "error",
        "-i", Path(input_video).resolve().as_posix(),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        Path(output_video).resolve().as_posix(),
    ]

    print(f"[video_burner] Reformatting video -> aspect={target_aspect}, mode={mode} ({tw}x{th})")
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
    print(f"[video_burner] Reformat completed successfully -> {output_video}")

