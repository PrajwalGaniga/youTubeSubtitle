# YT-sub Studio (v3) — Complete UI & Pipeline Feature Specification
*Prajwal's Personal YouTube Creator Studio & AI Video Production Toolkit*

---

## 1. Studio Identity & Personal Branding
* **Personal Creator Badge:** Displays `"Prajwal's Studio • YT·sub v3.0"` with a glowing dual-tone logo.
* **Studio Navigation Bar:**
  - `Studio`: Primary workspace (Upload, Live Processing, Step-by-Step workstation, Results).
  - `Projects`: Creator project history with quick re-open and download buttons.
  - `Settings`: Live system health dashboard (Gemini AI status, FFmpeg runtime, RNNoise models, disk space, 300 MB upload limit).
* **Live System Status Chip:** Real-time green/red dot showing Gemini API connectivity (`Gemini ● ok`) and FFmpeg health.

---

## 2. 300 MB Upload & Live Preview Workspace
* **300 MB Upload Limit:** Upgraded from 50 MB to 300 MB.
* **Streaming Disk Ingestion:** Uploads stream in 1 MB chunks directly to isolated job directories (`jobs/{job_id}/`), completely eliminating RAM bloat and HTTP request timeouts.
* **Real-Time Upload Progress Bar:** Powered by `XMLHttpRequest.upload.onprogress` displaying real-time percentage (`0-100%`), loaded MB / total MB, and transfer speed in MB/s (`14.2 MB/s`).
* **Live Video Preview with Instant Caption Overlay:**
  - Selecting any video renders a live HTML5 player preview.
  - Dynamically overlays active style preset typography on sample speech lines (`MAKE MONEY`, `SECRET TRICK`, `INSANE RESULT`, etc.).
  - Adjusting presets, highlight colors, position, or font size instantly updates the live preview on the user's video before processing!
* **Auto-Probing Metadata Chips:**
  - Displays detected pixel geometry (e.g. `1080×1920` or `1920×1080`).
  - Automatic aspect ratio detection (`9:16 Shorts` or `16:9 YouTube Landscape`).
  - File size and duration formatted chips with a quick "Replace Video" button.

---

## 3. Two Modes of Operation
1. **⚡ 1-Click Auto-Pilot:** Automates all 5 stages end-to-end without stopping.
2. **🛠️ Step-by-Step Studio Workflow (Interactive Creator Workstation):**
   - **Step 1: Extract Audio:**
     - Pulls raw 48 kHz 16-bit mono PCM audio track.
     - Pauses and lets the creator listen to raw audio in the browser.
     - Direct button: `⬇ Download Raw Audio (.wav)`.
     - Choice A: `🎙️ Use Built-in Neural AI Enhancer` (RNNoise GRU + Broadcast DSP).
     - Choice B: `⬆ Import External Enhanced Audio` (upload an enhanced track from Adobe Podcast, ElevenLabs, Audacity, or clean studio mic to replace the video's audio!).
   - **Step 2: Voice Enhancement:**
     - Pauses after cleaning so the creator can listen and compare the audio.
     - Direct button: `⬇ Download Cleaned Audio (.wav)`.
     - Next button: `✨ Proceed to Transcription`.
   - **Step 3: AI Transcription (Gemini):**
     - Generates Romanized English/Hinglish subtitles.
     - Displays an editable transcript table/text area where the creator can review and tweak any words!
     - Direct button: `⬇ Download Subtitles (.srt)`.
     - Next button: `🎨 Burn Subtitles Into Video`.
   - **Step 4: Subtitle Burn-in:**
     - Renders pixel-exact kinetic ASS subtitles matching native video resolution without aspect distortion.
   - **Step 5: Background Music & Final Preview:**
     - Allows uploading a background music track (`.mp3` / `.wav`), setting volume ducking (5% to 40%), and mixing into the final video!
     - Live synchronized preview before downloading.

---

## 4. Live Background Processing View (§4)
* **5-Stage Pipeline Timeline Strip:**
  1. `[Extract Audio]`: Pulls 48 kHz PCM track.
  2. `[Enhance Voice]`: RNNoise neural denoiser + Studio vocal EQ + EBU R128 loudness normalization.
  3. `[Transcribe Speech]`: Gemini AI speech engine with multi-model fallback & retry backoff.
  4. `[Burn Viral Captions]`: Native libass subtitle rendering.
  5. `[Package Downloads]`: Bundles all exports, transcripts, and ZIP archive.
* **"Now" Stage Card:** Displays stage name, plain-English summary, and percentage progress bar.
* **Live Terminal Log Panel:**
  - Auto-scrolls with live timestamps, stage tags, and status messages.
  - "Technical Details" toggle for inspecting raw FFmpeg / Gemini strings.
  - `[ Copy Log ]` button for instant copying.
* **Real Job Cancellation:** `[ Cancel Job ]` button gracefully terminates background FFmpeg processes and marks the job cancelled.

---

## 5. Result & Review View (§5)
* **Synced Dual Video Player:**
  - Side-by-side players (Original Video vs Cleaned + Subtitled Video).
  - Single synced scrubber bar (scrubbing either video scrubs both simultaneously).
  - Responsive layout (sleek portrait frames for 9:16 Shorts, wide layout for 16:9).
* **A/B Audio Toggle Button:**
  - Switch between hearing original raw camera audio and cleaned studio voice instantly with zero playback position jump!
* **Optional Background Music Mixing:**
  - Upload an MP3/WAV music file, adjust volume slider (5% to 40% with smart vocal ducking), and click `Mix & Update Video`!
* **What We Did Report Cards:**
  - Voice: Measured loudness before/after (-24.0 -> -16.0 LUFS), mode, noise gate status.
  - Captions: Word count, line count, style preset, language.
  - Video: Input/output resolution, codec, aspect ratio confirmation.
  - Time: Duration per stage and total processing time.
* **Multi-Asset Export Downloads:**
  - `Final Video (.mp4)`: Rendered video with burned subtitles + clean voice + optional music.
  - `Cleaned Audio (.wav)`: 48 kHz broadcast audio track.
  - `Original Audio (.wav)`: Raw extracted audio track.
  - `Subtitles (.srt)`: Standard SRT captions for YouTube upload.
  - `Styled Captions (.ass)`: Advanced SubStation Alpha styled captions.
  - `Transcript (.txt)`: Plain text transcript for video descriptions/notes.
  - `Complete Bundle (.zip)`: 1-click ZIP archive containing all project files.
  - `Diagnostics (.json)`: Full job metadata and timing breakdown.

---

## 6. Plain-English Error Taxonomy & Failure Report (§7 & §8)
When an issue occurs, the system presents a structured diagnostic report:
* **Failed Stage Indicator:** Visual red ✕ on the timeline strip.
* **Plain-English Explanation:** What happened, why it happened, and actionable fix.
* **"Your Work is Safe" Notice:** Informs the user that completed stages (such as raw and clean audio) are preserved.
* **Retry from Failed Stage:** One-click retry that resumes directly from the failed stage without re-doing earlier work!
* **Collapsible Technical Drawer:** Full error code, module name, and downloadable `diagnostics.json` for Prajwal.

---

## 7. Projects & Settings Views
* **Projects Tab:** History of all past jobs with status badges, video metadata, and instant download/open buttons.
* **Settings Tab:** Real-time health indicators for Gemini AI, FFmpeg version and path, neural models, free disk space, and 300 MB limit.
