"""
transcriber.py — Gemini-powered Hindi/English SRT subtitle generation.

Pipeline:
  1. Upload cleaned WAV to the Gemini File API
  2. Prompt gemini-1.5-pro with a strict SRT-only instruction
  3. Strip any accidental markdown fences
  4. Validate the SRT structure (must contain '-->') 
  5. Save to srt_path
  6. Delete the remote file to free Gemini quota
"""

import re
import time

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL


# ---------------------------------------------------------------------------
# Prompt — strict SRT-only output
# ---------------------------------------------------------------------------
_SRT_PROMPT = """\
Listen carefully to this audio recording. The speaker may speak in Hindi, English, or a mix of both (Hinglish).

CRITICAL SCRIPT REQUIREMENT:
All subtitle text MUST be in the English (Latin/Roman) alphabet ONLY.
- NEVER use Devanagari or Hindi script (NO characters like 'नमस्ते', 'क्या', etc.).
- If the speaker speaks in Hindi, write it in Romanized Hindi / Hinglish using the English alphabet (e.g., "Namaste dosto, kaise hain aap sab", "Yeh bohot hi accha tareeka hai").
- If the speaker speaks in English, transcribe in English.
- If the speaker speaks mixed Hindi & English, write everything in English/Latin letters (Hinglish).

Output ONLY a valid, strictly formatted SRT subtitle file with accurate timestamps.
Rules you MUST follow:
1. ONLY English/Latin letters, digits, and standard punctuation. Strictly ZERO Devanagari characters.
2. Do NOT include any markdown code fences (no ```srt or ``` wrappers).
3. Do NOT include any explanations, comments, or intro/outro text.
4. Each subtitle entry must follow this exact structure:
   <sequence_number>
   <HH:MM:SS,mmm> --> <HH:MM:SS,mmm>
   <subtitle text in English/Hinglish Latin letters>
   <blank line>
5. Timestamps must be monotonically increasing and must not overlap.
6. Keep each subtitle line to a maximum of 42 characters for readability.
7. Start sequence numbering at 1.
"""


def transcribe(wav_path: str, srt_path: str) -> None:
    """
    Generate an SRT subtitle file from *wav_path* using the Gemini API.

    Args:
        wav_path: Absolute path to the cleaned mono WAV file.
        srt_path: Absolute path where the SRT file will be written.

    Raises:
        ValueError: If the Gemini response does not contain valid SRT content.
        google.genai.errors.APIError: On Gemini API failures.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    # ------------------------------------------------------------------
    # 1. Upload WAV to Gemini File API
    # ------------------------------------------------------------------
    print("[transcriber] Uploading audio to Gemini File API …")
    uploaded_file = client.files.upload(
        file=wav_path,
        config=types.UploadFileConfig(mime_type="audio/wav"),
    )

    # Wait until the file is in ACTIVE state (usually immediate for WAV)
    max_wait = 60  # seconds
    waited = 0
    while uploaded_file.state.name != "ACTIVE":
        if waited >= max_wait:
            raise TimeoutError(
                f"Gemini file did not become ACTIVE within {max_wait}s. "
                f"Current state: {uploaded_file.state.name}"
            )
        time.sleep(2)
        waited += 2
        uploaded_file = client.files.get(name=uploaded_file.name)

    print(f"[transcriber] File ready: {uploaded_file.name}")

    # ------------------------------------------------------------------
    # 2. Generate SRT via Gemini (with automatic fallback on 503/404)
    # ------------------------------------------------------------------
    candidate_models = [GEMINI_MODEL]
    for backup in ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]:
        if backup not in candidate_models:
            candidate_models.append(backup)

    raw_text: str = ""
    last_err: Exception | None = None
    try:
        for model_name in candidate_models:
            try:
                print(f"[transcriber] Generating subtitles with {model_name} …")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[_SRT_PROMPT, uploaded_file],
                )
                if response.text:
                    raw_text = response.text
                    print(f"[transcriber] Subtitles successfully generated using {model_name}")
                    break
            except Exception as err:
                print(f"[transcriber] Model {model_name} encountered an issue: {err}")
                last_err = err
                continue

        if not raw_text:
            raise RuntimeError(
                f"All Gemini subtitle generation attempts failed. Last error: {last_err}"
            )
    finally:
        # ------------------------------------------------------------------
        # 3. Always delete the remote file to free quota
        # ------------------------------------------------------------------
        try:
            client.files.delete(name=uploaded_file.name)
            print("[transcriber] Remote file deleted.")
        except Exception as del_err:
            print(f"[transcriber] Warning: could not delete remote file: {del_err}")

    # ------------------------------------------------------------------
    # 4. Clean up any accidental markdown fences
    # ------------------------------------------------------------------
    cleaned = re.sub(r"```(?:srt)?\s*", "", raw_text, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    # ------------------------------------------------------------------
    # 5. Validate SRT structure
    # ------------------------------------------------------------------
    if "-->" not in cleaned:
        raise ValueError(
            "Gemini did not return a valid SRT file. "
            f"Response preview: {cleaned[:300]!r}"
        )

    # ------------------------------------------------------------------
    # 6. Write SRT file
    # ------------------------------------------------------------------
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(cleaned)

    print(f"[transcriber] SRT saved to: {srt_path}")
