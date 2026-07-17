import { useMutation, useQuery, useQueryClient, useIsMutating, keepPreviousData } from '@tanstack/react-query'
import { AiReport, generateAiReport, getCachedAiReport } from '@/api/analysis'
import { useStock } from './StockContext'

export type Horizon = 'combined' | 'anti_quant' | 'reflexivity'

/** 各处共用的 mutationKey 生成函数，确保一键按钮和 Tab 子按钮共享同一个 key。 */
export function aiReportMutationKey(code: string, horizon: Horizon) {
  return ['gen-ai-report', code, horizon] as const
}

interface MutationVars {
  force: boolean
  ctxCode: string
  ctxHorizon: Horizon
}

/**
 * 单一视角的 AI 报告状态与操作。
 *
 * mutationKey 绑定 (code, horizon)：一键按钮触发相同 key 的 mutation 时，
 * useIsMutating 能让子 Tab 的 isPending 同步为 true。
 */
export function useAiReport(horizon: Horizon) {
  const { code } = useStock()
  const qc = useQueryClient()

  const mutationKey = aiReportMutationKey(code, horizon)

  const cacheQuery = useQuery({
    queryKey: ['ai-report-cached', code, horizon],
    queryFn: () => getCachedAiReport(code, horizon),
    enabled: !!code,
    placeholderData: keepPreviousData,
  })

  const mutation = useMutation<AiReport, unknown, MutationVars>({
    mutationKey,
    mutationFn: (vars) =>
      generateAiReport(vars.ctxCode, { horizon: vars.ctxHorizon, force: vars.force }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['ai-report-cached', vars.ctxCode, vars.ctxHorizon] })
      qc.invalidateQueries({ queryKey: ['action-plan-deps', vars.ctxCode] })
      qc.invalidateQueries({ queryKey: ['action-plan', vars.ctxCode] })
    },
  })

  const pendingCount = useIsMutating({ mutationKey })
  const isPending = pendingCount > 0

  const cacheData =
    cacheQuery.data && !cacheQuery.data.empty && cacheQuery.data.horizon === horizon
      ? (cacheQuery.data as AiReport)
      : null
  const mData =
    mutation.data &&
    mutation.data.code === code &&
    mutation.data.horizon === horizon
      ? mutation.data
      : null
  const data = mData ?? cacheData
  const horizonMismatch =
    !!(mutation.data && mutation.data.horizon !== horizon) ||
    !!(cacheQuery.data && !cacheQuery.data.empty && cacheQuery.data.horizon !== horizon)
  const loading = isPending || cacheQuery.isLoading

  return {
    data,
    loading,
    isPending,
    isError: mutation.isError,
    error: mutation.error,
    generate: () => mutation.mutate({ force: false, ctxCode: code, ctxHorizon: horizon }),
    forceRegenerate: () => mutation.mutate({ force: true, ctxCode: code, ctxHorizon: horizon }),
    isCachedOnly: !mData && !!cacheData,
    horizonMismatch,
  }
}
