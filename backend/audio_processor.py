"""
audio_processor.py — Neural Voice Enhancement & Broadcast DSP Studio Pipeline.

Architecture:
  Pillar 1: De-rumble & Pre-filtering
    - 4th-order High-pass (80 Hz): cuts diaphragm overload, sub-bass AC hum, desk thumps, wind blasts
    - Low-pass (12 kHz): cuts ultrasonic sensor whine and coil hiss
  
  Pillar 2: Deep Recurrent Neural Denoising (RNNoise / arnndn)
    - Ultra-lightweight (~60k params, 297 KB weights) deep GRU recurrent neural network
    - Trained on speech + non-stationary ambient noise (fans, typing, clicks, street noise)
    - RTF < 0.02 on CPU (~85x faster than real-time), 0 VRAM requirement
    - Coupled with Adaptive FFT Denoise (afftdn) for stationary hum tracking
  
  Pillar 3: Vocal Body & Broadcast Studio Polish
    - Chest Body EQ (+2.5 dB @ 130 Hz): restores deep radio-host vocal warmth lost on phone mics
    - Mud Cut (-2.0 dB @ 320 Hz): cuts boxy room resonance and hollow room reflections
    - Vocal Presence EQ (+2.8 dB @ 3.5 kHz): crisp speech clarity & consonant intelligibility
    - Downward Noise Gate (agate): drops noise floor to absolute silence during speech pauses
    - Broadcast Speech Normalizer (speechnorm): levels speech to broadcast loudness (-16 LUFS)
"""

from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from config import FFMPEG_PATH

MODELS_DIR = Path(__file__).parent / "models"
DEFAULT_NEURAL_MODEL = "sh.rnnn"


def extract_audio(video_path: str, wav_path: str, sr: int = 48000) -> None:
    """
    Extract the audio track from video_path as 48 kHz 16-bit mono PCM WAV.
    48 kHz is the broadcast standard for neural speech models and video containers.
    """
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-nostdin",
        "-i", Path(video_path).resolve().as_posix(),
        "-vn",
        "-ac", "1",
        "-ar", str(sr),
        "-c:a", "pcm_s16le",
        Path(wav_path).resolve().as_posix(),
    ]
    subprocess.run(cmd, check=True, capture_output=True, stdin=subprocess.DEVNULL)


