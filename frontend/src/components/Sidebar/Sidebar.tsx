// 侧边栏：会话列表 + 新建对话 + 用户信息/登出
import { useEffect } from 'react'
import { useMessageStore } from '../../stores/messageStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useUserStore } from '../../stores/userStore'

interface SidebarProps {
  onCollapse: () => void
}

export function Sidebar({ onCollapse }: SidebarProps) {
  const sessions = useSessionStore((s) => s.sessions)
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const fetchSessions = useSessionStore((s) => s.fetchSessions)
  const createSession = useSessionStore((s) => s.createSession)
  const setCurrentSession = useSessionStore((s) => s.setCurrentSession)
  const loadHistory = useMessageStore((s) => s.loadHistory)
  const setLastSessionId = useUserStore((s) => s.setLastSessionId)
  const user = useUserStore((s) => s.user)
  const logout = useUserStore((s) => s.logout)

  useEffect(() => {
    void fetchSessions()
  }, [fetchSessions])

  const handleSelect = (id: string) => {
    setCurrentSession(id)
    setLastSessionId(id)
    void loadHistory(id)
  }

  const handleNew = async () => {
    const session = await createSession('新对话')
    if (session) {
      setLastSessionId(session.id)
      void loadHistory(session.id)
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <span className="sidebar-brand">Personal Assistant</span>
        <button
          className="sidebar-toggle-btn"
          onClick={onCollapse}
          aria-label="收起侧边栏"
        >
          «
        </button>
      </div>
      <button className="new-chat-btn" onClick={() => void handleNew()}>
        + 新对话
      </button>
      <ul className="session-list">
        {sessions.map((s) => (
          <li
            key={s.id}
            className={s.id === currentSessionId ? 'active' : ''}
            onClick={() => handleSelect(s.id)}
          >
            {s.title || '未命名对话'}
          </li>
        ))}
      </ul>
      <div className="sidebar-footer">
        <span className="sidebar-user">{user?.email ?? ''}</span>
        <button className="logout-btn" onClick={logout}>
          登出
        </button>
      </div>
    </aside>
  )
}
