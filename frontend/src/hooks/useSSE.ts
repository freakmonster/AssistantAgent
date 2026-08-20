// SSE 流式接收：fetch + ReadableStream 解析事件，驱动消息与任务状态
import { useCallback, useRef } from 'react'
import { getAuthToken } from '../services/api'
import { useMessageStore } from '../stores/messageStore'
import { useSessionStore } from '../stores/sessionStore'
import { useSettingsStore } from '../stores/settingsStore'
import { useTaskStore } from '../stores/taskStore'
import type { ToolCall, ToolPayload } from '../types'

// 发送消息时可携带的附件（file_id + 文件名）
export interface SendAttachment {
  file_id: string
  filename: string
}

function genId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// 判断是否为用户主动中断（AbortError），区别于网络/服务错误
function isAbortError(e: unknown): boolean {
  return e instanceof DOMException && e.name === 'AbortError'
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
  const removeMessage = useMessageStore((s) => s.removeMessage)
  const registerTask = useTaskStore((s) => s.registerTask)

  // 当前请求的 AbortController，stop() 时中断 fetch，进而断开 SSE、取消后端生成
  const controllerRef = useRef<AbortController | null>(null)
  // 上一轮「user + assistant」消息 id 对：暂停后保留，重生成时清掉半截
  const pendingPairRef = useRef<{ userId: string; assistantId: string } | null>(null)

  const sendMessage = useCallback(
    async (sessionId: string, message: string, attachments?: SendAttachment[]) => {
      // 重生成前清理上一次被暂停的半截（user + assistant 成对清掉）
      if (pendingPairRef.current) {
        removeMessage(pendingPairRef.current.assistantId)
        removeMessage(pendingPairRef.current.userId)
        pendingPairRef.current = null
      }

      // 先落库：用户消息 + 空的 assistant 消息（流式填充目标）
      const userId = genId()
      const assistantId = genId()
      pendingPairRef.current = { userId, assistantId }
      addMessage({
        id: userId,
        role: 'user',
        content: message,
        // 附件以 file 类型挂到用户消息上，气泡用 AttachmentCard 渲染
        attachments: (attachments ?? []).map((a) => ({
          type: 'file' as const,
          file_id: a.file_id,
          filename: a.filename,
        })),
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

      let aborted = false
      const controller = new AbortController()
      controllerRef.current = controller
      try {
        const res = await fetch('/api/v1/chat/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${getAuthToken() ?? ''}`,
          },
          body: JSON.stringify({
            session_id: sessionId,
            message,
            attachments: (attachments ?? []).map((a) => a.file_id),
            model: useSettingsStore.getState().model || undefined,
          }),
          signal: controller.signal,
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
        if (isAbortError(e)) {
          // 用户主动暂停：保留已生成的半截内容，不追加错误提示
          aborted = true
        } else {
          appendContent(
            assistantId,
            `\n[请求失败：${e instanceof Error ? e.message : String(e)}]`,
          )
        }
      } finally {
        controllerRef.current = null
        // 正常完整结束才清标记；暂停则保留，待下次重生成时清掉半截
        if (!aborted) {
          pendingPairRef.current = null
        }
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
      removeMessage,
      registerTask,
    ],
  )

  // 停止当前生成：中断 fetch，触发后端协程取消
  const stop = useCallback(() => {
    controllerRef.current?.abort()
  }, [])

  return { sendMessage, stop }
}
