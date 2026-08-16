// 用户状态：token 与用户信息
import { create } from 'zustand'
import { setAuthToken } from '../services/api'
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
  logout: () => void
}

export const useUserStore = create<UserState>((set) => ({
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
