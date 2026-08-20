// 输入区：外轮廓内分上下两部分（文字输入 + 底部工具栏），发送触发 SSE 流式对话。
// 支持文件上传：选择 → 上传 → 轮询解析状态（ready 后才可发送），附件以 chip 展示。
import { useRef, useState, type ChangeEvent } from 'react'
import { AudioOutlined } from '@ant-design/icons'
import { useSSE } from '../../hooks/useSSE'
import { audioApi, filesApi, taskApi } from '../../services/api'
import { useMessageStore } from '../../stores/messageStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useTranslation } from '../../stores/settingsStore'
import type { PendingFile } from '../../types'

interface ChatInputProps {
  sessionId: string | null
}

// 支持的附件类型（与后端 SUPPORTED_TYPES 对应）
const ACCEPT_TYPES = '.txt,.md,.json,.csv,.py,.pdf,.docx,.xlsx,.jpg,.jpeg,.png,.bmp'

// 单文件大小上限（字节，与后端 settings.FILE_MAX_SIZE 一致），用于上传前本地预校验
const MAX_FILE_SIZE = 20 * 1024 * 1024

// 生成会话标题：与后端 _gen_session_title 保持一致（去空白、截前 9 字）
function genTitle(message: string): string {
  const text = message.trim().replace(/\s+/g, ' ')
  if (!text) return '新对话'
  return text.slice(0, 9) + (text.length > 9 ? '…' : '')
}

// 文字输入区最高高度，超出后滚动条只在文字区（上半部分）出现
const MAX_TEXTAREA_HEIGHT = 600

// 解析状态轮询间隔（毫秒）
const POLL_INTERVAL_MS = 2000

// 语音录音最大时长（秒），与后端 30s 双层限制一致
const MAX_RECORD_SECONDS = 30

