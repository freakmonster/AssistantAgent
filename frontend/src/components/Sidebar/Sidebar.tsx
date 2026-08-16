// 侧边栏：会话列表 + 新建对话 + 用户信息/登出；每条会话支持重命名/置顶/删除
import { Fragment, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useMessageStore } from '../../stores/messageStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useUserStore } from '../../stores/userStore'
import type { Session } from '../../types'

interface SidebarProps {
  onCollapse: () => void
  onResizeStart: (e: ReactMouseEvent<HTMLDivElement>) => void
}

// 将会话按时间分组：置顶 / 今天 / 7天内 / 30天内 / 30天以上
function groupSessions(
  sessions: Session[],
): { label: string; items: Session[] }[] {
  const pinned = sessions.filter((s) => s.is_pinned)
  const rest = sessions.filter((s) => !s.is_pinned)

  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)
  const todayStart = startOfToday.getTime()
  const dayMs = 24 * 60 * 60 * 1000

  const today: Session[] = []
  const within7: Session[] = []
  const within30: Session[] = []
  const older: Session[] = []

  for (const s of rest) {
    const t = new Date(s.updated_at).getTime()
    if (t >= todayStart) today.push(s)
    else if (t >= todayStart - 7 * dayMs) within7.push(s)
    else if (t >= todayStart - 30 * dayMs) within30.push(s)
    else older.push(s)
  }

  const groups: { label: string; items: Session[] }[] = []
  if (pinned.length) groups.push({ label: '置顶', items: pinned })
  if (today.length) groups.push({ label: '今天', items: today })
  if (within7.length) groups.push({ label: '7天内', items: within7 })
  if (within30.length) groups.push({ label: '30天内', items: within30 })
  if (older.length) groups.push({ label: '30天以上', items: older })
  return groups
}

export function Sidebar({ onCollapse, onResizeStart }: SidebarProps) {
  const sessions = useSessionStore((s) => s.sessions)
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const fetchSessions = useSessionStore((s) => s.fetchSessions)
  const startNewChat = useSessionStore((s) => s.startNewChat)
  const setCurrentSession = useSessionStore((s) => s.setCurrentSession)
  const renameSession = useSessionStore((s) => s.renameSession)
  const togglePin = useSessionStore((s) => s.togglePin)
  const deleteSession = useSessionStore((s) => s.deleteSession)
  const loadHistory = useMessageStore((s) => s.loadHistory)
  const clearMessages = useMessageStore((s) => s.clearMessages)
  const setLastSessionId = useUserStore((s) => s.setLastSessionId)
  const user = useUserStore((s) => s.user)
  const logout = useUserStore((s) => s.logout)

  // 当前打开操作菜单的会话 id（同时最多一个）
  const [menuId, setMenuId] = useState<string | null>(null)
  // 正在重命名的会话 id 与输入内容
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const renameInputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    void fetchSessions()
  }, [fetchSessions])

  // 重命名开始时自动聚焦输入框
  useEffect(() => {
    if (renamingId) renameInputRef.current?.focus()
  }, [renamingId])

  // 点击下拉菜单外部时关闭菜单
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuId(null)
      }
    }
    document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [])

  const handleSelect = (id: string) => {
    setCurrentSession(id)
    setLastSessionId(id)
    void loadHistory(id)
  }

  const handleNew = () => {
    clearMessages()
    startNewChat()
  }

  const openMenu = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setMenuId((cur) => (cur === id ? null : id))
  }

  const startRename = (id: string, title: string | null) => {
    setMenuId(null)
    setRenamingId(id)
    setRenameValue(title || '')
  }

  const commitRename = async () => {
    if (!renamingId) return
    const title = renameValue.trim()
    if (title) await renameSession(renamingId, title)
    setRenamingId(null)
  }

  const handlePin = async (id: string) => {
    setMenuId(null)
    await togglePin(id)
  }

  const handleDelete = async (id: string) => {
    setMenuId(null)
    await deleteSession(id)
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
        {groupSessions(sessions).map((group) => (
          <Fragment key={group.label}>
            <li className="session-group-label">{group.label}</li>
            {group.items.map((s) => (
              <li
                key={s.id}
                className={s.id === currentSessionId ? 'active' : ''}
                onClick={() => handleSelect(s.id)}
              >
                {renamingId === s.id ? (
                  <input
                    ref={renameInputRef}
                    className="session-rename-input"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => void commitRename()}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void commitRename()
                      if (e.key === 'Escape') setRenamingId(null)
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span className="session-title">{s.title || '未命名对话'}</span>
                )}
                <button
                  className="session-menu-btn"
                  onClick={(e) => openMenu(e, s.id)}
                  aria-label="会话操作"
                >
                  ...
                </button>
                {menuId === s.id && (
                  <div className="session-menu" ref={menuRef}>
                    <button onClick={(e) => { e.stopPropagation(); startRename(s.id, s.title) }}>
                      重命名
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); void handlePin(s.id) }}>
                      {s.is_pinned ? '取消置顶' : '置顶'}
                    </button>
                    <button
                      className="danger"
                      onClick={(e) => { e.stopPropagation(); void handleDelete(s.id) }}
                    >
                      删除
                    </button>
                  </div>
                )}
              </li>
            ))}
          </Fragment>
        ))}
      </ul>
      <div className="sidebar-footer">
        <span className="sidebar-user">{user?.email ?? ''}</span>
        <button className="logout-btn" onClick={logout}>
          登出
        </button>
      </div>
      {/* 右侧拖拽调整宽度的把手 */}
      <div className="sidebar-resizer" onMouseDown={onResizeStart} />
    </aside>
  )
}
