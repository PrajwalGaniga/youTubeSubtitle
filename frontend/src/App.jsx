import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock,
  Copy,
  Download,
  FastForward,
  Film,
  FolderOpen,
  Headphones,
  Maximize2,
  Music,
  Palette,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Settings,
  Sliders,
  Sparkles,
  Trash2,
  Type,
  Upload,
  Volume2,
  VolumeX,
  Wand2,
  X,
  XCircle,
  Zap,
} from 'lucide-react'
import styles from './App.module.css'
import { getErrorDetails } from './errorCopy'

// ---------------------------------------------------------------------------
// Constants & Presets
// ---------------------------------------------------------------------------
const MAX_UPLOAD_MB = 300
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

const PRESET_OPTIONS = [
  {
    id: 'hormozi-yellow',
    name: 'Hormozi Impact',
    tag: 'Finance & Viral',
    fontClass: styles.fontAnton,
    lead: 'MAKE',
    highlight: 'MONEY',
    defaultColor: '#FFE600',
  },
  {
    id: 'tiktok-box',
    name: 'TikTok Box',
    tag: 'Reels / Shorts',
    fontClass: styles.fontInterBox,
    lead: 'SECRET',
    highlight: 'TRICK',
    defaultColor: '#00F0FF',
  },
  {
    id: 'mrbeast-green',
    name: 'MrBeast Hype',
    tag: 'Entertainment',
    fontClass: styles.fontLuckiestGuy,
    lead: 'INSANE',
    highlight: 'RESULT',
    defaultColor: '#00FF66',
  },
  {
    id: 'cyber-neon',
    name: 'Cyber Neon',
    tag: 'Tech & Gaming',
    fontClass: styles.fontOrbitron,
    lead: 'FUTURE',
    highlight: 'LEVEL',
    defaultColor: '#FF0055',
  },
  {
    id: 'minimal-apple',
    name: 'Minimal Apple',
    tag: 'Aesthetic / Vlogs',
    fontClass: styles.fontMinimal,
    lead: 'Simple.',
    highlight: 'Powerful.',
    defaultColor: '#FFFFFF',
  },
  {
    id: 'comic-bold',
    name: 'Comic Pop',
    tag: 'Commentary',
    fontClass: styles.fontBangers,
    lead: 'WAIT',
    highlight: 'WHAT?!',
    defaultColor: '#FF3B30',
  },
  {
    id: 'veed-impact',
    name: 'VEED Hero Box',
    tag: 'Hero Impact',
    fontClass: styles.fontAnton,
    lead: 'THE',
    highlight: 'TRUTH',
    defaultColor: '#FF1E1E',
  },
  {
    id: 'no-subs',
    name: 'No Subtitles',
    tag: 'Audio Clean Only',
    fontClass: styles.fontMinimal,
    lead: 'CLEAN',
    highlight: 'AUDIO',
    defaultColor: '#38BDF8',
    isAudioOnly: true,
  },
]

const COLOR_SWATCHES = ['#FFE600', '#00F0FF', '#00FF66', '#FF3B30', '#A855F7', '#FFFFFF', '#FF0055']

function fmtSize(bytes) {
  if (!bytes) return '0 MB'
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function fmtSec(sec) {
  if (!sec) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatIST(isoString) {
  if (!isoString) return ''
  try {
    const d = new Date(isoString)
    if (isNaN(d.getTime())) return isoString
    return (
      d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
      }) + ' IST'
    )
  } catch {
    return isoString
  }
}

/**
 * Prompts user with native OS "Save As" file dialog (asking folder location and filename),
 * then writes the file stream directly into that chosen location.
 * Falls back to standard anchor download if API unavailable.
 */
async function downloadWithSavePicker(downloadUrl, defaultFileName, prePickedHandle = null) {
  if (prePickedHandle) {
    try {
      const res = await fetch(downloadUrl)
      if (!res.ok) throw new Error(`Download failed (${res.status})`)
      const writable = await prePickedHandle.createWritable()
      if (res.body && typeof res.body.pipeTo === 'function') {
        await res.body.pipeTo(writable)
      } else {
        const blob = await res.blob()
        await writable.write(blob)
        await writable.close()
      }
      return { success: true, method: 'picker' }
    } catch (err) {
      console.warn('Writing to prePickedHandle failed, falling back:', err)
    }
  }

  if (typeof window !== 'undefined' && 'showSaveFilePicker' in window && !prePickedHandle) {
    try {
      const ext = defaultFileName.includes('.') ? '.' + defaultFileName.split('.').pop() : '.mp4'
      const handle = await window.showSaveFilePicker({
        suggestedName: defaultFileName,
        types: [
          {
            description: defaultFileName.endsWith('.mp4') ? 'MP4 Video' : 'File Asset',
            accept: {
              'video/mp4': ['.mp4'],
            },
          },
        ],
      })
      const res = await fetch(downloadUrl)
      if (!res.ok) throw new Error(`Download failed (${res.status})`)
      const writable = await handle.createWritable()
      if (res.body && typeof res.body.pipeTo === 'function') {
        await res.body.pipeTo(writable)
      } else {
        const blob = await res.blob()
        await writable.write(blob)
        await writable.close()
      }
      return { success: true, method: 'picker' }
    } catch (err) {
      if (err.name === 'AbortError') {
        return { cancelled: true }
      }
      console.warn('showSaveFilePicker failed, falling back:', err)
    }
  }

  // Fallback anchor
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = defaultFileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  return { success: true, method: 'fallback' }
}

