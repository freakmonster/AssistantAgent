// 消息状态：当前会话的消息列表与流式状态
import { create } from 'zustand'
import { messageApi } from '../services/api'
import type { ChatMessage, ToolCall, ToolCallStatus } from '../types'

interface MessageState {
  messages: ChatMessage[]
  streaming: boolean
  addMessage: (message: ChatMessage) => void
  appendContent: (id: string, chunk: string) => void
  setToolCalls: (id: string, toolCalls: ToolCall[]) => void
  setToolCallStatus: (id: string, status: ToolCallStatus) => void
  setTaskId: (id: string, taskId: string) => void
  setMessages: (messages: ChatMessage[]) => void
  loadHistory: (sessionId: string) => Promise<void>
  clearMessages: () => void
  setStreaming: (streaming: boolean) => void
}

export const useMessageStore = create<MessageState>((set) => ({
  messages: [],
  streaming: false,
  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),
  appendContent: (id, chunk) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + chunk } : m,
      ),
    })),
  setToolCalls: (id, toolCalls) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, toolCalls, toolCallStatus: 'running' } : m,
      ),
    })),
  setToolCallStatus: (id, status) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, toolCallStatus: status } : m,
      ),
    })),
  setTaskId: (id, taskId) =>
    set((state) => ({
      messages: state.messages.map((m) => (m.id === id ? { ...m, taskId } : m)),
    })),
  setMessages: (messages) => set({ messages }),
  loadHistory: async (sessionId) => {
    try {
      const list = await messageApi.list(sessionId)
      const messages: ChatMessage[] = list.map((m) => ({
        id: m.id,
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content ?? '',
        toolCalls: m.tool_calls ?? undefined,
        // 历史消息已落库，必然是完成态；补上状态，避免卡片回退默认值显示“执行中”
        toolCallStatus: m.tool_calls?.length ? 'success' : undefined,
        attachments: m.attachments ?? undefined,
        createdAt: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
      }))
      set({ messages })
    } catch (e) {
      console.error('加载历史消息失败', e)
      set({ messages: [] })
    }
  },
  clearMessages: () => set({ messages: [] }),
  setStreaming: (streaming) => set({ streaming }),
}))
