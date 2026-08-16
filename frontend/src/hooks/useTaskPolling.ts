// 任务轮询：定时查询未完成任务的最终状态，完成后更新结果
import { useEffect } from 'react'
import { taskApi } from '../services/api'
import { useTaskStore } from '../stores/taskStore'
import type { TaskStatus } from '../types'

const POLL_INTERVAL = 3000 // 轮询间隔（毫秒）
const ACTIVE_STATUSES: TaskStatus[] = ['queued', 'deferred', 'in_progress']

export function useTaskPolling(): void {
  useEffect(() => {
    const timer = setInterval(async () => {
      // 每轮从最新状态读取，避免闭包过期
      const tasks = useTaskStore.getState().tasks
      const activeIds = Object.values(tasks)
        .filter((t) => ACTIVE_STATUSES.includes(t.status))
        .map((t) => t.taskId)

      for (const id of activeIds) {
        try {
          const resp = await taskApi.get(id)
          const status = resp.status as TaskStatus
          if (status === 'complete') {
            useTaskStore.getState().setTaskResult(id, resp.result ?? null)
          } else if (status === 'not_found') {
            useTaskStore.getState().setTaskError(id, '任务不存在或已过期')
          } else {
            useTaskStore.getState().updateTaskStatus(id, status)
          }
        } catch (e) {
          // 网络抖动不立即判失败，等待下一轮重试
          console.error('轮询任务状态失败', id, e)
        }
      }
    }, POLL_INTERVAL)

    return () => clearInterval(timer)
  }, [])
}
