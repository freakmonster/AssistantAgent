// 用户状态：token 与用户信息
import { create } from 'zustand'
import { setAuthToken, userApi } from '../services/api'
import type { User } from '../types'

const TOKEN_KEY = 'agent_token'
const LAST_SESSION_KEY = 'agent_last_session'

function loadToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function loadLastSession(): string | null {
  try {
    return localStorage.getItem(LAST_SESSION_KEY)
  } catch {
    return null
  }
}

const initialToken = loadToken()
setAuthToken(initialToken)

interface UserState {
  token: string | null
  user: User | null
  lastSessionId: string | null
  setAuth: (token: string, user: User | null) => void
  setLastSessionId: (id: string | null) => void
  fetchMe: () => Promise<void>
  logout: () => void
}

export const useUserStore = create<UserState>((set, get) => ({
  token: initialToken,
  user: null,
  lastSessionId: loadLastSession(),
  setAuth: (token, user) => {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      // 忽略存储失败，token 仍保留在内存中
    }
    setAuthToken(token)
    set({ token, user })
  },
  setLastSessionId: (id) => {
    try {
      if (id) {
        localStorage.setItem(LAST_SESSION_KEY, id)
      } else {
        localStorage.removeItem(LAST_SESSION_KEY)
      }
    } catch {
      // 忽略存储失败
    }
    set({ lastSessionId: id })
  },
  fetchMe: async () => {
    // 刷新页面后 token 仍在，但 user 信息丢失，从后端重新拉取
    if (!get().token) return
    try {
      const user = await userApi.me()
      set({ user })
    } catch {
      // token 失效或接口不可用时忽略，保持 user 为 null
    }
  },
  logout: () => {
    try {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(LAST_SESSION_KEY)
    } catch {
      // 忽略存储失败
    }
    setAuthToken(null)
    set({ token: null, user: null, lastSessionId: null })
  },
}))
