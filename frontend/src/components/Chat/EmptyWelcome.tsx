// 空对话欢迎区：品牌 logo + 自我介绍 + 四个功能方框（左上角简笔画图标，各不同颜色）
import type { ReactNode } from 'react'

interface Feature {
  title: string
  desc: string
  color: string
  icon: ReactNode
}

// 四个功能方框内容：图标为简笔画线条 SVG，颜色通过 color 注入
const FEATURES: Feature[] = [
  {
    title: '联网搜索',
    desc: '实时搜索最新信息与新闻',
    color: '#2563eb',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </svg>
    ),
  },
  {
    title: '图片/视频生成',
    desc: '一句话生成图片与视频',
    color: '#9333ea',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 3a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
      </svg>
    ),
  },
  {
    title: '地图服务',
    desc: '地理编码、天气、路径与周边',
    color: '#16a34a',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
        <circle cx="12" cy="10" r="3" />
      </svg>
    ),
  },
  {
    title: '编程与竞赛',
    desc: 'LeetCode 题目、题解与用户信息',
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
  return (
    <div className="welcome">
      <img className="welcome-logo" src="/favicon.svg" alt="Personal Assistant" />
      <p className="welcome-intro">
        你好，我是超级个人综合型助手，能通过工具调用帮你完成各类任务。<br /><br />
        你可以询问我“你有什么功能”，我会告诉你我提供的所有功能。
      </p>
      <div className="welcome-grid">
        {FEATURES.map((f) => (
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
