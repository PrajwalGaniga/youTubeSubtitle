// errorCopy.js — User-friendly error taxonomy and troubleshooting guides for YT-sub Studio

export const ERROR_MAP = {
  GEMINI_429: {
    title: 'AI Transcription Busy',
    what: "Google's Gemini speech service is temporarily experiencing high server demand or rate limits.",
    fix: 'Wait 20–30 seconds and click Retry. Your cleaned audio is already saved so it will resume directly from transcription.',
    retryable: true,
  },
  GEMINI_503: {
    title: 'AI Transcription Service Unavailable',
    what: "Google's speech servers temporarily failed to respond after multiple automatic retries.",
    fix: 'Wait ~30 seconds and click "Retry from Transcribe". Audio cleaning will not be repeated.',
    retryable: true,
  },
  GEMINI_KEY_INVALID: {
    title: 'Gemini API Key Issue',
    what: 'The GEMINI_API_KEY in backend/.env is either missing, expired, or unauthorized.',
    fix: 'Check backend/.env to ensure your key is valid from Google AI Studio, then restart the backend.',
    retryable: false,
  },
  NO_SPEECH: {
    title: 'No Clear Speech Detected',
    what: 'The audio track was silent or speaking volume was too quiet for AI recognition.',
    fix: 'Ensure your video contains audible spoken dialogue in English or Hindi.',
    retryable: false,
  },
  FILE_TOO_LARGE: {
    title: 'File Exceeds 300 MB Limit',
    what: 'The uploaded video file is larger than the 300 MB maximum threshold.',
    fix: 'Trim or compress your video clip slightly before uploading.',
    retryable: false,
  },
  BAD_FORMAT: {
    title: 'Unsupported Video Format',
    what: 'The uploaded file is not a valid H.264/AAC MP4 container.',
    fix: 'Re-export your video as standard MP4 (H.264 video, AAC audio).',
    retryable: false,
  },
  FFMPEG_BURN: {
    title: 'Caption Rendering Glitch',
    what: 'FFmpeg encountered an issue reading frames or applying font glyphs during subtitle burn-in.',
    fix: 'Ensure your video has standard even pixel dimensions (e.g. 1080x1920), or try another preset style.',
    retryable: true,
  },
  FFMPEG_ENHANCE: {
    title: 'Voice Enhancement Filter Error',
    what: 'The neural audio filter chain encountered unexpected stream parameters.',
    fix: 'Try retrying with "Natural Clean" or "Original Audio" mode.',
    retryable: true,
  },
  UPLOAD_INTERRUPTED: {
    title: 'Upload Dropped',
    what: 'The network connection was interrupted mid-upload.',
    fix: 'Check your connection and upload the video again.',
    retryable: true,
  },
  CANCELLED: {
    title: 'Job Cancelled',
    what: 'The job was stopped by user request.',
    fix: 'Start a new job or re-upload when ready.',
    retryable: false,
  },
  UNKNOWN: {
    title: 'Unexpected Processing Error',
    what: 'An unhandled pipeline error occurred during processing.',
    fix: 'Copy the diagnostic log below or check backend terminal output for details.',
    retryable: true,
  },
}

export function getErrorDetails(errorCode, fallbackMessage) {
  const code = (errorCode || 'UNKNOWN').toUpperCase()
  const match = ERROR_MAP[code] || ERROR_MAP.UNKNOWN
  return {
    code: code,
    title: match.title,
    what: match.what,
    fix: match.fix,
    retryable: match.retryable,
    raw: fallbackMessage || '',
  }
}
