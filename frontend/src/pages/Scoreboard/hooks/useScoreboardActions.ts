import { useMutation, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { useState } from 'react'
import { analyzeBatchScore, cancelScan, runScan, summarizeScore } from '@/api/score'
import { addWatchlist } from '@/api/watchlist'
import { useInvalidation } from '@/hooks/useInvalidation'

/** Scoreboard 页面所有 useMutation 操作逻辑（扫描/取消/AI点评/AI汇总/加自选）。 */
export function useScoreboardActions(props: {
  scope: string
  force: boolean
  groupIds: number[]
  timeframe: 'daily' | 'weekly' | 'combined'
  aiParams: {
    scope: string
    group_ids?: string
    sort_by: 'total'
    dir: 'desc'
  }
}) {
  const { scope, force, groupIds, timeframe, aiParams } = props
  const qc = useQueryClient()
  const globalInv = useInvalidation()
  const [criteriaOpen, setCriteriaOpen] = useState(false)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [commentsOpen, setCommentsOpen] = useState(false)

  const scanMut = useMutation({
    mutationFn: () =>
      runScan({
        scope,
        force,
        group_ids: scope === 'group' && groupIds.length ? groupIds : undefined,
        // 扫什么周期 = 看什么周期；combined 在 weekly/daily 之后由 backend 自动合成
        timeframe: timeframe === 'combined' ? 'weekly' : timeframe,
      }),
    onSuccess: (d) => {
      if (d.started === false) message.warning(d.reason || '已有扫描进行中')
      else message.success(`开始扫描，共 ${d.total} 只`)
      // 立即刷新扫描状态：让轮询尽快切到 running(2s)，避免最长 30s 的空闲轮询延迟
      qc.invalidateQueries({ queryKey: ['score-scan-status'] })
    },
    onError: () => message.error('触发扫描失败'),
  })

  const cancelMut = useMutation({
    mutationFn: cancelScan,
    onSuccess: () => message.info('已请求取消'),
  })

  // AI 逐股点评（独立按钮：对当前列表每只各自生成总结，不做组对比）
  const commentMut = useMutation({
    mutationFn: () => analyzeBatchScore({ ...aiParams, limit: 10 }),
    onSuccess: () => setCommentsOpen(true),
    onError: () => message.error('AI 逐股点评失败，请稍后重试'),
  })

  // AI 整组汇总（独立按钮，复用当前列表的过滤/排序参数，不参与扫描）
  const summaryMut = useMutation({
    mutationFn: () => summarizeScore({ ...aiParams, limit: 15 }),
    onSuccess: () => setSummaryOpen(true),
    onError: () => message.error('AI 汇总失败，请稍后重试'),
  })

  const addMut = useMutation({
    // 处于"自选分组"范围且选中了分组时，加入自选直接放进当前分组
    mutationFn: (code: string) =>
      addWatchlist(code, scope === 'group' && groupIds.length ? groupIds : undefined),
    onSuccess: () => {
      message.success('已加入自选股')
      globalInv.afterSync()
    },
    onError: () => message.error('加入自选失败'),
  })

  return {
    // 模态开关
    criteriaOpen, setCriteriaOpen,
    summaryOpen, setSummaryOpen,
    commentsOpen, setCommentsOpen,
    // 异步动作
    scanMut,
    cancelMut,
    commentMut,
    summaryMut,
    addMut,
    // 数据用于模态内容
    summaryData: summaryMut.data ?? null,
    commentData: commentMut.data?.items ?? null,
  }
}
