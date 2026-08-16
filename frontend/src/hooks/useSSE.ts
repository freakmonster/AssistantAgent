// SSE 流式接收：fetch + ReadableStream 解析事件，驱动消息与任务状态
import { useCallback } from 'react'
import { getAuthToken } from '../services/api'
import { useMessageStore } from '../stores/messageStore'
import { useSessionStore } from '../stores/sessionStore'
import { useTaskStore } from '../stores/taskStore'
import type { ToolCall, ToolPayload } from '../types'

function genId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// 解析单个 SSE 帧为 { event, data }
function parseFrame(frame: string): { event: string; data: string } {
  let event = 'message'
  let data = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      data += line.slice(5).trim()
    }
  }
  return { event, data }
}

export function useSSE() {
  const addMessage = useMessageStore((s) => s.addMessage)
  const appendContent = useMessageStore((s) => s.appendContent)
  const setToolCalls = useMessageStore((s) => s.setToolCalls)
  const setToolCallStatus = useMessageStore((s) => s.setToolCallStatus)
  const setTaskId = useMessageStore((s) => s.setTaskId)
  const setStreaming = useMessageStore((s) => s.setStreaming)
  const registerTask = useTaskStore((s) => s.registerTask)

  const sendMessage = useCallback(
    async (sessionId: string, message: string) => {
      // 先落库：用户消息 + 空的 assistant 消息（流式填充目标）
      const assistantId = genId()
      addMessage({
        id: genId(),
        role: 'user',
        content: message,
        createdAt: Date.now(),
      })
      addMessage({
        id: assistantId,
        role: 'assistant',
        content: '',
        createdAt: Date.now(),
      })
      setStreaming(true)

      // 累积本次 assistant 消息的工具调用（跨多个 tool_call 事件合并）
      let accumulatedCalls: ToolCall[] = []

      const processToolResult = (raw: unknown) => {
        // 工具结果统一为 JSON 字符串，失败/任务/普通结果据此分类
        let payload: ToolPayload | null = null
        if (typeof raw === 'string') {
          try {
            payload = JSON.parse(raw) as ToolPayload
          } catch {
            payload = null
          }
        }
        if (!payload) {
          setToolCallStatus(assistantId, 'success')
          return
        }
        if (payload.error) {
          setToolCallStatus(assistantId, 'failed')
        } else if (payload.type === 'task' && payload.task_id) {
          registerTask(payload.task_id)
          setTaskId(assistantId, payload.task_id)
          setToolCallStatus(assistantId, 'success')
        } else {
          setToolCallStatus(assistantId, 'success')
        }
      }

      const processUpdate = (data: unknown) => {
        // update 事件：遍历各节点返回，识别 tools 节点的 ToolMessage
        if (!data || typeof data !== 'object') return
        for (const nodeValue of Object.values(data as Record<string, unknown>)) {
          if (!nodeValue || typeof nodeValue !== 'object') continue
          const messages = (nodeValue as { messages?: unknown[] }).messages
          if (!Array.isArray(messages)) continue
          for (const msg of messages) {
            const m = msg as { type?: string; content?: unknown }
            if (m?.type === 'tool') processToolResult(m.content)
          }
        }
      }

      const handleEvent = (event: string, data: unknown) => {
        switch (event) {
          case 'text': {
            const content = (data as { content?: string })?.content ?? ''
            if (content) appendContent(assistantId, content)
            break
          }
          case 'tool_call': {
            const calls = ((data as { tool_calls?: ToolCall[] })?.tool_calls ?? [])
            for (const c of calls) {
              const idx = accumulatedCalls.findIndex((x) => x.id === c.id)
              if (idx >= 0) {
                // 流式下同一调用会多次下发，后续 chunk 的 args 更完整，需覆盖而非丢弃
                accumulatedCalls = accumulatedCalls.map((x, i) =>
                  i === idx ? { ...x, ...c } : x,
                )
              } else {
                accumulatedCalls = [...accumulatedCalls, c]
              }
            }
            setToolCalls(assistantId, accumulatedCalls)
            break
          }
          case 'update': {
            processUpdate(data)
            break
          }
          case 'error': {
            const err = (data as { error?: string })?.error ?? '未知错误'
            appendContent(assistantId, `\n[请求出错：${err}]`)
            setToolCallStatus(assistantId, 'failed')
            break
          }
          default:
            break
        }
      }

      try {
        const res = await fetch('/api/v1/chat/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${getAuthToken() ?? ''}`,
          },
          body: JSON.stringify({ session_id: sessionId, message }),
        })
        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split('\n\n')
          buffer = frames.pop() ?? ''
          for (const frame of frames) {
            const { event, data } = parseFrame(frame)
            if (!data) continue
            try {
              handleEvent(event, JSON.parse(data))
            } catch {
              // 忽略无法解析的帧
            }
          }
        }
      } catch (e) {
        appendContent(
          assistantId,
          `\n[请求失败：${e instanceof Error ? e.message : String(e)}]`,
        )
      } finally {
        setStreaming(false)
        // 对话落库后刷新会话列表，让侧边栏标题（首条消息自动命名）立即更新
        void useSessionStore.getState().fetchSessions()
      }
    },
    [
      addMessage,
      appendContent,
      setToolCalls,
      setToolCallStatus,
      setTaskId,
      setStreaming,
      registerTask,
    ],
  )

  return { sendMessage }
}
