// 消息气泡：用户/助手消息，助手消息用 Markdown 渲染并内嵌异步任务结果与历史附件
import { CopyOutlined } from '@ant-design/icons'
import { useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTaskStore } from '../../stores/taskStore'
import type { ChatMessage } from '../../types'
import { AttachmentCard } from '../tasks/AttachmentCard'
import { TaskCard } from '../tasks/TaskCard'
import { ToolCallCard } from './ToolCallCard'

// 图片 URL 启发式判断：扩展名白名单 + 智谱媒体域名白名单
const IMAGE_EXT = /\.(png|jpe?g|webp|gif)(\?|$)/i
const VIDEO_EXT = /\.(mp4|mov|webm|m4v)(\?|$)/i
const IMAGE_DOMAINS = ['ufileos.com', 'maas-watermark-prod']

function isImageUrl(url: string): boolean {
  try {
    const u = new URL(url)
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return false
    if (VIDEO_EXT.test(u.pathname)) return false
    if (IMAGE_EXT.test(u.pathname)) return true
    return IMAGE_DOMAINS.some((d) => u.hostname.includes(d))
  } catch {
    return false
  }
}

// 把文本中的图片 URL 转成 markdown 图片语法，交给 ReactMarkdown 渲染为 <img>
function renderAssistantContent(text: string): string {
  // 兜底 1：处理 fenced code block（``` ```）内只含图片 URL 的情况，
  // 去掉代码块与反引号标记，替换为图片语法
  text = text.replace(
    /```[^\n]*\n\s*`?(https?:\/\/[^\s`]+)`?\s*\n```/g,
    (whole, url) => (isImageUrl(url) ? `\n![图片](${url})\n` : whole),
  )

  // 兜底 2：处理 inline code（`url`）包裹的图片 URL，去掉反引号并渲染为图片
  text = text.replace(/`(https?:\/\/[^\s`]+)`/g, (whole, url) =>
    isImageUrl(url) ? `\n![图片](${url})\n` : whole,
  )

  // 通用：裸 URL 转图片（负向后顾跳过已是 markdown 图片语法的 url，排除反引号）
  return text.replace(/(?<!\]\()(https?:\/\/[^\s)"'<>，。；：！？、`]+)/g, (url) =>
    isImageUrl(url) ? `\n![图片](${url})\n` : url,
  )
}

interface MessageBubbleProps {
  message: ChatMessage
  streaming?: boolean
}

export function MessageBubble({ message, streaming }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  // 关联的异步任务（type=task 时由 useSSE 写入 message.taskId）
  const task = useTaskStore((s) =>
    message.taskId ? s.tasks[message.taskId] : undefined,
  )
  // 复制状态：复制成功后短暂显示“已复制”
  const [copied, setCopied] = useState(false)
  const copyTimer = useRef<number | null>(null)

  const handleCopy = async () => {
    const text = message.content ?? ''
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      if (copyTimer.current) window.clearTimeout(copyTimer.current)
      copyTimer.current = window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // 剪贴板不可用（如非 HTTPS）时静默忽略
    }
  }

  return (
    <div className={`message-row ${isUser ? 'message-row-user' : 'message-row-assistant'}`}>
      <div className={`message-bubble ${isUser ? 'message-user' : 'message-assistant'}`}>
        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolCallCard
            toolCalls={message.toolCalls}
            status={message.toolCallStatus}
          />
        )}
        {message.content && (
          <div className="message-content">
            {isUser ? (
              <span>{message.content}</span>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {renderAssistantContent(message.content)}
              </ReactMarkdown>
            )}
          </div>
        )}
        {/* 历史消息附件（视频/图片等已完成的媒体） */}
        {message.attachments?.map((a, i) => (
          <AttachmentCard key={`${message.id}-${i}`} attachment={a} />
        ))}
        {task && <TaskCard task={task} />}
        {streaming && !message.content && !message.toolCalls && !message.attachments && (
          <div className="message-typing">正在思考…</div>
        )}
      </div>
      {/* 复制按钮：位于气泡之外，仅在有文本内容时显示 */}
      {message.content && (
        <button
          className="message-copy-btn"
          onClick={() => void handleCopy()}
          aria-label="复制"
        >
          <CopyOutlined />
          <span>{copied ? '已复制' : '复制'}</span>
        </button>
      )}
    </div>
  )
}
