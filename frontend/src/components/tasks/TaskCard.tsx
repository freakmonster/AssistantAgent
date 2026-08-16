// 单个异步任务卡片：按 result.type 渲染不同媒体形态
import type { Task } from '../../types'
import { AttachmentCard } from './AttachmentCard'

interface TaskCardProps {
  task: Task
}

export function TaskCard({ task }: TaskCardProps) {
  const { status, result, error } = task

  if (status === 'queued' || status === 'deferred') {
    return <div className="task-card">⏳ 任务排队中…</div>
  }
  if (status === 'in_progress') {
    return <div className="task-card">🔄 任务进行中…</div>
  }
  if (status === 'failed' || status === 'not_found') {
    return <div className="task-card">❌ {error ?? '任务失败'}</div>
  }

  // status === 'complete'
  if (!result) {
    return <div className="task-card">✅ 任务已完成</div>
  }

  // 完成态复用静态附件卡片渲染媒体
  return (
    <div className="task-card">
      <AttachmentCard attachment={result} />
    </div>
  )
}
