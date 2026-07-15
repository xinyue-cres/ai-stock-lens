import { useMutation, useQuery, useQueryClient, useIsMutating } from '@tanstack/react-query'
import { ActionPlan, generateActionPlan, getActionPlan } from '@/api/actionPlan'
import { useStock } from '@/features/stock-context'

/**
 * 操作指示（Trader）的状态和操作。
 *
 * mutationKey 绑定 code：即使组件因切股导致 code 变化，
 * useIsMutating 仍能检测到该 code 是否有正在跑的 mutation，
 * 切回来时 isPending 依旧为 true 直到 API 返回。
 */
export function useActionPlan() {
  const { code } = useStock()
  const qc = useQueryClient()

  const cacheQuery = useQuery({
    queryKey: ['action-plan', code],
    queryFn: () => getActionPlan(code),
    enabled: !!code,
  })

  const mutationKey = ['gen-action-plan', code]

  const mutation = useMutation<ActionPlan, unknown, { ctxCode: string; force: boolean }>({
    mutationKey,
    mutationFn: (vars) => generateActionPlan(vars.ctxCode, vars.force),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['action-plan', vars.ctxCode] })
      qc.invalidateQueries({ queryKey: ['action-plan-deps', vars.ctxCode] })
    },
  })

  // useIsMutating 不依赖组件内部的 mutation 实例状态，
  // 即使切股后 mutation.variables 不再匹配，只要 key 匹配就会返回 > 0
  const pendingCount = useIsMutating({ mutationKey })
  const isPending = pendingCount > 0

  const cacheData = cacheQuery.data && !cacheQuery.data.empty ? cacheQuery.data : null
  const mData = mutation.data && mutation.data.code === code ? mutation.data : null
  const data = mData ?? cacheData
  const loading = isPending || cacheQuery.isLoading

  return {
    data,
    loading,
    isPending,
    isError: mutation.isError,
    error: mutation.error,
    generate: () => mutation.mutate({ ctxCode: code, force: false }),
    forceRegenerate: () => mutation.mutate({ ctxCode: code, force: true }),
    isCachedOnly: !mData && !!cacheData,
  }
}
