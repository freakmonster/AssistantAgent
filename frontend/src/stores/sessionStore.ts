// 会话状态：会话列表与当前会话
import { create } from 'zustand'
import { sessionApi } from '../services/api'
import type { Session } from '../types'

// 会话排序：置顶优先，其次按更新时间倒序（最新在前）
function sortSessions(sessions: Session[]): Session[] {
  return [...sessions].sort((a, b) => {
    if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })
}

interface SessionState {
  sessions: Session[]
  currentSessionId: string | null
  loading: boolean
  fetchSessions: () => Promise<void>
  startNewChat: () => void
  ensureSession: (title: string) => Promise<string | null>
  setCurrentSession: (id: string | null) => void
  renameSession: (id: string, title: string) => Promise<void>
  togglePin: (id: string) => Promise<void>
  deleteSession: (id: string) => Promise<void>
  cleanupEmptySessions: () => Promise<void>
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  loading: false,
  fetchSessions: async () => {
    set({ loading: true })
    try {
      const sessions = await sessionApi.list()
      set({ sessions: sortSessions(sessions), loading: false })
    } catch (e) {
      set({ loading: false })
      console.error('获取会话列表失败', e)
    }
  },
  // 进入“新对话”草稿态：不立即创建后端会话，等发送首条消息时再建
  startNewChat: () => set({ currentSessionId: null }),
  // 确保存在真实会话：当前为草稿态时按标题创建，否则复用当前会话 id
  ensureSession: async (title) => {
    const current = get().currentSessionId
    if (current) return current
    try {
      const session = await sessionApi.create(title)
      set((state) => ({
        sessions: sortSessions([session, ...state.sessions]),
        currentSessionId: session.id,
      }))
      return session.id
    } catch (e) {
      console.error('创建会话失败', e)
      return null
    }
  },
  setCurrentSession: (id) => set({ currentSessionId: id }),
  renameSession: async (id, title) => {
    try {
      await sessionApi.rename(id, title)
      set((state) => ({
        sessions: state.sessions.map((s) => (s.id === id ? { ...s, title } : s)),
      }))
    } catch (e) {
      console.error('重命名会话失败', e)
    }
  },
  togglePin: async (id) => {
    try {
      await sessionApi.togglePin(id)
      // 置顶会改变排序，重新拉取列表保证顺序正确
      await get().fetchSessions()
    } catch (e) {
      console.error('切换置顶失败', e)
    }
  },
  deleteSession: async (id) => {
    try {
      await sessionApi.delete(id)
      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== id),
        currentSessionId:
          state.currentSessionId === id ? null : state.currentSessionId,
      }))
    } catch (e) {
      console.error('删除会话失败', e)
    }
  },
  cleanupEmptySessions: async () => {
    const emptyIds = get()
      .sessions.filter((s) => s.message_count === 0)
      .map((s) => s.id)
    if (emptyIds.length === 0) return
    await Promise.all(
      emptyIds.map((id) => sessionApi.delete(id).catch(() => null)),
    )
    await get().fetchSessions()
  },
}))
