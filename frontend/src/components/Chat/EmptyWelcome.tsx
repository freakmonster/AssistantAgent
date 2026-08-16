// 空对话欢迎区：品牌 logo + 自我介绍 + 四个功能方框（左上角简笔画图标，各不同颜色）
import type { ReactNode } from 'react'
import { useTranslation } from '../../stores/settingsStore'

interface Feature {
  title: string
  desc: string
  color: string
  icon: ReactNode
}

// 四个功能方框内容：图标为简笔画线条 SVG，颜色通过 color 注入；标题与描述按语言翻译
const FEATURE_ICONS: { color: string; icon: ReactNode }[] = [
  {
    color: '#2563eb',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </svg>
    ),
  },
  {
    color: '#9333ea',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 3a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
      </svg>
    ),
  },
  {
    color: '#16a34a',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
        <circle cx="12" cy="10" r="3" />
      </svg>
    ),
  },
  {
    color: '#ea580c',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </svg>
    ),
  },
]

export function EmptyWelcome() {
  const { t } = useTranslation()
  const features: Feature[] = FEATURE_ICONS.map((f, i) => {
    const labels = [
      t.welcome.features.search,
      t.welcome.features.media,
      t.welcome.features.map,
      t.welcome.features.code,
    ]
    return { ...f, title: labels[i].title, desc: labels[i].desc }
  })
  return (
    <div className="welcome">
      <img className="welcome-logo" src="/favicon.svg" alt="Personal Assistant" />
      <p className="welcome-intro">
        {t.welcome.intro1}
        <br />
        <br />
        {t.welcome.intro2}
      </p>
      <div className="welcome-grid">
        {features.map((f) => (
          <div className="feature-card" key={f.title}>
            <span className="feature-icon" style={{ color: f.color }}>
              {f.icon}
            </span>
            <div className="feature-title">{f.title}</div>
            <div className="feature-desc">{f.desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
