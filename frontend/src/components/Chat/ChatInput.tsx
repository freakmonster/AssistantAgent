// 输入区：外轮廓内分上下两部分（文字输入 + 底部工具栏），发送触发 SSE 流式对话
import { useRef, useState, type ChangeEvent } from 'react'
import { useSSE } from '../../hooks/useSSE'
import { useMessageStore } from '../../stores/messageStore'
import { useSessionStore } from '../../stores/sessionStore'

interface ChatInputProps {
  sessionId: string | null
}

// 生成会话标题：与后端 _gen_session_title 保持一致（去空白、截前 9 字）
function genTitle(message: string): string {
  const text = message.trim().replace(/\s+/g, ' ')
  if (!text) return '新对话'
  return text.slice(0, 9) + (text.length > 9 ? '…' : '')
}

// 文字输入区最高高度，超出后滚动条只在文字区（上半部分）出现
const MAX_TEXTAREA_HEIGHT = 600

export function ChatInput({ sessionId }: ChatInputProps) {
  const [text, setText] = useState('')
  const streaming = useMessageStore((s) => s.streaming)
  const ensureSession = useSessionStore((s) => s.ensureSession)
  const { sendMessage } = useSSE()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  // 防重入：ensureSession 异步创建会话期间，避免双击重复发送
  const sendingRef = useRef(false)

  // 文字区高度随行数动态增高，最高 600px
  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`
    }
  }

  const handleSend = async () => {
    const content = text.trim()
    if (!content || streaming || sendingRef.current) return
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
      void sendMessage(sid, content)
    } finally {
      sendingRef.current = false
    }
  }

  return (
    <div className="chat-input">
      <div className="chat-input-box">
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
          placeholder="畅所欲言"
          rows={1}
        />
        <div className="chat-input-toolbar">
          {/* 预留：文件上传按钮 */}
          {/* 预留：对话模型选择按钮 */}
          <button
            onClick={handleSend}
            disabled={streaming || !text.trim()}
            aria-label="发送"
          >
            {streaming ? (
              <span className="chat-send-dots">…</span>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