// ---------------------------------------------------------------------------
// Main Application Component
// ---------------------------------------------------------------------------
export default function App() {
  const [activeTab, setActiveTab] = useState('studio') // studio | projects | settings
  const [health, setHealth] = useState(null)

  // Current active job state
  const [activeJobId, setActiveJobId] = useState(null)
  const [job, setJob] = useState(null)
  const [projects, setProjects] = useState([])

  // Setup / Upload states
  const [selectedFile, setSelectedFile] = useState(null)
  const [videoSrc, setVideoSrc] = useState(null)
  const [videoMeta, setVideoMeta] = useState(null) // { width, height, duration, orientation }
  const [isDragging, setIsDragging] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null) // { pct, loadedMb, totalMb, speedMb }
  const [setupError, setSetupError] = useState('')

  // Styling & Options
  const [selectedPreset, setSelectedPreset] = useState('hormozi-yellow')
  const [autoPilot, setAutoPilot] = useState(true)
  const [voiceMode, setVoiceMode] = useState('studio')
  const [position, setPosition] = useState('default')
  const [customColor, setCustomColor] = useState('')
  const [sizeScale, setSizeScale] = useState(1.0)
  const [isUppercase, setIsUppercase] = useState(true)
  const [popAnim, setPopAnim] = useState(true)
  const [showCustomize, setShowCustomize] = useState(false)

  // Live Processing & Log States
  const [showTechnicalLog, setShowTechnicalLog] = useState(false)
  const [copiedLog, setCopiedLog] = useState(false)
  const [audioImportFile, setAudioImportFile] = useState(null)
  const [musicFile, setMusicFile] = useState(null)
  const [musicVol, setMusicVol] = useState(0.15)
  const [isSubmittingMusic, setIsSubmittingMusic] = useState(false)

  // Subtitle Editor state (when paused at transcribe)
  const [editableSrt, setEditableSrt] = useState('')

  // Download Format Pop-up Modal State
  const [isFormatModalOpen, setIsFormatModalOpen] = useState(false)
  const [formatModalJob, setFormatModalJob] = useState(null)
  const [isReformatting, setIsReformatting] = useState(false)
  const [reformattingFormat, setReformattingFormat] = useState(null)
  const [reformatError, setReformatError] = useState('')

  // Save Destination & Folder Selection
  const [saveMode, setSaveMode] = useState(() => localStorage.getItem('ytsub_save_mode') || 'ask') // 'ask' | 'folder'
  const [customFolderPath, setCustomFolderPath] = useState(() => localStorage.getItem('ytsub_export_folder') || '')
  const [commonFolders, setCommonFolders] = useState({})
  const [exportSuccessInfo, setExportSuccessInfo] = useState(null)
  const [copiedSavedPath, setCopiedSavedPath] = useState(false)

  // Synced Player & A/B Audio State
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [audioChannel, setAudioChannel] = useState('processed') // 'original' | 'processed'

  const videoPlayerOriginalRef = useRef(null)
  const videoPlayerProcessedRef = useRef(null)
  const logEndRef = useRef(null)

  // ---------------------------------------------------------------------------
  // Health check on mount
  // ---------------------------------------------------------------------------
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/health')
      if (res.ok) setHealth(await res.json())
    } catch {
      // Degraded or offline
    }
  }, [])

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch('/api/jobs')
      if (res.ok) setProjects(await res.json())
    } catch {
      // Ignore
    }
  }, [])

  useEffect(() => {
    const savedJobId = localStorage.getItem('ytsub_active_job')
    if (savedJobId) {
      setActiveJobId(savedJobId)
    }
    fetchHealth()
    fetchProjects()

    // Fetch common system folders for quick export destination selection
    fetch('/api/system/common-folders')
      .then((r) => r.json())
      .then((data) => {
        if (data?.folders) {
          setCommonFolders(data.folders)
          if (!localStorage.getItem('ytsub_export_folder')) {
            const defPath = data.folders.videos || data.folders.desktop || ''
            if (defPath) {
              setCustomFolderPath(defPath)
              localStorage.setItem('ytsub_export_folder', defPath)
            }
          }
        }
      })
      .catch(() => {})
    const timer = setInterval(() => {
      fetchHealth()
      fetchProjects()
    }, 4000)
    return () => clearInterval(timer)
  }, [fetchHealth, fetchProjects])

  // ---------------------------------------------------------------------------
  // SSE Event Stream & Polling fallback for activeJobId
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!activeJobId) return

    let eventSource = null
    let pollInterval = null
    let isCancelled = false

    const fetchSnapshot = async () => {
      try {
        const res = await fetch(`/api/jobs/${activeJobId}`)
        if (res.status === 404) {
          // Job does not exist on server (deleted or invalid)
          console.warn(`Job ${activeJobId} not found on server (404). Clearing active job.`)
          localStorage.removeItem('ytsub_active_job')
          if (eventSource) eventSource.close()
          if (pollInterval) clearInterval(pollInterval)
          setActiveJobId(null)
          setJob(null)
          return
        }
        if (res.ok) {
          const data = await res.json()
          if (!isCancelled) {
            setJob(data)
            // If paused at transcribe and we don't have editableSrt yet, fetch SRT
            if (data.step_action === 'awaiting_burn_proceed') {
              try {
                const srtRes = await fetch(`/api/jobs/${activeJobId}/files/captions.srt`)
                if (srtRes.ok) setEditableSrt(await srtRes.text())
              } catch {
                // Ignore
              }
            }
          }
        }
      } catch {
        // Polling error
      }
    }

    fetchSnapshot()

    // Connect to Server-Sent Events
    try {
      eventSource = new EventSource(`/api/jobs/${activeJobId}/events`)
      eventSource.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'deleted') {
            localStorage.removeItem('ytsub_active_job')
            if (eventSource) eventSource.close()
            if (pollInterval) clearInterval(pollInterval)
            setActiveJobId(null)
            setJob(null)
            return
          }
          if (msg.type === 'snapshot') {
            setJob(msg.job)
          } else {
            // Re-fetch snapshot on any update to stay completely in sync
            fetchSnapshot()
          }
        } catch {
          // Ignore
        }
      }
      eventSource.onerror = () => {
        if (eventSource) eventSource.close()
        // Fallback polling only if not already active
        if (!pollInterval && !isCancelled) {
          pollInterval = setInterval(fetchSnapshot, 3000)
        }
      }
    } catch {
      if (!pollInterval && !isCancelled) {
        pollInterval = setInterval(fetchSnapshot, 3000)
      }
    }

    return () => {
      isCancelled = true
      if (eventSource) eventSource.close()
      if (pollInterval) clearInterval(pollInterval)
    }
  }, [activeJobId])

  // Scroll log to bottom on updates
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [job?.logs])

  // ---------------------------------------------------------------------------
  // File Validation & Preview Loading
  // ---------------------------------------------------------------------------
  const handleFileSelect = useCallback((file) => {
    if (!file) return
    setSetupError('')

    if (!file.name.toLowerCase().endsWith('.mp4')) {
      setSetupError('Only .mp4 video files are supported.')
      return
    }

    if (file.size > MAX_UPLOAD_BYTES) {
      setSetupError(`File is ${fmtSize(file.size)}. Limit is ${MAX_UPLOAD_MB} MB. Please compress or trim it.`)
      return
    }

    if (videoSrc) URL.revokeObjectURL(videoSrc)

    const url = URL.createObjectURL(file)
    setSelectedFile(file)
    setVideoSrc(url)

    // Probe metadata via temporary video element
    const tempV = document.createElement('video')
    tempV.src = url
    tempV.onloadedmetadata = () => {
      const w = tempV.videoWidth
      const h = tempV.videoHeight
      const dur = tempV.duration
      setVideoMeta({
        width: w,
        height: h,
        duration: dur,
        orientation: h > w ? 'portrait' : 'landscape',
      })
    }
  }, [videoSrc])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files?.[0]) {
      handleFileSelect(e.dataTransfer.files[0])
    }
  }, [handleFileSelect])

  // ---------------------------------------------------------------------------
  // Upload with Real XHR Progress (Streaming to FastAPI)
  // ---------------------------------------------------------------------------
  const handleStartProcessing = useCallback(() => {
    if (!selectedFile) return
    setSetupError('')

    const formData = new FormData()
    formData.append('file', selectedFile)
    formData.append('preset_id', selectedPreset)
    formData.append('voice_mode', voiceMode)
    formData.append('position', position)
    if (customColor) formData.append('highlight_color', customColor)
    formData.append('size_scale', sizeScale.toString())
    formData.append('uppercase', isUppercase.toString())
    formData.append('pop_anim', popAnim.toString())
    formData.append('auto_pilot', autoPilot.toString())

    const xhr = new XMLHttpRequest()
    const startTime = Date.now()

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100)
        const loadedMb = (e.loaded / (1024 * 1024)).toFixed(1)
        const totalMb = (e.total / (1024 * 1024)).toFixed(1)
        const elapsedSec = (Date.now() - startTime) / 1000
        const speedMb = elapsedSec > 0 ? (loadedMb / elapsedSec).toFixed(1) : '0'

        setUploadProgress({
          pct,
          loadedMb,
          totalMb,
          speedMb,
        })
      }
    }

    xhr.onload = () => {
      setUploadProgress(null)
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText)
          const newJobId = res.job_id
          localStorage.setItem('ytsub_active_job', newJobId)
          setActiveJobId(newJobId)
          // Optimistically populate job state so View 2 renders IMMEDIATELY with zero lag
          setJob({
            job_id: newJobId,
            status: 'running',
            step_action: 'none',
            input: {
              name: selectedFile.name,
              size_mb: parseFloat((selectedFile.size / (1024 * 1024)).toFixed(1)),
              width: videoMeta?.width || 1280,
              height: videoMeta?.height || 720,
              duration_s: videoMeta?.duration || 0,
              orientation: videoMeta?.orientation || 'landscape',
            },
            options: {
              preset: selectedPreset,
              voice: voiceMode,
              position: position,
              highlight_color: customColor || null,
              size_scale: sizeScale,
              uppercase: isUppercase,
              pop_anim: popAnim,
              auto_pilot: autoPilot,
            },
            stages: [
              { key: 'extract', label: 'Extract Audio', status: 'running', progress: 20, message: 'Extracting 48 kHz mono track...' },
              { key: 'enhance', label: 'Enhance Voice', status: 'pending', progress: 0, message: 'Ready' },
              { key: 'transcribe', label: 'Transcribe Speech', status: 'pending', progress: 0, message: 'Waiting' },
              { key: 'burn', label: 'Burn Viral Captions', status: 'pending', progress: 0, message: 'Waiting' },
              { key: 'package', label: 'Package Downloads', status: 'pending', progress: 0, message: 'Waiting' },
            ],
            metrics: {},
            logs: [
              { time: new Date().toLocaleTimeString(), stage: 'upload', level: 'info', message: `Video uploaded (${(selectedFile.size / (1024 * 1024)).toFixed(1)} MB). Studio pipeline initialized.` },
            ],
            files: [],
          })
          fetchProjects()
        } catch {
          setSetupError('Server returned invalid response.')
        }
      } else {
        try {
          const errData = JSON.parse(xhr.responseText)
          setSetupError(errData.detail || `Upload error (${xhr.status})`)
        } catch {
          setSetupError(`Upload failed with status ${xhr.status}`)
        }
      }
    }

    xhr.onerror = () => {
      setUploadProgress(null)
      setSetupError('Network error during upload. Please check connection and retry.')
    }

    xhr.open('POST', '/api/jobs')
    xhr.send(formData)
  }, [selectedFile, selectedPreset, voiceMode, position, customColor, sizeScale, isUppercase, popAnim, autoPilot])

  // ---------------------------------------------------------------------------
  // Step-by-Step Actions
  // ---------------------------------------------------------------------------
  const handleResumeStep = async (targetStage) => {
    if (!activeJobId) return
    const formData = new FormData()
    if (targetStage) formData.append('target_stage', targetStage)
    await fetch(`/api/jobs/${activeJobId}/resume`, {
      method: 'POST',
      body: formData,
    })
  }

  const handleImportAudio = async () => {
    if (!activeJobId || !audioImportFile) return
    const formData = new FormData()
    formData.append('file', audioImportFile)
    const res = await fetch(`/api/jobs/${activeJobId}/import-audio`, {
      method: 'POST',
      body: formData,
    })
    if (res.ok) {
      setAudioImportFile(null)
      // Resume to transcribe
      handleResumeStep('transcribe')
    }
  }

  const handleMixMusic = async () => {
    if (!activeJobId || !musicFile) return
    setIsSubmittingMusic(true)
    const formData = new FormData()
    formData.append('file', musicFile)
    formData.append('volume', musicVol.toString())
    try {
      await fetch(`/api/jobs/${activeJobId}/music`, {
        method: 'POST',
        body: formData,
      })
      setMusicFile(null)
    } finally {
      setIsSubmittingMusic(false)
    }
  }

  const handleReburnWithEdits = async () => {
    if (!activeJobId) return
    const formData = new FormData()
    if (editableSrt) formData.append('srt_text', editableSrt)
    formData.append('preset_id', selectedPreset)
    await fetch(`/api/jobs/${activeJobId}/reburn`, {
      method: 'POST',
      body: formData,
    })
  }

  const handleRetryJob = async () => {
    if (!activeJobId) return
    await fetch(`/api/jobs/${activeJobId}/retry`, { method: 'POST' })
  }

  const handleCancelJob = async () => {
    if (!activeJobId) return
    if (window.confirm('Are you sure you want to cancel processing?')) {
      await fetch(`/api/jobs/${activeJobId}/cancel`, { method: 'POST' })
    }
  }

  const handleReset = () => {
    if (videoSrc) URL.revokeObjectURL(videoSrc)
    setSelectedFile(null)
    setVideoSrc(null)
    setVideoMeta(null)
    setActiveJobId(null)
    setJob(null)
    setUploadProgress(null)
    setSetupError('')
    localStorage.removeItem('ytsub_active_job')
  }

  const handleDeleteProject = async (jobId, projectName, e) => {
    if (e) e.stopPropagation()
    const confirmMsg = projectName
      ? `Permanently delete project "${projectName}"? This will delete all video, audio, and subtitle files from disk.`
      : 'Permanently delete this project from disk?'
    if (!window.confirm(confirmMsg)) return

    try {
      const res = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' })
      if (res.ok) {
        setProjects((prev) => prev.filter((p) => p.job_id !== jobId))
        if (activeJobId === jobId) {
          handleReset()
        }
      } else {
        alert('Failed to delete project.')
      }
    } catch (err) {
      alert(`Error deleting project: ${err.message}`)
    }
  }

  const handleClearAllProjects = async () => {
    if (projects.length === 0) return
    if (
      !window.confirm(
        `Permanently delete ALL ${projects.length} projects? This will purge all stored video and audio files from disk.`
      )
    )
      return

    try {
      const res = await fetch('/api/jobs', { method: 'DELETE' })
      if (res.ok) {
        setProjects([])
        handleReset()
      } else {
        alert('Failed to clear projects.')
      }
    } catch (err) {
      alert(`Error clearing projects: ${err.message}`)
    }
  }

  const copyLogText = () => {
    if (!job?.logs) return
    const text = job.logs.map((l) => `[${l.time}] [${l.stage}] ${l.message} ${l.raw || ''}`).join('\n')
    navigator.clipboard.writeText(text)
    setCopiedLog(true)
    setTimeout(() => setCopiedLog(false), 2000)
  }

  // ---------------------------------------------------------------------------
  // Synced Player Controls
  // ---------------------------------------------------------------------------
  const togglePlay = () => {
    const v1 = videoPlayerOriginalRef.current
    const v2 = videoPlayerProcessedRef.current
    if (isPlaying) {
      if (v1) v1.pause()
      if (v2) v2.pause()
      setIsPlaying(false)
    } else {
      if (v1) v1.play()
      if (v2) v2.play()
      setIsPlaying(true)
    }
  }

  const handleSeek = (e) => {
    const t = parseFloat(e.target.value)
    setCurrentTime(t)
    if (videoPlayerOriginalRef.current) videoPlayerOriginalRef.current.currentTime = t
    if (videoPlayerProcessedRef.current) videoPlayerProcessedRef.current.currentTime = t
  }

  const handleTimeUpdate = (e) => {
    setCurrentTime(e.target.currentTime)
    if (e.target.duration && !duration) {
      setDuration(e.target.duration)
    }
  }

  // ---------------------------------------------------------------------------
  // Aspect Ratio Export & Download Modal Handlers
  // ---------------------------------------------------------------------------
  const openFormatModal = (targetJob = null) => {
    setFormatModalJob(targetJob || job)
    setIsFormatModalOpen(true)
    setReformatError('')
    setExportSuccessInfo(null)
  }

  const closeFormatModal = () => {
    if (isReformatting) return
    setIsFormatModalOpen(false)
    setFormatModalJob(null)
    setReformatError('')
    setExportSuccessInfo(null)
  }

  const handleOpenExplorer = async (path) => {
    if (!path) return
    try {
      await fetch('/api/system/open-explorer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
    } catch (err) {
      console.error('Failed to open explorer:', err)
    }
  }

  const handleExportAndDownload = async (targetAspect, mode) => {
    const j = formatModalJob || job
    if (!j) return
    const jobId = j.job_id
    const baseName = j.input?.name ? j.input.name.replace(/\.[^/.]+$/, '') : 'video'
    const aspectSlug = targetAspect === 'original' ? '' : `_${targetAspect.replace(':', '_')}_${mode}`
    const defaultFileName = `${baseName}_sub${aspectSlug}.mp4`

    setReformatError('')
    setExportSuccessInfo(null)

    // Option A: Save directly to user-specified local folder path on their PC
    if (saveMode === 'folder') {
      const targetFolder = (customFolderPath || '').trim()
      if (!targetFolder) {
        setReformatError('Please enter or select a destination folder path first.')
        return
      }

      setIsReformatting(true)
      setReformattingFormat(
        `${targetAspect === '9:16' ? 'YouTube Shorts (9:16)' : targetAspect === '16:9' ? 'Landscape (16:9)' : 'Original'} • Saving to ${targetFolder}...`
      )

      try {
        const formData = new FormData()
        formData.append('target_aspect', targetAspect)
        formData.append('mode', mode)
        formData.append('folder_path', targetFolder)
        formData.append('custom_filename', defaultFileName)

        const res = await fetch(`/api/jobs/${jobId}/save-to-folder`, {
          method: 'POST',
          body: formData,
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `Saving to folder failed (${res.status})`)
        }
        const data = await res.json()
        setExportSuccessInfo({
          full_path: data.full_path,
          folder_path: data.folder_path,
          filename: data.filename,
          size_mb: data.size_mb,
          method: 'folder',
        })
      } catch (err) {
        setReformatError(err.message || 'Export error')
      } finally {
        setIsReformatting(false)
        setReformattingFormat(null)
      }
      return
    }

    // Option B: Native OS "Save As" file picker (asks user which folder location and filename)
    let prePickedHandle = null
    if (typeof window !== 'undefined' && 'showSaveFilePicker' in window) {
      try {
        prePickedHandle = await window.showSaveFilePicker({
          suggestedName: defaultFileName,
          types: [
            {
              description: 'MP4 Video',
              accept: { 'video/mp4': ['.mp4'] },
            },
          ],
        })
      } catch (err) {
        if (err.name === 'AbortError') {
          // User cancelled the Save dialog
          return
        }
        console.warn('showSaveFilePicker prompt failed:', err)
      }
    }

    setIsReformatting(true)
    setReformattingFormat(
      `${targetAspect === '9:16' ? 'YouTube Shorts (9:16)' : 'Landscape (16:9)'} • ${
        mode === 'letterbox' ? 'Fit & Letterbox' : 'Center Crop'
      }`
    )

    try {
      let downloadUrl = `/api/jobs/${jobId}/files/final_video.mp4`

      if (targetAspect !== 'original') {
        const formData = new FormData()
        formData.append('target_aspect', targetAspect)
        formData.append('mode', mode)

        const res = await fetch(`/api/jobs/${jobId}/reformat`, {
          method: 'POST',
          body: formData,
        })

        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `Reformatting failed (${res.status})`)
        }

        const data = await res.json()
        downloadUrl = data.download_url
      }

      const saveResult = await downloadWithSavePicker(downloadUrl, defaultFileName, prePickedHandle)
      if (!saveResult.cancelled) {
        setExportSuccessInfo({
          filename: defaultFileName,
          method: 'picker',
        })
      }
    } catch (err) {
      setReformatError(err.message || 'Export error')
    } finally {
      setIsReformatting(false)
      setReformattingFormat(null)
    }
  }

  // Apply A/B audio toggle
  useEffect(() => {
    if (videoPlayerOriginalRef.current) {
      videoPlayerOriginalRef.current.muted = audioChannel !== 'original'
    }
    if (videoPlayerProcessedRef.current) {
      videoPlayerProcessedRef.current.muted = audioChannel !== 'processed'
    }
  }, [audioChannel])

  // Current active preset object
  const activePreset = PRESET_OPTIONS.find((p) => p.id === selectedPreset) || PRESET_OPTIONS[0]
  const currentHighlightColor = customColor || activePreset.defaultColor

  // Check if there is another running/paused job in background
  const activeRunningJob = projects.find(
    (p) => (p.status === 'running' || p.status === 'paused') && p.job_id !== activeJobId
  )

  // Caption overlay position class
  const posClass =
    position === 'center'
      ? styles.captionPosCenter
      : position === 'upper'
      ? styles.captionPosUpper
      : styles.captionPosBottom

  return (
    <div className={styles.root}>
      {/* ── Top Bar ── */}
      <header className={styles.topBar}>
        <div className={styles.brandGroup}>
          <div className={styles.logoWrap}>
            <Zap size={24} className={styles.logoIcon} />
            <span className={styles.logoText}>
              YT<span className={styles.logoDot}>·</span>sub
            </span>
          </div>
          <span className={styles.personalBadge}>Prajwal's Studio</span>
        </div>

        {/* Navigation Tabs */}
        <nav className={styles.navTabs}>
          <button
            type="button"
            className={`${styles.navTabBtn} ${activeTab === 'studio' ? styles.navTabActive : ''}`}
            onClick={() => setActiveTab('studio')}
          >
            <Film size={15} /> Studio
          </button>
          <button
            type="button"
            className={`${styles.navTabBtn} ${activeTab === 'projects' ? styles.navTabActive : ''}`}
            onClick={() => {
              setActiveTab('projects')
              fetchProjects()
            }}
          >
            <FolderOpen size={15} /> Projects
          </button>
          <button
            type="button"
            className={`${styles.navTabBtn} ${activeTab === 'settings' ? styles.navTabActive : ''}`}
            onClick={() => {
              setActiveTab('settings')
              fetchHealth()
            }}
          >
            <Settings size={15} /> Settings
          </button>
        </nav>

        {/* Status Chip & Avatar */}
        <div className={styles.topBarRight}>
          <div className={styles.healthChip} title="Gemini & FFmpeg Health Status">
            <span
              className={`${styles.statusDot} ${health?.status !== 'healthy' ? styles.statusDotError : ''}`}
            />
            <span>{health?.gemini?.configured ? 'Gemini ● ok' : 'API needed'}</span>
          </div>
          <div className={styles.userAvatar} title="Creator Profile">
            P
          </div>
        </div>
      </header>

      {/* ── Main Content Area ── */}
      <main className={styles.mainContent}>
        {/* ═══════════════════════════════════════════════════════════════════
            TAB 1: STUDIO (Upload, Live Process, Result, Failure)
           ═══════════════════════════════════════════════════════════════════ */}
        {activeTab === 'studio' && (
          <>
            {/* VIEW 1: SETUP & UPLOAD (When no job is running) */}
            {!activeJobId && (
              <>
                {/* Active Running Job Banner */}
                {activeRunningJob && (
                  <div className={styles.activeJobBanner}>
                    <div className={styles.activeJobBannerInfo}>
                      <span className={styles.bannerBadgePulse}>
                        <RefreshCw size={14} className={styles.spin} />
                        {activeRunningJob.status === 'paused' ? 'ACTION REQUIRED' : 'PROCESSING IN BACKGROUND'}
                      </span>
                      <div className={styles.bannerJobDetails}>
                        <strong>{activeRunningJob.name}</strong>
                        <span>
                          {activeRunningJob.status === 'paused'
                            ? '• Pipeline paused for user review (Cleaned audio ready)'
                            : `• Live AI studio pipeline running (${activeRunningJob.preset})`}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className={styles.bannerActionBtn}
                      onClick={() => {
                        setActiveJobId(activeRunningJob.job_id)
                        localStorage.setItem('ytsub_active_job', activeRunningJob.job_id)
                      }}
                    >
                      Open Live Studio Progress →
                    </button>
                  </div>
                )}

                <div className={styles.studioGrid}>
                {/* Left Column: Dropzone & Live Video Preview */}
                <div className={styles.previewCol}>
                  {!videoSrc ? (
                    <label
                      htmlFor="studioFileInput"
                      className={`${styles.dropzone} ${isDragging ? styles.dropzoneDragging : ''}`}
                      onDragOver={(e) => {
                        e.preventDefault()
                        setIsDragging(true)
                      }}
                      onDragLeave={() => setIsDragging(false)}
                      onDrop={onDrop}
                    >
                      <input
                        id="studioFileInput"
                        type="file"
                        accept="video/mp4,.mp4"
                        className={styles.fileInputHidden}
                        onChange={(e) => {
                          if (e.target.files?.[0]) handleFileSelect(e.target.files[0])
                          e.target.value = ''
                        }}
                      />
                      <div className={styles.dropzoneIconWrap}>
                        <Upload size={32} />
                      </div>
                      <h3 className={styles.dropzoneTitle}>Drop your MP4 video here</h3>
                      <p className={styles.dropzoneSubtitle}>
                        Up to 300 MB • 9:16 Shorts or 16:9 Landscape YouTube Video
                      </p>
                      <div className={styles.dropzonePills}>
                        <span className={styles.pill}>🎙️ Neural Voice Enhancement</span>
                        <span className={styles.pill}>⚡ Word-by-Word Kinetic Pop</span>
                        <span className={styles.pill}>📝 English / Hinglish</span>
                      </div>
                    </label>
                  ) : (
                    /* Live Video Preview Box with Real Subtitle Overlay */
                    <div className={styles.previewBox}>
                      <div className={styles.previewVideoWrap}>
                        <video
                          src={videoSrc}
                          controls
                          className={styles.previewVideoEl}
                        />
                        {/* Live Caption Sample Overlay */}
                        <div className={`${styles.previewCaptionOverlay} ${posClass}`}>
                          {selectedPreset === 'no-subs' ? (
                            <div className={styles.previewAudioOnlyBadge}>
                              <Headphones size={18} color="#38BDF8" />
                              <span>Audio Cleanup Only • No Subtitles</span>
                            </div>
                          ) : (
                            <div
                              className={`${activePreset.fontClass} ${popAnim ? styles.popScale : ''}`}
                              style={{
                                fontSize: `${Math.round(26 * sizeScale)}px`,
                                textTransform: isUppercase ? 'uppercase' : 'none',
                              }}
                            >
                              <span className={styles.previewWordLead}>{activePreset.lead}</span>
                              <span
                                className={styles.previewWordHighlight}
                                style={{ color: currentHighlightColor }}
                              >
                                {activePreset.highlight}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Video Meta Chips & Replace Button */}
                      <div className={styles.metaChipsRow}>
                        <div className={styles.chipsGroup}>
                          <span className={`${styles.metaChip} ${styles.metaChipCyan}`}>
                            {videoMeta?.orientation === 'portrait' ? '9:16 Shorts' : '16:9 YouTube'}
                          </span>
                          <span className={styles.metaChip}>
                            {videoMeta ? `${videoMeta.width}×${videoMeta.height}` : 'MP4'}
                          </span>
                          <span className={styles.metaChip}>
                            {videoMeta ? fmtSec(videoMeta.duration) : '0:00'}
                          </span>
                          <span className={styles.metaChip}>{fmtSize(selectedFile?.size)}</span>
                        </div>
                        <button
                          type="button"
                          className={styles.replaceBtn}
                          onClick={() => {
                            setSelectedFile(null)
                            setVideoSrc(null)
                            setVideoMeta(null)
                          }}
                        >
                          Replace
                        </button>
                      </div>
                    </div>
                  )}

                  {setupError && (
                    <div style={{ color: 'var(--danger)', fontSize: '0.85rem', display: 'flex', gap: 6, alignItems: 'center' }}>
                      <AlertCircle size={16} />
                      <span>{setupError}</span>
                    </div>
                  )}
                </div>

                {/* Right Column: Setup Controls */}
                <div className={styles.setupCol}>
                  {/* Style Presets */}
                  <div>
                    <h4 className={styles.sectionTitle}>
                      <Palette size={16} /> Subtitle Style Preset
                    </h4>
                    <p className={styles.sectionSubtitle}>Select viral typography for burned captions</p>
                    <div className={styles.presetGrid}>
                      {PRESET_OPTIONS.map((p) => {
                        const isActive = selectedPreset === p.id
                        return (
                          <div
                            key={p.id}
                            className={`${styles.presetCard} ${isActive ? styles.presetCardActive : ''}`}
                            onClick={() => setSelectedPreset(p.id)}
                          >
                            <div className={styles.presetHeader}>
                              <span className={styles.presetName}>{p.name}</span>
                              <span className={styles.presetTag}>{p.tag}</span>
                            </div>
                            <div className={`${p.fontClass} ${styles.presetPreviewText}`}>
                              <span style={{ color: '#fff', marginRight: 4 }}>{p.lead}</span>
                              <span style={{ color: p.defaultColor }}>{p.highlight}</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {/* Workflow Mode Toggle */}
                  <div className={styles.workflowCard}>
                    <div className={styles.workflowInfo}>
                      <span className={styles.workflowTitle}>
                        {autoPilot ? '⚡ 1-Click Auto-Pilot' : '🛠️ Step-by-Step Studio'}
                      </span>
                      <span className={styles.workflowDesc}>
                        {autoPilot
                          ? 'Automates all 5 stages end-to-end in one click'
                          : 'Pause at each step to download raw audio, import external AI audio, or edit captions'}
                      </span>
                    </div>
                    <label className={styles.checkboxLabel} style={{ margin: 0 }}>
                      <input
                        type="checkbox"
                        checked={autoPilot}
                        onChange={(e) => setAutoPilot(e.target.checked)}
                      />
                      <span>Auto</span>
                    </label>
                  </div>

                  {/* Voice Enhancement Mode */}
                  <div className={styles.segmentedGroup}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h4 className={styles.sectionTitle} style={{ margin: 0 }}>
                        <Headphones size={16} /> Voice Enhancement Mode
                      </h4>
                      <span className={styles.activeModePill}>
                        {voiceMode === 'studio' ? '🎙️ Studio AI (Active)' : voiceMode === 'clean' ? '🌿 Natural (Active)' : '🔈 Original Audio'}
                      </span>
                    </div>
                    <p className={styles.sectionSubtitle}>
                      Select cleanup model — applied when you click Start Studio Processing below
                    </p>
                    <div className={styles.segmentedRow}>
                      {[
                        { id: 'studio', label: '🎙️ Studio Podcast' },
                        { id: 'clean', label: '🌿 Natural Clean' },
                        { id: 'off', label: '🔈 Original Audio' },
                      ].map((m) => {
                        const isSelected = voiceMode === m.id
                        return (
                          <button
                            key={m.id}
                            type="button"
                            className={`${styles.segmentBtn} ${isSelected ? styles.segmentBtnActive : ''}`}
                            onClick={() => setVoiceMode(m.id)}
                          >
                            {isSelected && <Check size={13} style={{ marginRight: 4, verticalAlign: 'middle' }} />}
                            {m.label}
                          </button>
                        )
                      })}
                    </div>
                    <div className={styles.modeExplainerNote}>
                      {voiceMode === 'studio' && (
                        <span>⚡ <strong>Studio Podcast selected:</strong> Deep neural RNNoise eliminates hum/AC noise, followed by studio EQ and -16 LUFS broadcast vocal normalization.</span>
                      )}
                      {voiceMode === 'clean' && (
                        <span>🌿 <strong>Natural Clean selected:</strong> Light noise filtering preserving ambient room tone.</span>
                      )}
                      {voiceMode === 'off' && (
                        <span>🔈 <strong>Original Audio selected:</strong> Preserves raw microphone audio without AI alterations.</span>
                      )}
                    </div>
                  </div>

                  {/* Granular Customization Drawer */}
                  <div>
                    <button
                      type="button"
                      className={styles.accordionBtn}
                      onClick={() => setShowCustomize(!showCustomize)}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Sliders size={16} /> Customize Position &amp; Colors
                      </span>
                      <ChevronDown
                        size={16}
                        style={{
                          transform: showCustomize ? 'rotate(180deg)' : 'none',
                          transition: 'transform 0.2s',
                        }}
                      />
                    </button>

                    {showCustomize && (
                      <div className={styles.accordionBody}>
                        {/* Position */}
                        <div className={styles.segmentedGroup}>
                          <label className={styles.sectionSubtitle}>
                            <Maximize2 size={13} /> Position Alignment
                          </label>
                          <div className={styles.segmentedRow}>
                            {['default', 'bottom', 'center', 'upper'].map((pos) => (
                              <button
                                key={pos}
                                type="button"
                                className={`${styles.segmentBtn} ${position === pos ? styles.segmentBtnActive : ''}`}
                                onClick={() => setPosition(pos)}
                              >
                                {pos === 'default' ? 'Auto' : pos.charAt(0).toUpperCase() + pos.slice(1)}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Highlight Color */}
                        <div>
                          <label className={styles.sectionSubtitle}>
                            <Palette size={13} /> Highlight Color
                          </label>
                          <div className={styles.swatchRow}>
                            {COLOR_SWATCHES.map((hex) => (
                              <button
                                key={hex}
                                type="button"
                                className={`${styles.colorSwatch} ${currentHighlightColor === hex ? styles.colorSwatchActive : ''}`}
                                style={{ backgroundColor: hex }}
                                onClick={() => setCustomColor(hex)}
                              />
                            ))}
                            <input
                              type="color"
                              value={currentHighlightColor}
                              onChange={(e) => setCustomColor(e.target.value)}
                              className={styles.colorPickerInput}
                              title="Pick custom hex color"
                            />
                          </div>
                        </div>

                        {/* Size Scale */}
                        <div className={styles.segmentedGroup}>
                          <label className={styles.sectionSubtitle}>
                            <Type size={13} /> Caption Size: {Math.round(sizeScale * 100)}%
                          </label>
                          <div className={styles.segmentedRow}>
                            {[
                              { label: 'Compact (85%)', val: 0.85 },
                              { label: 'Normal (100%)', val: 1.0 },
                              { label: 'Punchy (115%)', val: 1.15 },
                            ].map((s) => (
                              <button
                                key={s.label}
                                type="button"
                                className={`${styles.segmentBtn} ${sizeScale === s.val ? styles.segmentBtnActive : ''}`}
                                onClick={() => setSizeScale(s.val)}
                              >
                                {s.label}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Checkboxes */}
                        <div className={styles.checkboxRow}>
                          <label className={styles.checkboxLabel}>
                            <input
                              type="checkbox"
                              checked={isUppercase}
                              onChange={(e) => setIsUppercase(e.target.checked)}
                            />
                            <span>ALL CAPS</span>
                          </label>
                          <label className={styles.checkboxLabel}>
                            <input
                              type="checkbox"
                              checked={popAnim}
                              onChange={(e) => setPopAnim(e.target.checked)}
                            />
                            <span>Word Pop Animation</span>
                          </label>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Action Area & Upload Progress */}
                  <div className={styles.actionArea}>
                    <button
                      type="button"
                      className={styles.primaryBtn}
                      onClick={handleStartProcessing}
                      disabled={!selectedFile || uploadProgress !== null}
                    >
                      {uploadProgress ? (
                        <>
                          <div
                            className={styles.uploadProgressBar}
                            style={{ width: `${uploadProgress.pct}%` }}
                          />
                          <span style={{ zIndex: 2 }}>
                            Uploading {uploadProgress.pct}% ({uploadProgress.loadedMb}/{uploadProgress.totalMb} MB • {uploadProgress.speedMb} MB/s)
                          </span>
                        </>
                      ) : (
                        <>
                          <Sparkles size={18} />
                          <span>
                            Start Studio Processing ({voiceMode === 'studio' ? '🎙️ Studio AI' : voiceMode === 'clean' ? '🌿 Clean AI' : '🔈 Raw Audio'})
                          </span>
                        </>
                      )}
                    </button>
                    <span className={styles.estTimeLabel}>
                      Estimated processing time: ~1–3 min • Max 300 MB
                    </span>
                  </div>
                </div>
              </div>
              </>
            )}

            {/* VIEW 2: LIVE PROCESSING OR STEP-BY-STEP PAUSED */}
            {activeJobId && !job && (
              <div style={{ textAlign: 'center', padding: '100px 0', color: 'var(--text-muted)' }}>
                <RefreshCw size={28} className={styles.spin} color="#38BDF8" style={{ marginBottom: 16 }} />
                <p style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>Connecting to Prajwal's Studio Pipeline...</p>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-faint)', marginTop: 4 }}>Loading job #{activeJobId}</p>
              </div>
            )}
            {activeJobId && job && (job.status === 'running' || job.status === 'paused') && (
              <div className={styles.processingView}>
                {/* Header Bar */}
                <div className={styles.jobHeaderBar}>
                  <div className={styles.jobTitleGroup}>
                    <span className={styles.jobName}>{job.input.name}</span>
                    <span className={styles.pill}>{job.options.preset}</span>
                    <span className={styles.pill}>Voice: {job.options.voice}</span>
                    <div className={styles.healthChip}>
                      <span className={styles.statusDot} />
                      <span>{job.status === 'paused' ? 'Paused (Action Required)' : 'Processing'}</span>
                    </div>
                  </div>
                  <button type="button" className={styles.cancelBtn} onClick={handleCancelJob}>
                    Cancel Job
                  </button>
                </div>

                {/* Split Area: Original Video + Now Card */}
                <div className={styles.processSplitGrid}>
                  <div className={styles.originalVideoCard}>
                    <h4 className={styles.sectionTitle} style={{ marginBottom: 10 }}>
                      Original Uploaded Video
                    </h4>
                    {videoSrc && (
                      <video
                        src={videoSrc}
                        controls
                        style={{ width: '100%', maxHeight: 320, borderRadius: 8 }}
                      />
                    )}
                  </div>

                  <div className={styles.nowCard}>
                    <div>
                      <div className={styles.nowHeader}>
                        <span className={styles.nowStageTag}>Current Stage</span>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-faint)' }}>
                          Job ID: {activeJobId}
                        </span>
                      </div>
                      <h3 className={styles.nowStageName}>
                        {job.stages.find((s) => s.status === 'running')?.label || 'Processing pipeline…'}
                      </h3>
                      <p className={styles.nowDescription}>
                        {job.stages.find((s) => s.status === 'running')?.message ||
                          'Applying neural denoiser, EQ, speech transcription, and libass subtitle rendering.'}
                      </p>
                    </div>

                    <div>
                      <div className={styles.progressBarTrack}>
                        <div
                          className={styles.progressBarFill}
                          style={{
                            width: `${
                              job.stages.find((s) => s.status === 'running')?.progress || 20
                            }%`,
                          }}
                        />
                      </div>
                      <div className={styles.progressNumbers}>
                        <span>
                          Progress:{' '}
                          {job.stages.find((s) => s.status === 'running')?.progress || 0}%
                        </span>
                        <span>Full-band 48 kHz</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Horizontal Timeline Pipeline */}
                <div className={styles.timelineCard}>
                  <div className={styles.timelineHeader}>
                    <span className={styles.timelineLabel}>Pipeline Timeline</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-faint)' }}>
                      Total Duration: {job.input.duration_s ? `${job.input.duration_s}s` : 'Probed'}
                    </span>
                  </div>
                  <div className={styles.timelineStrip}>
                    {job.stages.map((st) => {
                      const isRunning = st.status === 'running'
                      const isDone = st.status === 'done'
                      const isFailed = st.status === 'failed'
                      const isSkipped = isDone && st.message?.toLowerCase().includes('skipped')

                      let clipClass = styles.timelineClip
                      if (isRunning) clipClass += ` ${styles.timelineClipActive}`
                      if (isDone) clipClass += ` ${styles.timelineClipDone}`
                      if (isFailed) clipClass += ` ${styles.timelineClipFailed}`

                      return (
                        <div
                          key={st.key}
                          className={clipClass}
                          style={{ '--clip-progress': `${st.progress}%` }}
                        >
                          {isSkipped ? (
                            <FastForward size={14} color="#38BDF8" />
                          ) : isDone ? (
                            <Check size={14} color="#86EFAC" />
                          ) : isRunning ? (
                            <RefreshCw size={14} className={styles.spin} color="#F5B50A" />
                          ) : isFailed ? (
                            <XCircle size={14} color="#F87171" />
                          ) : (
                            <Clock size={14} color="var(--text-faint)" />
                          )}
                          <span>
                            {st.label}
                            {isSkipped ? ' (Skipped)' : ''}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* ── Step-by-Step Interactive Workstation (When Paused) ── */}
                {job.status === 'paused' && (
                  <div className={styles.stepHighlightBox}>
                    {/* Action 1: Awaiting audio decision after extract */}
                    {job.step_action === 'awaiting_audio_decision' && (
                      <>
                        <div className={styles.stepHeaderGroup}>
                          <Headphones size={24} color="#38BDF8" />
                          <div>
                            <h4 className={styles.stepTitle}>
                              Step 1 Complete: Audio Track Extracted!
                            </h4>
                            <p className={styles.stepDesc}>
                              Listen to the extracted raw audio below. Choose whether to enhance it with our built-in neural AI, or import an externally enhanced track.
                            </p>
                          </div>
                        </div>

                        <div className={styles.audioPlayerPreviewRow}>
                          <span className={styles.audioPlayerLabel}>Raw Audio Preview:</span>
                          <audio
                            src={`/api/jobs/${activeJobId}/files/extracted_audio.wav`}
                            controls
                            style={{ flex: 1, height: 38 }}
                          />
                          <a
                            href={`/api/jobs/${activeJobId}/files/extracted_audio.wav`}
                            download="raw_audio.wav"
                            className={styles.secondaryBtn}
                            style={{ height: 38, padding: '0 14px' }}
                          >
                            <Download size={14} /> Download WAV
                          </a>
                        </div>

                        <div className={styles.stepActionsRow}>
                          <button
                            type="button"
                            className={styles.stepProceedBtn}
                            onClick={() => handleResumeStep('enhance')}
                          >
                            <Wand2 size={16} /> Use Built-in Neural AI Cleaner ({job.options?.voice || 'Studio'})
                          </button>

                          {/* External audio upload */}
                          <label className={styles.secondaryBtn} style={{ cursor: 'pointer', height: 42 }}>
                            <Upload size={15} />
                            <span>{audioImportFile ? audioImportFile.name : 'Import External Clean Audio'}</span>
                            <input
                              type="file"
                              accept="audio/*,.wav,.mp3"
                              className={styles.fileInputHidden}
                              onChange={(e) => {
                                if (e.target.files?.[0]) setAudioImportFile(e.target.files[0])
                              }}
                            />
                          </label>

                          {audioImportFile && (
                            <button
                              type="button"
                              className={styles.primaryBtn}
                              style={{ height: 42, background: 'var(--success)', padding: '0 16px' }}
                              onClick={handleImportAudio}
                            >
                              Confirm &amp; Proceed
                            </button>
                          )}
                        </div>

                        {/* Skip Actions Row */}
                        <div className={styles.skipActionsGroup}>
                          <button
                            type="button"
                            className={styles.skipBtn}
                            onClick={() => handleResumeStep('skip_enhance')}
                            title="Skip audio cleaning and keep original microphone audio"
                          >
                            <FastForward size={15} />
                            <span>Skip Audio Cleanup (Keep Raw Audio)</span>
                          </button>
                          <button
                            type="button"
                            className={styles.skipBtnGhost}
                            onClick={() => handleResumeStep('skip_subtitles')}
                            title="Finish video immediately with clean audio — skip subtitle transcription"
                          >
                            <FastForward size={15} />
                            <span>Skip to Finish (Audio Cleanup Only, No Subtitles)</span>
                          </button>
                        </div>
                      </>
                    )}

                    {/* Action 2: Cleaned audio ready */}
                    {job.step_action === 'awaiting_transcribe_proceed' && (
                      <>
                        <div className={styles.stepHeaderGroup}>
                          <Sparkles size={24} color="#F5B50A" />
                          <div>
                            <h4 className={styles.stepTitle}>
                              Step 2 Complete: Audio Cleaned &amp; Normalized!
                            </h4>
                            <p className={styles.stepDesc}>
                              Your audio track has been enhanced with RNNoise neural denoiser and studio EQ. Listen to the enhanced result below, then proceed to transcribe speech into viral subtitles!
                            </p>
                          </div>
                        </div>

                        <div className={styles.audioPlayerPreviewRow}>
                          <span className={styles.audioPlayerLabel}>Cleaned Audio Preview:</span>
                          <audio
                            src={`/api/jobs/${activeJobId}/files/cleaned_audio.wav`}
                            controls
                            style={{ flex: 1, height: 38 }}
                          />
                          <a
                            href={`/api/jobs/${activeJobId}/files/cleaned_audio.wav`}
                            download="cleaned_audio.wav"
                            className={styles.secondaryBtn}
                            style={{ height: 38, padding: '0 14px' }}
                          >
                            <Download size={14} /> Download WAV
                          </a>
                        </div>

                        <div className={styles.stepProceedRow}>
                          <button
                            type="button"
                            className={styles.stepProceedBtn}
                            onClick={() => handleResumeStep('transcribe')}
                          >
                            <ArrowRight size={18} />
                            <span>Proceed to Step 3: Transcribe Speech with Gemini AI →</span>
                          </button>
                          <button
                            type="button"
                            className={styles.skipBtn}
                            onClick={() => handleResumeStep('skip_subtitles')}
                            title="Skip subtitle generation and export final video with clean audio immediately"
                          >
                            <FastForward size={16} />
                            <span>Skip Subtitles &amp; Finish Video (Audio Cleanup Only)</span>
                          </button>
                        </div>
                      </>
                    )}

                    {/* Action 3: Subtitles generated, user can review/edit */}
                    {job.step_action === 'awaiting_burn_proceed' && (
                      <>
                        <h4 className={styles.stepTitle}>
                          <Type size={18} /> Step 3 Complete: Subtitles Generated!
                        </h4>
                        <p className={styles.stepDesc}>
                          Review or adjust your Hinglish/English captions below before burning them onto the video.
                        </p>
                        <textarea
                          value={editableSrt}
                          onChange={(e) => setEditableSrt(e.target.value)}
                          rows={6}
                          style={{
                            width: '100%',
                            background: 'var(--panel-2)',
                            border: '1px solid var(--border)',
                            borderRadius: 8,
                            color: '#fff',
                            padding: 10,
                            fontFamily: 'monospace',
                            fontSize: '0.8rem',
                          }}
                        />
                        <div className={styles.stepActionsRow}>
                          <a
                            href={`/api/jobs/${activeJobId}/files/captions.srt`}
                            download="subtitles.srt"
                            className={styles.secondaryBtn}
                          >
                            <Download size={15} /> Download Subtitles (.srt)
                          </a>
                          <button
                            type="button"
                            className={styles.primaryBtn}
                            style={{ height: 42, padding: '0 20px' }}
                            onClick={handleReburnWithEdits}
                          >
                            <Film size={16} /> Burn Subtitles Into Video
                          </button>
                          <button
                            type="button"
                            className={styles.skipBtn}
                            onClick={() => handleResumeStep('skip_burn')}
                            title="Export video with clean audio without burning subtitles on screen (SRT download remains available)"
                          >
                            <FastForward size={16} />
                            <span>Skip Subtitle Burn (Export Video &amp; Keep SRT)</span>
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* Live Terminal Log Panel */}
                <div className={styles.logPanel}>
                  <div className={styles.logHeader}>
                    <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#fff' }}>
                      Terminal &amp; Execution Log
                    </span>
                    <div style={{ display: 'flex', gap: 10 }}>
                      <label className={styles.checkboxLabel} style={{ fontSize: '0.75rem' }}>
                        <input
                          type="checkbox"
                          checked={showTechnicalLog}
                          onChange={(e) => setShowTechnicalLog(e.target.checked)}
                        />
                        <span>Technical Details</span>
                      </label>
                      <button type="button" className={styles.replaceBtn} onClick={copyLogText}>
                        <Copy size={13} /> {copiedLog ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                  </div>
                  <div className={styles.logBody}>
                    {job.logs?.map((l, i) => (
                      <div key={i} className={styles.logLine}>
                        <span className={styles.logTime}>{l.time}</span>
                        <span className={styles.logStage}>{l.stage}</span>
                        <span
                          className={`${styles.logMsg} ${l.level === 'error' ? styles.logLevelError : ''}`}
                        >
                          {l.message} {showTechnicalLog && l.raw ? `(${l.raw})` : ''}
                        </span>
                      </div>
                    ))}
                    <div ref={logEndRef} />
                  </div>
                </div>
              </div>
            )}

            {/* VIEW 3: RESULT & DOWNLOADS VIEW */}
            {activeJobId && job?.status === 'done' && (
              <div className={styles.resultView}>
                {/* Result Header */}
                <div className={styles.resultHeader}>
                  <div className={styles.successBanner}>
                    <CheckCircle2 size={24} />
                    <span>
                      {job?.options?.preset === 'no-subs' ||
                      job?.stages?.find((s) => s.key === 'transcribe')?.message?.toLowerCase().includes('skipped') ||
                      job?.stages?.find((s) => s.key === 'burn')?.message?.toLowerCase().includes('subtitles skipped')
                        ? 'Clean Audio Video Exported & Ready!'
                        : 'Viral Video Rendered & Ready!'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 10 }}>
                    <button
                      type="button"
                      onClick={() => openFormatModal(job)}
                      className={styles.downloadCtaBtn}
                    >
                      <Download size={18} /> Download Final Video (9:16 / 16:9)
                    </button>
                    <button type="button" className={styles.secondaryBtn} onClick={handleReset}>
                      <RotateCcw size={15} /> New Project
                    </button>
                  </div>
                </div>

                {/* Synced Dual Video Player with A/B Audio Toggle */}
                <div className={styles.syncedPlayersCard}>
                  <div className={styles.dualPlayersGrid}>
                    {/* Left: Original Video Player */}
                    <div className={styles.playerBox}>
                      <div className={styles.playerHeader}>
                        <span className={styles.playerLabel}>Original Video</span>
                        <span className={styles.metaChip}>
                          {audioChannel === 'original' ? (
                            <Volume2 size={13} color="#38BDF8" />
                          ) : (
                            <VolumeX size={13} />
                          )}
                        </span>
                      </div>
                      <video
                        ref={videoPlayerOriginalRef}
                        src={`/api/jobs/${activeJobId}/files/input.mp4`}
                        className={styles.playerVideo}
                        onTimeUpdate={handleTimeUpdate}
                        playsInline
                      />
                    </div>

                    {/* Right: Processed Video Player */}
                    <div className={styles.playerBox}>
                      <div className={styles.playerHeader}>
                        <span className={styles.playerLabel}>
                          {job?.options?.preset === 'no-subs' ||
                          job?.stages?.find((s) => s.key === 'transcribe')?.message?.toLowerCase().includes('skipped') ||
                          job?.stages?.find((s) => s.key === 'burn')?.message?.toLowerCase().includes('subtitles skipped')
                            ? 'Cleaned Audio Video'
                            : 'Cleaned Audio + Subtitles'}
                        </span>
                        <span className={`${styles.metaChip} ${styles.metaChipCyan}`}>
                          {audioChannel === 'processed' ? (
                            <Volume2 size={13} color="#38BDF8" />
                          ) : (
                            <VolumeX size={13} />
                          )}
                        </span>
                      </div>
                      <video
                        ref={videoPlayerProcessedRef}
                        src={`/api/jobs/${activeJobId}/files/final_video.mp4`}
                        className={styles.playerVideo}
                        playsInline
                      />
                    </div>
                  </div>

                  {/* Synced Controls Bar */}
                  <div className={styles.syncedControlsBar}>
                    <button type="button" className={styles.secondaryBtn} onClick={togglePlay}>
                      {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                      <span>{isPlaying ? 'Pause Both' : 'Play Both'}</span>
                    </button>

                    <div className={styles.scrubGroup}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-faint)' }}>
                        {fmtSec(currentTime)}
                      </span>
                      <input
                        type="range"
                        min="0"
                        max={duration || 100}
                        step="0.1"
                        value={currentTime}
                        onChange={handleSeek}
                        className={styles.scrubSlider}
                      />
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-faint)' }}>
                        {fmtSec(duration)}
                      </span>
                    </div>

                    {/* A/B Audio Switcher */}
                    <button
                      type="button"
                      className={styles.abToggleBtn}
                      onClick={() =>
                        setAudioChannel((prev) => (prev === 'processed' ? 'original' : 'processed'))
                      }
                      title="Switch audio stream to compare original vs cleaned audio"
                    >
                      <Volume2 size={15} />
                      <span>Audio: {audioChannel === 'processed' ? 'Cleaned Audio' : 'Original Audio'}</span>
                    </button>
                  </div>
                </div>

                {/* Background Music Mixing Card */}
                <div className={styles.musicMixerCard}>
                  <h4 className={styles.sectionTitle}>
                    <Music size={18} /> Optional: Add Background Music
                  </h4>
                  <p className={styles.sectionSubtitle}>
                    Upload an MP3/WAV background score. It will be looped and gently ducked under your spoken voice.
                  </p>
                  <div className={styles.musicRow}>
                    <label className={styles.secondaryBtn} style={{ cursor: 'pointer' }}>
                      <Upload size={15} />
                      <span>{musicFile ? musicFile.name : 'Choose Music (.mp3, .wav)'}</span>
                      <input
                        type="file"
                        accept="audio/*,.mp3,.wav"
                        className={styles.fileInputHidden}
                        onChange={(e) => {
                          if (e.target.files?.[0]) setMusicFile(e.target.files[0])
                        }}
                      />
                    </label>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        Volume: {Math.round(musicVol * 100)}%
                      </span>
                      <input
                        type="range"
                        min="0.05"
                        max="0.40"
                        step="0.01"
                        value={musicVol}
                        onChange={(e) => setMusicVol(parseFloat(e.target.value))}
                        className={styles.musicSlider}
                      />
                    </div>

                    <button
                      type="button"
                      className={styles.primaryBtn}
                      style={{ height: 40, padding: '0 18px' }}
                      disabled={!musicFile || isSubmittingMusic}
                      onClick={handleMixMusic}
                    >
                      {isSubmittingMusic ? 'Mixing...' : 'Mix & Update Video'}
                    </button>
                  </div>
                </div>

                {/* What We Did Report Cards */}
                <div className={styles.reportCardsGrid}>
                  <div className={styles.reportCard}>
                    <span className={styles.reportCardTitle}>Voice Enhancement</span>
                    <div className={styles.reportCardStat}>-16.0 LUFS</div>
                    <span className={styles.reportCardSub}>
                      RNNoise Neural GRU + Studio Vocal EQ + Downward Gate
                    </span>
                  </div>

                  <div className={styles.reportCard}>
                    <span className={styles.reportCardTitle}>Captions Burned</span>
                    <div className={styles.reportCardStat}>
                      {job.metrics?.words || 0} words
                    </div>
                    <span className={styles.reportCardSub}>
                      {job.metrics?.lines || 0} lines • {job.options.preset}
                    </span>
                  </div>

                  <div className={styles.reportCard}>
                    <span className={styles.reportCardTitle}>Video Geometry</span>
                    <div className={styles.reportCardStat}>
                      {job.input.width}×{job.input.height}
                    </div>
                    <span className={styles.reportCardSub}>
                      {job.input.orientation === 'portrait' ? '9:16 Portrait' : '16:9 Landscape'} (Zero distortion)
                    </span>
                  </div>

                  <div className={styles.reportCard}>
                    <span className={styles.reportCardTitle}>Export Time</span>
                    <div className={styles.reportCardStat}>
                      {(
                        job.stages.reduce((acc, s) => acc + (s.duration_ms || 0), 0) / 1000
                      ).toFixed(1)}
                      s
                    </div>
                    <span className={styles.reportCardSub}>Fast CPU libass render</span>
                  </div>
                </div>

                {/* Multi-Asset Downloads */}
                <div className={styles.downloadsCard}>
                  <h4 className={styles.sectionTitle}>
                    <Download size={18} /> Download Project Assets
                  </h4>
                  <div className={styles.filesGrid}>
                    {job.files?.map((f) => {
                      const isVideo = f.name.endsWith('.mp4')
                      return isVideo ? (
                        <div
                          key={f.name}
                          className={styles.fileCardItem}
                          style={{ cursor: 'pointer' }}
                          onClick={() => openFormatModal(job)}
                          title="Click to choose 9:16 Shorts or 16:9 Landscape"
                        >
                          <div className={styles.fileItemLeft}>
                            <Film size={20} color="#38BDF8" />
                            <div>
                              <div className={styles.fileItemName}>
                                {f.label}{' '}
                                <span style={{ fontSize: '0.72rem', color: '#F5B50A', marginLeft: 6 }}>
                                  (Choose Format)
                                </span>
                              </div>
                              <div className={styles.fileItemSize}>{f.size_mb} MB • 9:16 / 16:9</div>
                            </div>
                          </div>
                          <Download size={16} color="#F5B50A" />
                        </div>
                      ) : (
                        <div
                          key={f.name}
                          className={styles.fileCardItem}
                          style={{ cursor: 'pointer' }}
                          onClick={() =>
                            downloadWithSavePicker(
                              `/api/jobs/${activeJobId}/files/${f.name}`,
                              f.name,
                              null
                            )
                          }
                          title="Click to download and choose destination folder"
                        >
                          <div className={styles.fileItemLeft}>
                            {f.name.endsWith('.wav') ? (
                              <Volume2 size={20} color="#86EFAC" />
                            ) : f.name.endsWith('.zip') ? (
                              <FolderOpen size={20} color="#F5B50A" />
                            ) : (
                              <Type size={20} color="#A5B4FC" />
                            )}
                            <div>
                              <div className={styles.fileItemName}>{f.label}</div>
                              <div className={styles.fileItemSize}>{f.size_mb} MB</div>
                            </div>
                          </div>
                          <Download size={16} color="var(--text-faint)" />
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* VIEW 4: FAILURE REPORT VIEW */}
            {activeJobId && job?.status === 'failed' && (
              <div className={styles.failureCard}>
                <div className={styles.failureHeader}>
                  <AlertCircle size={32} className={styles.failureIcon} />
                  <div>
                    <h3 className={styles.failureTitle}>
                      {getErrorDetails(job.error?.code, job.error?.message).title}
                    </h3>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-faint)' }}>
                      Failed at stage: {job.error?.stage || 'processing'}
                    </span>
                  </div>
                </div>

                {/* Timeline showing failed stage */}
                <div className={styles.timelineStrip}>
                  {job.stages.map((st) => (
                    <div
                      key={st.key}
                      className={`${styles.timelineClip} ${
                        st.status === 'failed'
                          ? styles.timelineClipFailed
                          : st.status === 'done'
                          ? styles.timelineClipDone
                          : ''
                      }`}
                    >
                      <span>{st.label}</span>
                    </div>
                  ))}
                </div>

                {/* Plain-English Explanation */}
                <div className={styles.failureExplainBox}>
                  <p style={{ fontWeight: 700, marginBottom: 4 }}>What happened:</p>
                  <p>{getErrorDetails(job.error?.code, job.error?.message).what}</p>
                  <p style={{ fontWeight: 700, marginTop: 10, marginBottom: 4 }}>What to do:</p>
                  <p>{getErrorDetails(job.error?.code, job.error?.message).fix}</p>
                </div>

                {/* Saved Work Notice */}
                <div className={styles.savedWorkNotice}>
                  <strong>✓ Your work is safe:</strong> Any previously completed stages (such as audio
                  extraction and clean audio) are preserved. Retrying resumes directly from the failed stage!
                </div>

                {/* Actions */}
                <div className={styles.failureActionsRow}>
                  <button type="button" className={styles.retryBtn} onClick={handleRetryJob}>
                    <RefreshCw size={16} /> Retry from Failed Stage
                  </button>
                  <a
                    href={`/api/jobs/${activeJobId}/files/extracted_audio.wav`}
                    download="extracted_audio.wav"
                    className={styles.secondaryBtn}
                  >
                    <Download size={15} /> Download Extracted Audio
                  </a>
                  <button type="button" className={styles.secondaryBtn} onClick={handleReset}>
                    Upload Different Video
                  </button>
                </div>

                {/* Technical Drawer for Prajwal */}
                <div>
                  <button
                    type="button"
                    className={styles.replaceBtn}
                    onClick={() => setShowTechnicalLog(!showTechnicalLog)}
                  >
                    {showTechnicalLog ? 'Hide Technical Details' : 'View Technical Details (For Prajwal)'}
                  </button>
                  {showTechnicalLog && (
                    <div className={styles.techDrawer}>
                      {JSON.stringify(job, null, 2)}
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {/* ═══════════════════════════════════════════════════════════════════
            TAB 2: PROJECTS / HISTORY
           ═══════════════════════════════════════════════════════════════════ */}
        {activeTab === 'projects' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <h3 className={styles.sectionTitle} style={{ fontSize: '1.25rem', marginBottom: 6 }}>
                  <FolderOpen size={22} /> Creator Project History
                </h3>
                <p className={styles.sectionSubtitle}>
                  {projects.length} recent video{projects.length === 1 ? '' : 's'} processed in your studio
                </p>
              </div>
              {projects.length > 0 && (
                <button
                  type="button"
                  className={styles.deleteProjectBtn}
                  onClick={handleClearAllProjects}
                  title="Permanently remove all project files and free up disk space"
                >
                  <Trash2 size={14} /> Clear All History
                </button>
              )}
            </div>

            {projects.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>
                No past projects found. Upload a video in the Studio tab to get started!
              </div>
            ) : (
              <div className={styles.projectsGrid}>
                {projects.map((p) => {
                  const uploadTimeIST = p.created_at_ist || formatIST(p.created_at)
                  const thumbUrl = p.thumbnail_url || `/api/jobs/${p.job_id}/thumbnail`

                  return (
                    <div key={p.job_id} className={styles.projectCard}>
                      {/* Video Thumbnail (First Frame Preview) */}
                      <div
                        className={styles.projectThumbnailWrap}
                        onClick={() => {
                          localStorage.setItem('ytsub_active_job', p.job_id)
                          setActiveJobId(p.job_id)
                          setActiveTab('studio')
                        }}
                        title="Click to open this video in Studio"
                      >
                        <img
                          src={thumbUrl}
                          alt={p.name}
                          className={styles.projectThumbnailImg}
                          loading="lazy"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none'
                            const fb = e.currentTarget.parentElement?.querySelector(`.${styles.projectThumbnailFallback}`)
                            if (fb) fb.style.display = 'flex'
                          }}
                        />
                        <div className={styles.projectThumbnailFallback} style={{ display: 'none' }}>
                          <Film size={32} />
                          <span style={{ fontSize: '0.72rem', marginTop: 4 }}>Video Preview</span>
                        </div>

                        {/* Overlay Status Badge */}
                        <span className={`${styles.projectStatusBadge} ${styles['statusBadge_' + p.status] || ''}`}>
                          {p.status}
                        </span>

                        {/* Duration Badge */}
                        {p.duration_s > 0 && (
                          <span className={styles.projectDurationBadge}>
                            {fmtSec(p.duration_s)}
                          </span>
                        )}

                        {/* Orientation Badge */}
                        {p.orientation && (
                          <span className={styles.projectOrientationBadge}>
                            {p.orientation === 'portrait' ? '9:16 Shorts' : '16:9 Landscape'}
                          </span>
                        )}
                      </div>

                      {/* Video Information Header */}
                      <div className={styles.projectInfo}>
                        <div
                          className={styles.projectTitle}
                          title={p.name}
                          onClick={() => {
                            localStorage.setItem('ytsub_active_job', p.job_id)
                            setActiveJobId(p.job_id)
                            setActiveTab('studio')
                          }}
                        >
                          {p.name}
                        </div>

                        {/* Indian Standard Time (IST) Upload Timestamp */}
                        <div className={styles.projectTimestampRow} title={`Uploaded at ${uploadTimeIST}`}>
                          <Clock size={12} className={styles.timestampIcon} />
                          <span>Uploaded: <strong style={{ color: '#E2E8F0', fontWeight: 600 }}>{uploadTimeIST}</strong></span>
                        </div>

                        <div className={styles.projectMetaRow}>
                          <span>Preset: <strong style={{ color: '#CBD5E1' }}>{p.preset}</strong></span>
                          <span>•</span>
                          <span>{p.size_mb} MB</span>
                          {p.voice && (
                            <>
                              <span>•</span>
                              <span>Voice: {p.voice}</span>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Project Actions */}
                      <div className={styles.projectActionsRow}>
                        <button
                          type="button"
                          className={styles.openProjectBtn}
                          onClick={() => {
                            localStorage.setItem('ytsub_active_job', p.job_id)
                            setActiveJobId(p.job_id)
                            setActiveTab('studio')
                          }}
                          title="Open in Studio for subtitle editing, audio tuning, and export"
                        >
                          Open in Studio
                        </button>
                        {p.status === 'done' && (
                          <button
                            type="button"
                            className={styles.secondaryBtn}
                            style={{ padding: '6px 11px', fontSize: '0.78rem' }}
                            onClick={() => openFormatModal(p)}
                            title="Export in 9:16 Shorts or 16:9 Landscape format"
                          >
                            <Download size={13} /> Export Format
                          </button>
                        )}
                        <button
                          type="button"
                          className={styles.deleteCardBtn}
                          onClick={(e) => handleDeleteProject(p.job_id, p.name, e)}
                          title="Permanently delete project and purge disk files"
                        >
                          <Trash2 size={13} /> Delete
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════════
            TAB 3: SETTINGS & SYSTEM HEALTH
           ═══════════════════════════════════════════════════════════════════ */}
        {activeTab === 'settings' && (
          <div>
            <h3 className={styles.sectionTitle} style={{ fontSize: '1.25rem', marginBottom: 6 }}>
              <Settings size={22} /> System Health &amp; Studio Diagnostics
            </h3>
            <p className={styles.sectionSubtitle} style={{ marginBottom: 20 }}>
              Live configuration status of your personal AI video toolkit
            </p>

            <div className={styles.settingsCard}>
              <div className={styles.settingsRow}>
                <div>
                  <div style={{ fontWeight: 700, color: '#fff' }}>Google Gemini AI Speech API</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Model: {health?.gemini?.model || 'gemini-3.5-flash'} • Roman-script Hinglish &amp; English
                  </div>
                </div>
                <span className={styles.pill} style={{ color: health?.gemini?.configured ? '#86EFAC' : '#F87171' }}>
                  {health?.gemini?.configured ? '● Configured & Live' : '✕ Missing Key'}
                </span>
              </div>

              <div className={styles.settingsRow}>
                <div>
                  <div style={{ fontWeight: 700, color: '#fff' }}>FFmpeg &amp; libass Runtime</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    {health?.ffmpeg?.version || 'Gyan.FFmpeg 9.0.2 Full Build'}
                  </div>
                </div>
                <span className={styles.pill} style={{ color: '#86EFAC' }}>
                  ● Active
                </span>
              </div>

              <div className={styles.settingsRow}>
                <div>
                  <div style={{ fontWeight: 700, color: '#fff' }}>RNNoise Neural Audio Models</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Model weights: sh.rnnn (~297 KB) &amp; cb.rnnn (~299 KB)
                  </div>
                </div>
                <span className={styles.pill} style={{ color: '#86EFAC' }}>
                  ● Bundled &amp; Ready
                </span>
              </div>

              <div className={styles.settingsRow}>
                <div>
                  <div style={{ fontWeight: 700, color: '#fff' }}>Max Upload Size</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Streaming disk chunks in 1 MB buffers
                  </div>
                </div>
                <span className={styles.pill} style={{ color: 'var(--accent-cyan)' }}>
                  {health?.storage?.max_upload_mb || 300} MB Limit
                </span>
              </div>

              <div className={styles.settingsRow}>
                <div>
                  <div style={{ fontWeight: 700, color: '#fff' }}>Free Storage Space</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Jobs directory: {health?.storage?.jobs_dir || 'backend/jobs'}
                  </div>
                </div>
                <span className={styles.pill}>
                  {health?.storage?.free_gb || 0} GB Free
                </span>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ── Download Format Pop-up Modal ── */}
      {isFormatModalOpen && formatModalJob && (
        <div className={styles.modalOverlay} onClick={closeFormatModal}>
          <div className={styles.modalCard} onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className={styles.modalHeader}>
              <div className={styles.modalTitleGroup}>
                <h3 className={styles.modalTitle}>
                  <Sparkles size={22} color="#F5B50A" /> Choose Video Export Format
                </h3>
                <span className={styles.modalSubtitle}>
                  Target video:{' '}
                  <strong style={{ color: '#fff' }}>{formatModalJob.name || formatModalJob.input?.name || 'Video'}</strong> •
                  Detected native orientation:{' '}
                  <strong style={{ color: '#38BDF8' }}>
                    {formatModalJob.orientation === 'portrait' || formatModalJob.input?.orientation === 'portrait'
                      ? '9:16 Vertical Shorts'
                      : '16:9 Landscape Video'}
                  </strong>
                </span>
              </div>
              <button
                type="button"
                className={styles.modalCloseBtn}
                onClick={closeFormatModal}
                disabled={isReformatting}
              >
                <X size={18} />
              </button>
            </div>

            {/* Converting Overlay when FFmpeg is running */}
            {isReformatting && (
              <div className={styles.modalConvertingOverlay}>
                <div className={styles.convertingSpinner} />
                <div className={styles.convertingTitle}>
                  Exporting {reformattingFormat}...
                </div>
                <div className={styles.convertingDesc}>
                  FFmpeg is formatting your video frames and multiplexing clean audio. This typically takes
                  around 3–5 seconds. Download will begin automatically!
                </div>
              </div>
            )}

            {reformatError && (
              <div className={styles.setupErrorCard} style={{ marginBottom: 16 }}>
                <AlertCircle size={16} />
                <span>{reformatError}</span>
              </div>
            )}

            {/* Save Location / Folder Destination Section */}
            <div className={styles.destinationSection}>
              <div className={styles.destinationHeader}>
                <FolderOpen size={16} color="#F5B50A" />
                <span style={{ fontWeight: 600, color: '#fff', fontSize: '0.88rem' }}>
                  Save Location / Folder Destination
                </span>
              </div>

              <div className={styles.destinationToggleRow}>
                <button
                  type="button"
                  className={`${styles.destModeBtn} ${saveMode === 'ask' ? styles.destModeBtnActive : ''}`}
                  onClick={() => {
                    setSaveMode('ask')
                    localStorage.setItem('ytsub_save_mode', 'ask')
                  }}
                >
                  <span className={styles.destRadioDot}>{saveMode === 'ask' && <span />}</span>
                  <span>📁 <strong>Ask where to save</strong> (Windows Explorer Save As Dialog)</span>
                </button>
                <button
                  type="button"
                  className={`${styles.destModeBtn} ${saveMode === 'folder' ? styles.destModeBtnActive : ''}`}
                  onClick={() => {
                    setSaveMode('folder')
                    localStorage.setItem('ytsub_save_mode', 'folder')
                  }}
                >
                  <span className={styles.destRadioDot}>{saveMode === 'folder' && <span />}</span>
                  <span>💾 <strong>Save directly to folder path</strong></span>
                </button>
              </div>

              {saveMode === 'folder' && (
                <div className={styles.folderInputWrap}>
                  <div className={styles.folderInputRow}>
                    <input
                      type="text"
                      className={styles.folderTextInput}
                      placeholder="e.g. C:\Users\Prajwal\Videos or D:\YouTube\Final"
                      value={customFolderPath}
                      onChange={(e) => {
                        setCustomFolderPath(e.target.value)
                        localStorage.setItem('ytsub_export_folder', e.target.value)
                      }}
                    />
                  </div>

                  {commonFolders && Object.keys(commonFolders).length > 0 && (
                    <div className={styles.quickFoldersRow}>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-faint)', marginRight: 4 }}>
                        Quick Presets:
                      </span>
                      {Object.entries(commonFolders).map(([key, fpath]) => (
                        <button
                          key={key}
                          type="button"
                          className={`${styles.quickFolderChip} ${customFolderPath === fpath ? styles.quickFolderChipActive : ''}`}
                          onClick={() => {
                            setCustomFolderPath(fpath)
                            localStorage.setItem('ytsub_export_folder', fpath)
                          }}
                          title={fpath}
                        >
                          {key === 'desktop' ? '🖥️ Desktop' : key === 'videos' ? '🎬 Videos' : key === 'downloads' ? '📥 Downloads' : `📁 ${key}`}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Export Success Notification Banner */}
            {exportSuccessInfo && (
              <div className={styles.exportSuccessCard}>
                <CheckCircle2 size={20} color="#86EFAC" style={{ flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, color: '#86EFAC', fontSize: '0.9rem' }}>
                    Export Completed Successfully!
                  </div>
                  {exportSuccessInfo.full_path ? (
                    <div style={{ fontSize: '0.8rem', color: '#E2E8F0', marginTop: 4, wordBreak: 'break-all' }}>
                      Saved to:{' '}
                      <code className={styles.savedPathCode}>{exportSuccessInfo.full_path}</code>
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.8rem', color: '#E2E8F0', marginTop: 4 }}>
                      Saved as: <strong>{exportSuccessInfo.filename}</strong> inside your chosen folder location.
                    </div>
                  )}
                </div>
                {exportSuccessInfo.full_path && (
                  <div style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className={styles.openExplorerBtn}
                      onClick={() => handleOpenExplorer(exportSuccessInfo.full_path)}
                      title="Open in Windows File Explorer"
                    >
                      <FolderOpen size={14} /> Open Folder
                    </button>
                    <button
                      type="button"
                      className={styles.copyPathBtn}
                      onClick={() => {
                        navigator.clipboard.writeText(exportSuccessInfo.full_path)
                        setCopiedSavedPath(true)
                        setTimeout(() => setCopiedSavedPath(false), 2000)
                      }}
                      title="Copy file path"
                    >
                      {copiedSavedPath ? <Check size={14} /> : <Copy size={14} />}
                      {copiedSavedPath ? 'Copied' : 'Copy Path'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Cards Grid: Symmetrical for Landscape or Portrait sources */}
            {(formatModalJob.orientation !== 'portrait' && formatModalJob.input?.orientation !== 'portrait') ? (
              /* LANDSCAPE SOURCE (Standard YouTube video) */
              <div className={styles.formatGrid}>
                {/* 1. Shorts Letterbox (Fit & Center) — RECOMMENDED */}
                <div className={`${styles.formatCard} ${styles.formatCardRecommended}`}>
                  <span className={`${styles.formatBadge} ${styles.formatBadgeGold}`}>
                    9:16 SHORTS • FIT &amp; CENTER (RECOMMENDED)
                  </span>
                  <div className={styles.aspectDiagramWrap}>
                    <div className={styles.phoneFrame}>
                      <div className={styles.diagramVideoLetterbox}>
                        <span style={{ fontSize: '6px', color: '#94A3B8' }}>VIDEO</span>
                        <span className={styles.diagramSubtitleSample}>CAPTIONS</span>
                      </div>
                    </div>
                  </div>
                  <h4 className={styles.formatTitle}>YouTube Shorts (Fit)</h4>
                  <p className={styles.formatDesc}>
                    Adds <strong>black layers top &amp; bottom</strong>. 100% of your video frames and subtitles
                    remain visible in the center. <strong>Zero frames cut or destroyed.</strong>
                  </p>
                  <button
                    type="button"
                    className={`${styles.formatBtn} ${styles.formatBtnPrimary}`}
                    onClick={() => handleExportAndDownload('9:16', 'letterbox')}
                    disabled={isReformatting}
                  >
                    <Download size={16} /> Export 9:16 Shorts (Fit)
                  </button>
                </div>

                {/* 2. Shorts Center Crop (Full-Screen) */}
                <div className={styles.formatCard}>
                  <span className={`${styles.formatBadge} ${styles.formatBadgeCyan}`}>
                    9:16 SHORTS • FULLSCREEN CROP
                  </span>
                  <div className={styles.aspectDiagramWrap}>
                    <div className={styles.phoneFrame}>
                      <div className={styles.diagramVideoCrop}>
                        <span style={{ fontSize: '7px', color: '#94A3B8' }}>FULL SCREEN</span>
                        <span className={styles.diagramSubtitleSample}>CAPTIONS</span>
                      </div>
                    </div>
                  </div>
                  <h4 className={styles.formatTitle}>YouTube Shorts (Crop)</h4>
                  <p className={styles.formatDesc}>
                    Fills the vertical phone screen edge-to-edge by <strong>zooming &amp; cropping</strong> the
                    left and right sides. Best when speakers stay in the center.
                  </p>
                  <button
                    type="button"
                    className={`${styles.formatBtn} ${styles.formatBtnCyan}`}
                    onClick={() => handleExportAndDownload('9:16', 'crop')}
                    disabled={isReformatting}
                  >
                    <Download size={16} /> Export 9:16 Shorts (Crop)
                  </button>
                </div>

                {/* 3. Original Landscape (Native) */}
                <div className={styles.formatCard}>
                  <span className={`${styles.formatBadge} ${styles.formatBadgeMuted}`}>
                    16:9 • NATIVE WIDESCREEN
                  </span>
                  <div className={styles.aspectDiagramWrap}>
                    <div className={styles.desktopFrame}>
                      <div className={styles.diagramVideoNative}>
                        <span style={{ fontSize: '7px', color: '#94A3B8' }}>ORIGINAL 16:9</span>
                        <span className={styles.diagramSubtitleSample}>CAPTIONS</span>
                      </div>
                    </div>
                  </div>
                  <h4 className={styles.formatTitle}>Original Landscape</h4>
                  <p className={styles.formatDesc}>
                    Original wide aspect ratio ({formatModalJob.width || formatModalJob.input?.width || 1280}×
                    {formatModalJob.height || formatModalJob.input?.height || 720}). Best for standard YouTube long-form, laptop, and TV
                    viewing.
                  </p>
                  <button
                    type="button"
                    className={`${styles.formatBtn} ${styles.formatBtnSecondary}`}
                    onClick={() => handleExportAndDownload('original')}
                    disabled={isReformatting}
                  >
                    <Download size={16} /> Download Original (Instant)
                  </button>
                </div>
              </div>
            ) : (
              /* PORTRAIT SOURCE (Already Vertical) */
              <div className={styles.formatGrid}>
                {/* 1. Original 9:16 Portrait — RECOMMENDED */}
                <div className={`${styles.formatCard} ${styles.formatCardRecommended}`}>
                  <span className={`${styles.formatBadge} ${styles.formatBadgeGold}`}>
                    9:16 SHORTS • NATIVE (RECOMMENDED)
                  </span>
                  <div className={styles.aspectDiagramWrap}>
                    <div className={styles.phoneFrame}>
                      <div className={styles.diagramVideoCrop}>
                        <span style={{ fontSize: '7px', color: '#94A3B8' }}>NATIVE 9:16</span>
                        <span className={styles.diagramSubtitleSample}>CAPTIONS</span>
                      </div>
                    </div>
                  </div>
                  <h4 className={styles.formatTitle}>Original 9:16 Shorts</h4>
                  <p className={styles.formatDesc}>
                    Original vertical resolution ({formatModalJob.width || formatModalJob.input?.width || 1080}×
                    {formatModalJob.height || formatModalJob.input?.height || 1920}). Tailor-made for YouTube Shorts, Instagram Reels, and
                    TikTok.
                  </p>
                  <button
                    type="button"
                    className={`${styles.formatBtn} ${styles.formatBtnPrimary}`}
                    onClick={() => handleExportAndDownload('original')}
                    disabled={isReformatting}
                  >
                    <Download size={16} /> Download Original 9:16
                  </button>
                </div>

                {/* 2. 16:9 Landscape Pillarbox (Fit) */}
                <div className={styles.formatCard}>
                  <span className={`${styles.formatBadge} ${styles.formatBadgeCyan}`}>
                    16:9 WIDESCREEN • PILLARBOX
                  </span>
                  <div className={styles.aspectDiagramWrap}>
                    <div className={styles.desktopFrame} style={{ justifyContent: 'center' }}>
                      <div style={{ width: '42px', height: '100%', background: '#334155', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <span className={styles.diagramSubtitleSample}>CAPTIONS</span>
                      </div>
                    </div>
                  </div>
                  <h4 className={styles.formatTitle}>16:9 YouTube (Pillarbox)</h4>
                  <p className={styles.formatDesc}>
                    Pads the sides with black bars to convert vertical video into widescreen 16:9 without
                    clipping frames.
                  </p>
                  <button
                    type="button"
                    className={`${styles.formatBtn} ${styles.formatBtnCyan}`}
                    onClick={() => handleExportAndDownload('16:9', 'letterbox')}
                    disabled={isReformatting}
                  >
                    <Download size={16} /> Export 16:9 (Pillarbox)
                  </button>
                </div>

                {/* 3. 16:9 Landscape Center Crop */}
                <div className={styles.formatCard}>
                  <span className={`${styles.formatBadge} ${styles.formatBadgeMuted}`}>
                    16:9 WIDESCREEN • CROP
                  </span>
                  <div className={styles.aspectDiagramWrap}>
                    <div className={styles.desktopFrame}>
                      <div className={styles.diagramVideoNative}>
                        <span style={{ fontSize: '7px', color: '#94A3B8' }}>CROP 16:9</span>
                        <span className={styles.diagramSubtitleSample}>CAPTIONS</span>
                      </div>
                    </div>
                  </div>
                  <h4 className={styles.formatTitle}>16:9 YouTube (Crop)</h4>
                  <p className={styles.formatDesc}>
                    Center-crops the vertical video to fill a standard 16:9 widescreen canvas.
                  </p>
                  <button
                    type="button"
                    className={`${styles.formatBtn} ${styles.formatBtnSecondary}`}
                    onClick={() => handleExportAndDownload('16:9', 'crop')}
                    disabled={isReformatting}
                  >
                    <Download size={16} /> Export 16:9 (Crop)
                  </button>
                </div>
              </div>
            )}

            {/* Modal Bottom Notice */}
            <div className={styles.modalNotice}>
              <CheckCircle2 size={16} color="#86EFAC" />
              <span>
                <strong>Lossless Audio &amp; Subtitle Preservation:</strong> Subtitles are already rendered directly onto the video frames. Audio tracks are copied losslessly without re-compression.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
