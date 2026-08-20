// API 客户端：统一 fetch 封装 + 各端点方法
import type { Session, TaskResult, TokenResponse, User } from '../types'

const API_BASE = '/api/v1'

// 内存中的认证 token（由 userStore 在登录/登出时同步）
let authToken: string | null = null

export function setAuthToken(token: string | null): void {
  authToken = token
}

export function getAuthToken(): string | null {
  return authToken
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    // 尽量提取后端 detail 作为错误信息
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      detail = `HTTP ${res.status} ${res.statusText}`
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// 认证接口
export const authApi = {
  login(email: string, password: string): Promise<TokenResponse> {
    return request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },
  register(email: string, password: string): Promise<TokenResponse> {
    return request<TokenResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },
}

// 会话接口
export const sessionApi = {
  list(): Promise<Session[]> {
    return request<Session[]>('/sessions')
  },
  create(title?: string): Promise<Session> {
    return request<Session>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ title }),
    })
  },
  rename(id: string, title: string): Promise<Session> {
    return request<Session>(`/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    })
  },
  togglePin(id: string): Promise<Session> {
    return request<Session>(`/sessions/${id}/pin`, { method: 'POST' })
  },
  delete(id: string): Promise<{ deleted: boolean }> {
    return request<{ deleted: boolean }>(`/sessions/${id}`, { method: 'DELETE' })
  },
}

// 任务查询响应（GET /api/v1/tasks/{task_id}）
export interface TaskStatusResponse {
  task_id: string
  status: string
  result?: TaskResult | null
}

// 任务接口
export const taskApi = {
  get(taskId: string): Promise<TaskStatusResponse> {
    return request<TaskStatusResponse>(`/tasks/${taskId}`)
  },
}

// 历史消息响应（GET /api/v1/sessions/{id}/messages）
export interface MessageResponse {
  id: string
  role: string
  content: string | null
  tool_calls: { name: string; args: Record<string, unknown>; id?: string }[] | null
  attachments: import('../types').Attachment[] | null
  created_at: string
}

// 消息接口
export const messageApi = {
  list(sessionId: string): Promise<MessageResponse[]> {
    return request<MessageResponse[]>(`/sessions/${sessionId}/messages`)
  },
}

// 当前用户信息接口（预留：后端若无 /users/me 可后续补充）
export const userApi = {
  me(): Promise<User> {
    return request<User>('/users/me')
  },
}

// 文件上传响应（POST /api/v1/files）
export interface FileUploadResponse {
  file_id: string
  task_id: string | null
  status: string
  filename: string
}

// 文件接口：上传走 multipart，不能复用 request()（其强制 JSON Content-Type）
export const filesApi = {
  async upload(file: File): Promise<FileUploadResponse> {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API_BASE}/files`, {
      method: 'POST',
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
      body: form,
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        detail = body.detail ?? JSON.stringify(body)
      } catch {
        detail = `HTTP ${res.status} ${res.statusText}`
      }
      throw new Error(detail)
    }
    return res.json() as Promise<FileUploadResponse>
  },
  // 获取文件公开访问 URL（历史附件展示/下载用）
  async url(fileId: string): Promise<{ file_id: string; url: string; filename: string }> {
    return request(`/files/${fileId}/url`)
  },
}
