// 应用入口：未登录显示认证，已登录显示三栏聊天布局
import { useEffect, useState } from 'react'
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

  // 新建对话：复用侧边栏同款逻辑，供收起态下的「+」按钮使用
  const handleNewChat = async () => {
    const session = await createSession('新对话')
    if (session) {
      setLastSessionId(session.id)
      void loadHistory(session.id)
    }
  }

  // 登录/刷新后恢复上次会话并加载历史消息
  useEffect(() => {
    if (!token) return
    void (async () => {
      await useSessionStore.getState().fetchSessions()
      // 刷新页面时自动清理空会话
      await useSessionStore.getState().cleanupEmptySessions()
      const sessions = useSessionStore.getState().sessions
      const last = useUserStore.getState().lastSessionId
      if (last && sessions.some((s) => s.id === last)) {
        useSessionStore.getState().setCurrentSession(last)
        await useMessageStore.getState().loadHistory(last)
      } else if (sessions.length > 0) {
        const first = sessions[0].id
        useSessionStore.getState().setCurrentSession(first)
        await useMessageStore.getState().loadHistory(first)
      }
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
          <div className="no-session">请先选择或新建会话</div>
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
