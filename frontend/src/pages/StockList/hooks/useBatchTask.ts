/** StockList 批量任务：batchRun 编排 + 完成后的 toast 与缓存失效（从 index.tsx 抽出）。
 *
 * 完成 2s 后 items 变化时清理 batchState（batchDoneRef 标记"已展示结果"，
 * 避免缓冲期内 items 刷新反复触发清理弹 toast）。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { message } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { batchRun, BatchItemStatus, BatchState, BatchTaskType } from '@/api/batchTask'
import { useInvalidation } from '@/hooks/useInvalidation'

export function useBatchTask(
  onSelectedCleared: () => void,
  invalidateSignals: () => void,
  /** 列表数据引用：变化时触发已完成的 batchState 清理（原 index.tsx 的 useEffect([items]) 语义） */
  items: unknown[],
) {
  const qc = useQueryClient()
  const globalInv = useInvalidation()
  const [batchState, setBatchState] = useState<BatchState | null>(null)
  const batchDoneRef = useRef(false)

  useEffect(() => {
    if (batchDoneRef.current && batchState && !batchState.running) {
      setBatchState(null)
      batchDoneRef.current = false
    }
  }, [items, batchState])

  const start = useCallback((type: BatchTaskType, selected: Set<string>) => {
    const codes = [...selected]
    if (codes.length === 0) return
    // 并发按类型分离：sync 只发 K 线请求拉到 8（实测 8-19 并发 50 只自选耗时 242s/21s/19s/33s/32s，
    // 超过 16 反而触发东财 rate limit 强制 fallback baostock 全局锁）；
    // ai/action_plan 每只内还各并行 4 个 horizon 调 DeepSeek，拼太高会触发 rate limit，保持 3
    const concurrency = type === 'sync' ? 8 : 3
    batchRun(type, codes, concurrency, (state) => {
      setBatchState(state)
      if (!state.running) {
        const errors = [...state.items.values()].filter(s => s.status === 'error').length
        const label = type === 'ai' ? ' AI 分析' : type === 'sync' ? '同步' : '操作指示'
        if (errors === 0) {
          message.success(`${state.total} 只${label}全部完成`)
        } else {
          message.warning(`${label}完成 ${state.completed}/${state.total}，${errors} 只失败`)
        }
        if (type === 'sync') {
          globalInv.afterSync()
        } else if (type === 'ai') {
          globalInv.afterAiReport(codes[0])
          qc.invalidateQueries({ queryKey: ['ai-report-cached'] })
          invalidateSignals()
        } else {
          qc.invalidateQueries({ queryKey: ['action-plan'] })
          invalidateSignals()
        }
        setTimeout(() => { batchDoneRef.current = true }, 2000)
      }
    })
    onSelectedCleared()
  }, [qc, globalInv, invalidateSignals, onSelectedCleared])

  const getStatus = useCallback((code: string): BatchItemStatus | null => {
    if (!batchState) return null
    const item = batchState.items.get(code)
    return item?.status ?? null
  }, [batchState])

  return {
    batchState,
    start,
    getStatus,
    running: batchState?.running ?? false,
    type: batchState?.type ?? null,
    completed: batchState?.completed ?? 0,
    total: batchState?.total ?? 0,
  }
}
