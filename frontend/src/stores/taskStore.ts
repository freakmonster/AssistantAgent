// 任务状态：异步任务的注册、状态更新与结果存储（轮询数据源）
import { create } from 'zustand'
import type { Task, TaskResult, TaskStatus } from '../types'

interface TaskState {
  tasks: Record<string, Task>
  registerTask: (taskId: string) => void
  updateTaskStatus: (taskId: string, status: TaskStatus) => void
  setTaskResult: (taskId: string, result: TaskResult | null) => void
  setTaskError: (taskId: string, error: string) => void
  removeTask: (taskId: string) => void
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: {},
  registerTask: (taskId) =>
    set((state) => {
      // 已存在则跳过，避免覆盖已有结果
      if (state.tasks[taskId]) return state
      return {
        tasks: { ...state.tasks, [taskId]: { taskId, status: 'queued' } },
      }
    }),
  updateTaskStatus: (taskId, status) =>
    set((state) => {
      const existing = state.tasks[taskId]
      if (!existing) return state
      return {
        tasks: { ...state.tasks, [taskId]: { ...existing, status } },
      }
    }),
  setTaskResult: (taskId, result) =>
    set((state) => {
      const existing = state.tasks[taskId]
      if (!existing) return state
      return {
        tasks: {
          ...state.tasks,
          [taskId]: { ...existing, status: 'complete', result },
        },
      }
    }),
  setTaskError: (taskId, error) =>
    set((state) => {
      const existing = state.tasks[taskId]
      if (!existing) return state
      return {
        tasks: {
          ...state.tasks,
          [taskId]: { ...existing, status: 'failed', error },
        },
      }
    }),
  removeTask: (taskId) =>
    set((state) => {
      const next = { ...state.tasks }
      delete next[taskId]
      return { tasks: next }
    }),
}))
