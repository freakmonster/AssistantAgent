// 侧边栏：会话列表 + 新建对话 + 用户信息/登出；每条会话支持重命名/置顶/删除
import { LogoutOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons'
import { Fragment, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useMessageStore } from '../../stores/messageStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useSettingsStore, useTranslation } from '../../stores/settingsStore'
import { useUserStore } from '../../stores/userStore'
import type { Session } from '../../types'

interface SidebarProps {
  onCollapse: () => void
  onResizeStart: (e: ReactMouseEvent<HTMLDivElement>) => void
}

// 将会话按时间分组：置顶 / 今天 / 7天内 / 30天内 / 30天以上
function groupSessions(
  sessions: Session[],
  labels: Record<'pinned' | 'today' | 'within7' | 'within30' | 'older', string>,
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
  if (pinned.length) groups.push({ label: labels.pinned, items: pinned })
  if (today.length) groups.push({ label: labels.today, items: today })
  if (within7.length) groups.push({ label: labels.within7, items: within7 })
  if (within30.length) groups.push({ label: labels.within30, items: within30 })
  if (older.length) groups.push({ label: labels.older, items: older })
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
  const { t } = useTranslation()
  const theme = useSettingsStore((s) => s.theme)
  const locale = useSettingsStore((s) => s.locale)
  const setTheme = useSettingsStore((s) => s.setTheme)
  const setLocale = useSettingsStore((s) => s.setLocale)

  // 当前打开操作菜单的会话 id（同时最多一个）
  const [menuId, setMenuId] = useState<string | null>(null)
  // 正在重命名的会话 id 与输入内容
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const renameInputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // 用户菜单（登出/系统设置/帮助）下拉框状态与弹窗状态
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [modal, setModal] = useState<'settings' | 'help' | null>(null)
  const userMenuRef = useRef<HTMLDivElement>(null)

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
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false)
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
        {t.sidebar.newChat}
      </button>
      <ul className="session-list">
        {groupSessions(sessions, {
          pinned: t.sidebar.pinned,
          today: t.sidebar.today,
          within7: t.sidebar.within7,
          within30: t.sidebar.within30,
          older: t.sidebar.older,
        }).map((group) => (
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
                  <span className="session-title">{s.title || t.sidebar.untitled}</span>
                )}
                <button
                  className="session-menu-btn"
                  onClick={(e) => openMenu(e, s.id)}
                  aria-label={t.sidebar.sessionActions}
                >
                  ...
                </button>
                {menuId === s.id && (
                  <div className="session-menu" ref={menuRef}>
                    <button onClick={(e) => { e.stopPropagation(); startRename(s.id, s.title) }}>
                      {t.sidebar.rename}
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); void handlePin(s.id) }}>
                      {s.is_pinned ? t.sidebar.unpin : t.sidebar.pin}
                    </button>
                    <button
                      className="danger"
                      onClick={(e) => { e.stopPropagation(); void handleDelete(s.id) }}
                    >
                      {t.sidebar.delete}
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
        <div className="user-menu-wrap" ref={userMenuRef}>
          <button
            className="user-menu-btn"
            onClick={(e) => {
              e.stopPropagation()
              setUserMenuOpen((o) => !o)
            }}
            aria-label={t.sidebar.userMenu}
          >
            ...
          </button>
          {userMenuOpen && (
            <div className="user-menu">
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setUserMenuOpen(false)
                  logout()
                }}
              >
                <LogoutOutlined /> {t.sidebar.logout}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setUserMenuOpen(false)
                  setModal('settings')
                }}
              >
                <SettingOutlined /> {t.sidebar.settings}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setUserMenuOpen(false)
                  setModal('help')
                }}
              >
                <QuestionCircleOutlined /> {t.sidebar.help}
              </button>
            </div>
          )}
        </div>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">
                {modal === 'settings' ? t.settings.title : t.settings.helpTitle}
              </span>
              <button
                className="modal-close"
                onClick={() => setModal(null)}
                aria-label={t.settings.close}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              {modal === 'settings' ? (
                <div className="settings-body">
                  {/* 主题选择 */}
                  <div className="setting-row">
                    <span className="setting-label">{t.settings.theme}</span>
                    <div className="setting-options">
                      <button
                        className={theme === 'light' ? 'active' : ''}
                        onClick={() => setTheme('light')}
                      >
                        {t.settings.light}
                      </button>
                      <button
                        className={theme === 'dark' ? 'active' : ''}
                        onClick={() => setTheme('dark')}
                      >
                        {t.settings.dark}
                      </button>
                    </div>
                  </div>
                  {/* 语言选择 */}
                  <div className="setting-row">
                    <span className="setting-label">{t.settings.language}</span>
                    <div className="setting-options">
                      <button
                        className={locale === 'zh' ? 'active' : ''}
                        onClick={() => setLocale('zh')}
                      >
                        {t.settings.chinese}
                      </button>
                      <button
                        className={locale === 'en' ? 'active' : ''}
                        onClick={() => setLocale('en')}
                      >
                        {t.settings.english}
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="help-body">
                  {/* 功能一览 */}
                  <section className="help-section">
                    <h4 className="help-section-title">{t.help.featuresTitle}</h4>
                    <ul className="help-features">
                      {t.help.features.map((f) => (
                        <li key={f.name} className="help-feature">
                          <span className="help-feature-name">{f.name}</span>
                          <span className="help-feature-desc">{f.desc}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                  {/* 使用技巧 */}
                  <section className="help-section">
                    <h4 className="help-section-title">{t.help.tipsTitle}</h4>
                    <ul className="help-tips">
                      {t.help.tips.map((tip, i) => (
                        <li key={i}>{tip}</li>
                      ))}
                    </ul>
                  </section>
                  {/* 常见问题 */}
                  <section className="help-section">
                    <h4 className="help-section-title">{t.help.faqTitle}</h4>
                    <ul className="help-faq">
                      {t.help.faq.map((item, i) => (
                        <li key={i}>
                          <p className="help-faq-q">{item.q}</p>
                          <p className="help-faq-a">{item.a}</p>
                        </li>
                      ))}
                    </ul>
                  </section>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {/* 右侧拖拽调整宽度的把手 */}
      <div className="sidebar-resizer" onMouseDown={onResizeStart} />
    </aside>
  )
}
