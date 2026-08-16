// 前端共享类型定义

// 消息角色
export type MessageRole = 'user' | 'assistant'

// 工具调用（来自 SSE 的 tool_call 事件）
export interface ToolCall {
  name: string
  args: Record<string, unknown>
  id?: string
}

// 工具调用卡片状态
export type ToolCallStatus = 'running' | 'success' | 'failed'

// 工具返回的统一协议（type=task 等，见设计文档 16.3）
export interface ToolPayload {
  type?: string
  task_id?: string
  status?: string
  content?: string
  url?: string
  alt?: string
  poster?: string
  prompt?: string
  error?: string
  message?: string
  [key: string]: unknown
}

// 异步任务结果类型
export type TaskResultType = 'text' | 'image' | 'video'

// 消息附件（历史消息中的媒体，如视频/图片）
export interface Attachment {
  type: TaskResultType
  url?: string
  poster?: string
  alt?: string
  content?: string
  prompt?: string
  [key: string]: unknown
}

// 异步任务结果（worker 完成时返回，见设计文档 16.3）
export interface TaskResult {
  type: TaskResultType
  url?: string
  poster?: string
  content?: string
  alt?: string
  prompt?: string
  [key: string]: unknown
}

// 任务状态（映射 ARQ JobStatus 的 value）
export type TaskStatus =
  | 'queued'
  | 'deferred'
  | 'in_progress'
  | 'complete'
  | 'not_found'
  | 'failed'

// 前端维护的异步任务状态
export interface Task {
  taskId: string
  status: TaskStatus
  result?: TaskResult | null
  error?: string
}

// 对话消息
export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  toolCalls?: ToolCall[]
  toolCallStatus?: ToolCallStatus
  taskId?: string
  attachments?: Attachment[]
  createdAt: number
}

// 会话
export interface Session {
  id: string
  title: string | null
  thread_id: string
  created_at: string
  updated_at: string
  message_count: number
}

// 用户
export interface User {
  id: string
  email: string
}

// 认证响应
export interface TokenResponse {
  access_token: string
  token_type: string
}
