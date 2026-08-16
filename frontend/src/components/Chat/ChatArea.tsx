// 聊天区：消息列表 + 智能滚动，并挂载任务轮询
import { useEffect, useRef } from 'react'
import { useTaskPolling } from '../../hooks/useTaskPolling'
import { useMessageStore } from '../../stores/messageStore'
import { EmptyWelcome } from './EmptyWelcome'
import { MessageBubble } from './MessageBubble'

export function ChatArea() {
  const messages = useMessageStore((s) => s.messages)
  const streaming = useMessageStore((s) => s.streaming)
  const containerRef = useRef<HTMLDivElement>(null)
  const autoScrollRef = useRef(true)

  // 挂载任务轮询（对 type=task 产生的异步任务定时拉取结果）
  useTaskPolling()

  // 监听用户滚动：离开底部则暂停自动滚动（智能滚动）
  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    autoScrollRef.current = nearBottom
  }

  useEffect(() => {
    if (autoScrollRef.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages])

  return (
    <div className="chat-area" ref={containerRef} onScroll={handleScroll}>
      {messages.length === 0 && <EmptyWelcome />}
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} streaming={streaming} />
      ))}
    </div>
  )
}