def clean_audio(wav_path: str, clean_wav_path: str, mode: str = "studio") -> dict:
    """
    Apply Neural Denoising and Studio Vocal Enhancement.

    Modes:
      - 'studio': Neural RNNoise + Adaptive FFT + Vocal Chest/Presence EQ + Noise Gate + Speechnorm
      - 'clean':  Neural RNNoise + Gentle Adaptive FFT + Subtle Presence + Noise Gate + Speechnorm
      - 'off':    Pass-through (raw audio untouched)

    Returns a dict with processing metadata (mode, neural_model, status).
    """
    if mode == "off":
        if os.path.abspath(wav_path) != os.path.abspath(clean_wav_path):
            shutil.copy2(wav_path, clean_wav_path)
        return {"mode": "off", "status": "pass-through"}

    tmp_dir = os.path.abspath(os.path.dirname(clean_wav_path) or ".")
    os.makedirs(tmp_dir, exist_ok=True)

    staging_out = os.path.join(tmp_dir, "temp_neural_out.wav")
    local_model_file = os.path.join(tmp_dir, DEFAULT_NEURAL_MODEL)

    # 1. Check for neural model weights
    src_model = MODELS_DIR / DEFAULT_NEURAL_MODEL
    has_neural_model = src_model.exists()

    filter_stages: list[str] = []

    # ------------------------------------------------------------------
    # Stage 1: Pre-filtering (High-pass 80 Hz, Low-pass 12 kHz)
    # Cuts microphone blast, wind, desk thumps before neural normalization
    # ------------------------------------------------------------------
    filter_stages.append("highpass=f=80")
    filter_stages.append("lowpass=f=12000")

    # ------------------------------------------------------------------
    # Stage 2: Neural RNNoise Recurrent Network + Adaptive FFT Denoise
    # ------------------------------------------------------------------
    use_neural = False
    if has_neural_model:
        try:
            # Copy model to tmp_dir to prevent Windows drive colon (C:) parsing bug in FFmpeg
            if not os.path.exists(local_model_file):
                shutil.copy2(src_model, local_model_file)
            filter_stages.append(f"arnndn=m={DEFAULT_NEURAL_MODEL}")
            use_neural = True
        except Exception as e:
            print(f"[audio_processor] Warning: Failed to prepare neural model ({e}), falling back to DSP")

    if mode == "studio":
        # Adaptive FFT denoiser to sweep any residual stationary hum
        filter_stages.append("afftdn=nr=10:nf=-32:tn=1")
    else:
        filter_stages.append("afftdn=nr=6:nf=-34:tn=1")

    # ------------------------------------------------------------------
    # Stage 3: Vocal Body & Broadcast Studio Polish
    # ------------------------------------------------------------------
    if mode == "studio":
        # +2.5 dB @ 130 Hz: restores rich chest resonance (podcast / condenser mic body)
        filter_stages.append("equalizer=f=130:width_type=q:width=1.2:g=2.5")
        # -2.0 dB @ 320 Hz: cuts hollow room boxiness and acoustic mud
        filter_stages.append("equalizer=f=320:width_type=q:width=1.0:g=-2.0")
        # +2.8 dB @ 3500 Hz: crisp vocal presence and consonant intelligibility
        filter_stages.append("equalizer=f=3500:width_type=q:width=1.3:g=2.8")
        # Downward noise gate: absolute silence between words
        filter_stages.append("agate=threshold=0.018:ratio=2.5:attack=15:release=220")
        # Broadcast loudness normalization (EBU R128 / BS.1770 compliant: -16 LUFS, -1.5 dB True-Peak limiter)
        filter_stages.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    else:  # 'clean' mode
        # Subtle presence and gentle noise gate
        filter_stages.append("equalizer=f=320:width_type=q:width=1.0:g=-1.5")
        filter_stages.append("equalizer=f=3200:width_type=q:width=1.2:g=1.5")
        filter_stages.append("agate=threshold=0.012:ratio=2.0:attack=15:release=200")
        filter_stages.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    filter_complex = ",".join(filter_stages)

    try:
        in_posix = Path(wav_path).resolve().as_posix()
        out_posix = Path(staging_out).resolve().as_posix()

        cmd = [
            FFMPEG_PATH,
            "-y",
            "-nostdin",
            "-i", in_posix,
            "-af", filter_complex,
            "-ar", "48000",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            out_posix,
        ]
        res = subprocess.run(
            cmd,
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
        )

        if not os.path.exists(staging_out) or os.path.getsize(staging_out) == 0:
            raise RuntimeError("FFmpeg audio enhancement produced an empty file")

        # Move staging file to final clean_wav_path
        shutil.move(staging_out, clean_wav_path)
        print(f"[audio_processor] Neural audio enhancement succeeded (mode={mode}, neural={use_neural}) -> {clean_wav_path}")

        return {
            "mode": mode,
            "neural": use_neural,
            "model": DEFAULT_NEURAL_MODEL if use_neural else "dsp_fallback",
            "status": "success",
        }

    except Exception as exc:
        print(f"[audio_processor] Neural pass error ({exc}). Attempting safe fallback DSP...")
        try:
            fallback_af = "highpass=f=80,afftdn=nr=12:nf=-30:tn=1,loudnorm=I=-16:TP=-1.5:LRA=11"
            subprocess.run(
                [
                    FFMPEG_PATH,
                    "-y",
                    "-nostdin",
                    "-i", Path(wav_path).resolve().as_posix(),
                    "-af", fallback_af,
                    "-ar", "48000",
                    "-ac", "1",
                    "-acodec", "pcm_s16le",
                    Path(clean_wav_path).resolve().as_posix(),
                ],
                check=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )
            print(f"[audio_processor] Fallback DSP completed -> {clean_wav_path}")
            return {"mode": mode, "neural": False, "model": "fallback_dsp", "status": "fallback"}
        except Exception as fb_err:
            print(f"[audio_processor] Fallback also failed ({fb_err}), copying raw wav")
            if os.path.abspath(wav_path) != os.path.abspath(clean_wav_path):
                shutil.copy2(wav_path, clean_wav_path)
            return {"mode": mode, "neural": False, "status": "failed_passthrough"}

    finally:
        if os.path.exists(staging_out):
            try:
                os.remove(staging_out)
            except Exception:
                pass
        if os.path.exists(local_model_file) and os.path.abspath(local_model_file) != os.path.abspath(src_model):
            try:
                os.remove(local_model_file)
            except Exception:
                pass