export function ChatInput({ sessionId }: ChatInputProps) {
  const [text, setText] = useState('')
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
  // 上传超限等错误提示（自动消失的红色提示条）
  const [errorTip, setErrorTip] = useState<string | null>(null)
  // 气泡提示（输入框上方浮现，如「未识别到文字」），与错误提示条区分
  const [toast, setToast] = useState<string | null>(null)
  const streaming = useMessageStore((s) => s.streaming)
  const ensureSession = useSessionStore((s) => s.ensureSession)
  const { t } = useTranslation()
  const { sendMessage, stop } = useSSE()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 防重入：ensureSession 异步创建会话期间，避免双击重复发送
  const sendingRef = useRef(false)
  // 错误提示自动消失的定时器句柄
  const errorTipTimer = useRef<number | null>(null)
  // 气泡提示自动消失的定时器句柄
  const toastTimer = useRef<number | null>(null)
  // 语音录音相关状态与引用
  const [recording, setRecording] = useState(false)
  const [recordingRemain, setRecordingRemain] = useState(MAX_RECORD_SECONDS)
  const [transcribing, setTranscribing] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const recordCountdownRef = useRef<number | null>(null)
  const remainingRef = useRef(MAX_RECORD_SECONDS)

  // 显示错误提示，5 秒后自动清除（后出现的提示会覆盖先前的定时器）
  const showErrorTip = (msg: string) => {
    setErrorTip(msg)
    if (errorTipTimer.current) window.clearTimeout(errorTipTimer.current)
    errorTipTimer.current = window.setTimeout(() => setErrorTip(null), 5000)
  }

  // 显示气泡提示（输入框上方浮现，3 秒后渐隐消失）
  const showToast = (msg: string) => {
    setToast(msg)
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 3000)
  }

  // 文字区高度随行数动态增高，最高 600px
  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`
    }
  }

  // 更新某个附件的状态（按 file_id 定位）
  const updatePendingFile = (fileId: string, patch: Partial<PendingFile>) => {
    setPendingFiles((prev) =>
      prev.map((f) => (f.file_id === fileId ? { ...f, ...patch } : f)),
    )
  }

  // 删除附件（失败/多余文件）
  const removePendingFile = (fileId: string) => {
    setPendingFiles((prev) => prev.filter((f) => f.file_id !== fileId))
  }

  // 轮询解析任务，parsing → ready/failed
  const pollParseStatus = (file: PendingFile) => {
    if (!file.task_id) return
    const timer = window.setInterval(async () => {
      try {
        const resp = await taskApi.get(file.task_id!)
        // 任务执行失败（异常退出）：直接标红
        if (resp.status === 'failed') {
          window.clearInterval(timer)
          updatePendingFile(file.file_id, {
            status: 'failed',
            error: '解析任务执行失败',
          })
          return
        }
        // 任务正常完成：需看 result.ok 判断解析是否真正成功
        if (resp.status === 'complete') {
          window.clearInterval(timer)
          const result = resp.result as { ok?: boolean; error?: string } | null
          if (result && result.ok === false) {
            // 任务正常返回但解析失败：显示红色并透出具体原因
            updatePendingFile(file.file_id, {
              status: 'failed',
              error: result.error ?? '文件解析失败',
            })
          } else {
            updatePendingFile(file.file_id, { status: 'ready' })
          }
        }
      } catch {
        // 轮询失败：保留 parsing 状态，下一轮继续
      }
    }, POLL_INTERVAL_MS)
  }

  // 选择文件后立即上传，维护 pendingFiles 状态
  const handleFileSelect = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = '' // 允许重复选择同一文件
    for (const file of files) {
      // 本地预校验大小：超限直接标记失败，不发请求（避免白传大文件）
      if (file.size > MAX_FILE_SIZE) {
        setPendingFiles((prev) => [
          ...prev,
          {
            file_id: `local-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            filename: file.name,
            status: 'failed',
            error: '文件超过大小上限（20MB）',
          },
        ])
        showErrorTip(`「${file.name}」超过 20MB，上传失败`)
        continue
      }
      try {
        const resp = await filesApi.upload(file)
        const pending: PendingFile = {
          file_id: resp.file_id,
          filename: resp.filename,
          status: 'parsing',
          task_id: resp.task_id ?? undefined,
        }
        setPendingFiles((prev) => [...prev, pending])
        if (resp.task_id) pollParseStatus(pending)
      } catch (err) {
        // 上传失败：显示一个 failed 附件 chip，供用户删除
        setPendingFiles((prev) => [
          ...prev,
          {
            file_id: `local-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            filename: file.name,
            status: 'failed',
            error: err instanceof Error ? err.message : '上传失败',
          },
        ])
      }
    }
  }

  // 回填转写文本到输入框（追加），并同步调整 textarea 高度
  const fillText = (transcribed: string) => {
    setText((prev) => (prev ? prev + transcribed : transcribed))
    window.setTimeout(() => {
      const el = textareaRef.current
      if (el) {
        el.style.height = 'auto'
        el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`
      }
    }, 0)
  }

  // 停止录音：主动停止与 30s 自动停止共用（触发 onstop 提交转写）
  const stopRecording = () => {
    const rec = mediaRecorderRef.current
    if (rec && rec.state !== 'inactive') rec.stop()
    if (recordCountdownRef.current) {
      window.clearInterval(recordCountdownRef.current)
      recordCountdownRef.current = null
    }
    setRecording(false)
  }

  // 开始录音：申请麦克风 → MediaRecorder 采集 → 30s 自动停止
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      mediaRecorderRef.current = rec
      chunksRef.current = []
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      rec.onstop = async () => {
        // 停止所有音轨，释放麦克风
        stream.getTracks().forEach((track) => track.stop())
        const blob = new Blob(chunksRef.current, {
          type: rec.mimeType || 'audio/webm',
        })
        if (blob.size === 0) return
        setTranscribing(true)
        try {
          const { text } = await audioApi.transcribe(blob)
          if (!text) {
            showToast(t.chat.noSpeech)
          } else {
            fillText(text)
          }
        } catch (err) {
          showErrorTip(err instanceof Error ? err.message : '语音转写失败')
        } finally {
          setTranscribing(false)
        }
      }
      rec.start()
      setRecording(true)
      // 重置倒计时并每秒递减，到 0 自动停止（与后端 30s 双层限制一致）
      remainingRef.current = MAX_RECORD_SECONDS
      setRecordingRemain(MAX_RECORD_SECONDS)
      recordCountdownRef.current = window.setInterval(() => {
        remainingRef.current -= 1
        setRecordingRemain(Math.max(remainingRef.current, 0))
        if (remainingRef.current <= 0) stopRecording()
      }, 1000)
    } catch {
      showErrorTip('无法访问麦克风，请检查浏览器权限')
    }
  }

  // 语音按钮点击：未录音→开始，已录音→停止（提交转写）
  const handleVoiceClick = () => {
    if (transcribing) return
    if (recording) stopRecording()
    else startRecording()
  }

  const handleSend = async () => {
    const content = text.trim()
    // 存在未就绪附件（上传中/解析中/失败）时禁用发送
    const hasBusy = pendingFiles.some(
      (f) => f.status === 'uploading' || f.status === 'parsing',
    )
    if (!content || streaming || sendingRef.current || hasBusy) return
    sendingRef.current = true
    try {
      // 草稿态：先创建会话（用首条消息生成标题），创建成功后再发送
      let sid = sessionId
      if (!sid) {
        sid = await ensureSession(genTitle(content))
        if (!sid) return
      }
      setText('')
      const el = textareaRef.current
      if (el) el.style.height = 'auto'
      const readyFiles = pendingFiles.filter((f) => f.status === 'ready')
      void sendMessage(
        sid,
        content,
        readyFiles.map((f) => ({ file_id: f.file_id, filename: f.filename })),
      )
      // 发送成功后清空附件（历史消息已通过 SSE 落库展示）
      if (readyFiles.length) setPendingFiles([])
    } finally {
      sendingRef.current = false
    }
  }

  return (
    <div className="chat-input">
      {/* 气泡提示：输入框上方浮现，3 秒后渐隐 */}
      {toast && (
        <div className="chat-input-toast">
          <span className="chat-toast-icon">!</span>
          {toast}
        </div>
      )}
      <div className="chat-input-box">
        {/* 上传错误提示条：超限等，自动消失 */}
        {errorTip && <div className="chat-input-error-tip">{errorTip}</div>}
        {/* 待发送附件 chip 列表：解析中 / 完成 / 失败 */}
        {pendingFiles.length > 0 && (
          <div className="chat-input-attachments">
            {pendingFiles.map((f) => (
              <span
                key={f.file_id}
                className={`chat-attachment-chip chat-attachment-${f.status}`}
                title={f.error ?? f.filename}
              >
                {f.status === 'parsing' && (
                  <span className="chat-attachment-spinner" aria-label="解析中" />
                )}
                {f.status === 'ready' && <span className="chat-attachment-done">✓</span>}
                {f.status === 'failed' && (
                  <span className="chat-attachment-failed-icon" aria-label="失败">
                    ✕
                  </span>
                )}
                <span className="chat-attachment-name">{f.filename}</span>
                <button
                  className="chat-attachment-remove"
                  onClick={() => removePendingFile(f.file_id)}
                  aria-label="移除附件"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder={t.chat.inputPlaceholder}
          rows={1}
        />
        <div className="chat-input-toolbar">
          <button
            className="chat-upload-button"
            onClick={() => fileInputRef.current?.click()}
            disabled={streaming}
            aria-label="上传文件"
            title="上传文件（txt/md/csv/json/py/pdf/docx/xlsx），单个文件最大为20MB"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M16.5 6v11.5a4 4 0 01-8 0V5a2.5 2.5 0 015 0v10.5a1 1 0 01-2 0V6H10v9.5a2.5 2.5 0 005 0V5a4 4 0 00-8 0v12.5a5.5 5.5 0 0011 0V6h-1.5z" />
            </svg>
          </button>
          <button
            className={`chat-voice-button${recording ? ' recording' : ''}`}
            onClick={handleVoiceClick}
            disabled={streaming || transcribing}
            aria-label={recording ? t.chat.stopRecord : t.chat.startRecord}
            title={recording ? t.chat.stopRecord : t.chat.startRecord}
          >
            <AudioOutlined style={{ fontSize: 16 }} />
          </button>
          {/* 录音倒计时：进度条随剩余时间缩短 + 秒数 */}
          {recording && (
            <div className="chat-recording-indicator">
              <span className="chat-recording-track">
                <span
                  className="chat-recording-fill"
                  style={{ width: `${(recordingRemain / MAX_RECORD_SECONDS) * 100}%` }}
                />
              </span>
              <span className="chat-recording-countdown">{recordingRemain}s</span>
            </div>
          )}
          {/* 隐藏的文件选择框（accept 限定可上传类型） */}
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT_TYPES}
            multiple
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
          {streaming ? (
            <button
              onClick={stop}
              aria-label={t.chat.stop}
              title={t.chat.stop}
            >
              <span className="chat-stop-icon" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!text.trim() || pendingFiles.some(
                (f) => f.status === 'uploading' || f.status === 'parsing',
              )}
              aria-label={t.chat.send}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
