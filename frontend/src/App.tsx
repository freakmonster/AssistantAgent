// 应用入口：未登录显示认证，已登录显示三栏聊天布局
import type { CSSProperties, MouseEvent as ReactMouseEvent } from 'react'
import { useEffect, useRef, useState } from 'react'
import { Login } from './components/Auth/Login'
import { Register } from './components/Auth/Register'
import { ChatArea } from './components/Chat/ChatArea'
import { ChatInput } from './components/Chat/ChatInput'
import { Sidebar } from './components/Sidebar/Sidebar'
import { useMessageStore } from './stores/messageStore'
import { useSessionStore } from './stores/sessionStore'
import { useUserStore } from './stores/userStore'

export default function App() {
  const token = useUserStore((s) => s.token)
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  // 侧边栏宽度（可拖拽调整），上下限分别限制
  const [sidebarWidth, setSidebarWidth] = useState(260)
  const initializedRef = useRef(false)

  // 侧边栏宽度上下限
  const SIDEBAR_MIN = 200
  const SIDEBAR_MAX = 480

  // 新建对话：进入草稿态（不创建后端会话），清空消息，供收起态下的「+」按钮使用
  const handleNewChat = () => {
    useMessageStore.getState().clearMessages()
    useSessionStore.getState().startNewChat()
  }

  // 拖拽调整侧边栏宽度（mousedown 后监听全局移动，限制在上下限内）
  const handleResizeStart = (e: ReactMouseEvent<HTMLDivElement>) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = sidebarWidth
    const onMove = (ev: MouseEvent) => {
      const next = Math.min(
        SIDEBAR_MAX,
        Math.max(SIDEBAR_MIN, startWidth + (ev.clientX - startX)),
      )
      setSidebarWidth(next)
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  // 登录/刷新后直接进入新会话界面（空对话欢迎区）
  useEffect(() => {
    if (!token) {
      // 登出后重置，保证再次登录仍能初始化
      initializedRef.current = false
      return
    }
    // 防 StrictMode 开发环境 effect 双调用导致重复新建会话
    if (initializedRef.current) return
    initializedRef.current = true
    void (async () => {
      // 刷新后恢复用户信息（侧边栏底部邮箱等）
      await useUserStore.getState().fetchMe()
      await useSessionStore.getState().fetchSessions()
      // 清理历史遗留的空会话，避免堆积
      await useSessionStore.getState().cleanupEmptySessions()
      useMessageStore.getState().clearMessages()
      // 进入草稿态，不立即创建会话，等发送首条消息时再建
      useSessionStore.getState().startNewChat()
    })()
  }, [token])

  if (!token) {
    return authMode === 'login' ? (
      <Login onSwitch={() => setAuthMode('register')} />
    ) : (
      <Register onSwitch={() => setAuthMode('login')} />
    )
  }

  return (
    <div
      className={`app-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}
      style={{ '--sidebar-width': `${sidebarWidth}px` } as CSSProperties}
    >
      <Sidebar
        onCollapse={() => setSidebarCollapsed(true)}
        onResizeStart={handleResizeStart}
      />
      <main className="main-panel">
        <ChatArea />
        <ChatInput sessionId={currentSessionId} />
      </main>
      <button
        className="sidebar-expand-btn"
        onClick={() => setSidebarCollapsed(false)}
        aria-label="展开侧边栏"
      >
        »
      </button>
      <button
        className="new-chat-float-btn"
        onClick={() => void handleNewChat()}
        aria-label="新建对话"
      >
        +
      </button>
    </div>
  )
}
