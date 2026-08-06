import { useQueryClient } from '@tanstack/react-query'

export const SYNC_ALL_KEY = ['sync-all'] as const

export function useInvalidation() {
  const qc = useQueryClient()

  return {
    afterSync: () => {
      qc.invalidateQueries({ queryKey: ['signals-today'] })
      qc.invalidateQueries({ queryKey: ['kline'] })
      qc.invalidateQueries({ queryKey: ['market-summary'] })
      qc.invalidateQueries({ queryKey: ['action-plan-deps'] })
      // 选股打分（排行/详情/扫描状态）+ 自选列表，同步后一并刷新
      qc.invalidateQueries({ queryKey: ['score-list'] })
      qc.invalidateQueries({ queryKey: ['score-detail'] })
      qc.invalidateQueries({ queryKey: ['score-scan-status'] })
      qc.invalidateQueries({ queryKey: ['watchlist'] })
    },
    afterSyncSingle: (code: string) => {
      qc.invalidateQueries({ queryKey: ['signals-today'] })
      qc.invalidateQueries({ queryKey: ['kline', code] })
      qc.invalidateQueries({ queryKey: ['action-plan-deps', code] })
    },
    afterAiReport: (code: string, horizon?: string) => {
      if (horizon) {
        qc.invalidateQueries({ queryKey: ['ai-report-cached', code, horizon] })
      } else {
        qc.invalidateQueries({ queryKey: ['ai-report-cached', code] })
      }
      qc.invalidateQueries({ queryKey: ['action-plan-deps', code] })
      qc.invalidateQueries({ queryKey: ['action-plan', code] })
      qc.invalidateQueries({ queryKey: ['signals-today'] })
    },
  }
}
