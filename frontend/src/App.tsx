// 应用入口：未登录显示认证，已登录显示三栏聊天布局
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
  const createSession = useSessionStore((s) => s.createSession)
  const setLastSessionId = useUserStore((s) => s.setLastSessionId)
  const loadHistory = useMessageStore((s) => s.loadHistory)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const initializedRef = useRef(false)

  // 新建对话：复用侧边栏同款逻辑，供收起态下的「+」按钮使用
  const handleNewChat = async () => {
    const session = await createSession('新对话')
    if (session) {
      setLastSessionId(session.id)
      void loadHistory(session.id)
    }
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
      await useSessionStore.getState().fetchSessions()
      // 清理历史遗留的空会话，避免堆积
      await useSessionStore.getState().cleanupEmptySessions()
      useMessageStore.getState().clearMessages()
      await useSessionStore.getState().createSession('新对话')
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
    <div className={`app-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar onCollapse={() => setSidebarCollapsed(true)} />
      <main className="main-panel">
        <ChatArea />
        {currentSessionId ? (
          <ChatInput sessionId={currentSessionId} />
        ) : (
          <div className="no-session"></div>
        )}
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
