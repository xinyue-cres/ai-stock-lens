import { generateActionPlan } from './actionPlan'
import { generateAiReport } from './analysis'

const AI_HORIZONS = ['combined', 'anti_quant', 'reflexivity'] as const

export type BatchTaskType = 'ai' | 'action_plan'
export type BatchItemStatus = 'pending' | 'running' | 'done' | 'error'

export interface BatchItemState {
  status: BatchItemStatus
  error?: string
}

export interface BatchState {
  type: BatchTaskType
  items: Map<string, BatchItemState>
  total: number
  completed: number
  running: boolean
}

export type BatchStateCallback = (state: BatchState) => void

export async function batchRun(
  type: BatchTaskType,
  codes: string[],
  concurrency = 3,
  onUpdate?: BatchStateCallback,
): Promise<BatchState> {
  const items = new Map<string, BatchItemState>()
  for (const code of codes) {
    items.set(code, { status: 'pending' })
  }

  const state: BatchState = {
    type,
    items,
    total: codes.length,
    completed: 0,
    running: true,
  }

  const emit = () => {
    onUpdate?.({ ...state, items: new Map(state.items) })
  }

  emit()

  const queue = [...codes]
  const runOne = async () => {
    while (queue.length > 0) {
      const code = queue.shift()!
      state.items.set(code, { status: 'running' })
      emit()
      try {
        if (type === 'ai') {
          await Promise.all(AI_HORIZONS.map(horizon =>
            generateAiReport(code, { horizon, force: false })
          ))
        } else {
          await generateActionPlan(code, false)
        }
        state.items.set(code, { status: 'done' })
      } catch (e: any) {
        state.items.set(code, { status: 'error', error: e?.message || '失败' })
      }
      state.completed++
      emit()
    }
  }

  const workers: Promise<void>[] = []
  for (let i = 0; i < Math.min(concurrency, codes.length); i++) {
    workers.push(runOne())
  }
  await Promise.all(workers)

  state.running = false
  emit()
  return state
}
