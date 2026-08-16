// 消息气泡：用户/助手消息，助手消息用 Markdown 渲染并内嵌异步任务结果与历史附件
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

// 把文本中的裸图片 URL 转成 markdown 图片语法，交给 ReactMarkdown 渲染为 <img>
function renderAssistantContent(text: string): string {
  // 负向后顾 (?<!\]\() 跳过已是 markdown 图片语法的 url，避免重复包裹
  return text.replace(/(?<!\]\()(https?:\/\/[^\s)"'<>，。；：！？、]+)/g, (url) =>
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

  return (
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
  )
}
