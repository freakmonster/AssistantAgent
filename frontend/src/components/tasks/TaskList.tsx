// 任务列表：展示所有异步任务并挂载轮询
import { useTaskPolling } from '../../hooks/useTaskPolling'
import { useTaskStore } from '../../stores/taskStore'
import { TaskCard } from './TaskCard'

export function TaskList() {
  // 挂载全局轮询：对未完成任务定时拉取状态
  useTaskPolling()
  const tasks = useTaskStore((s) => s.tasks)
  const list = Object.values(tasks)

  if (list.length === 0) return null

  return (
    <div className="task-list">
      {list.map((task) => (
        <TaskCard key={task.taskId} task={task} />
      ))}
    </div>
  )
}
