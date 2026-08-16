// 工具调用卡片：展示 Agent 调用的工具及其执行状态，支持收起/展开
import { useEffect, useState } from 'react'
import { useTranslation } from '../../stores/settingsStore'
import type { ToolCall, ToolCallStatus } from '../../types'

interface ToolCallCardProps {
  toolCalls: ToolCall[]
  status?: ToolCallStatus
}

const STATUS_ICON: Record<ToolCallStatus, string> = {
  running: '🔧',
  success: '✅',
  failed: '❌',
}

export function ToolCallCard({ toolCalls, status = 'running' }: ToolCallCardProps) {
  const { t } = useTranslation()
  const statusText: Record<ToolCallStatus, string> = {
    running: t.tool.running,
    success: t.tool.success,
    failed: t.tool.failed,
  }
  // 执行中默认展开展示参数；完成后默认收起为一行
  const [collapsed, setCollapsed] = useState(status !== 'running')

  // 工具执行结束（running → success/failed）时自动收起
  useEffect(() => {
    if (status !== 'running') {
      setCollapsed(true)
    }
  }, [status])

  if (toolCalls.length === 0) return null

  return (
    <div className={`tool-call-card tool-call-${status}`}>
      <div className="tool-call-header">
        <button
          className="tool-call-toggle"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? '展开工具详情' : '收起工具详情'}
        >
          {collapsed ? '▸' : '▾'}
        </button>
        <span>{STATUS_ICON[status]}</span>
        <span>
          {t.tool.call} {toolCalls.map((c) => c.name).join('、')}
        </span>
        <span className="tool-call-status">{statusText[status]}</span>
      </div>
      {!collapsed &&
        toolCalls.map((call) => (
          <div key={call.id ?? call.name} className="tool-call-args">
            <code>{JSON.stringify(call.args)}</code>
          </div>
        ))}
    </div>
  )
}

