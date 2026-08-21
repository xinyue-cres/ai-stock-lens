import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { getCombinedDetail, getScanStatus, getScoreDetail, getScoreList } from '@/api/score'
import { getGroups } from '@/api/groups'
import { useQueryClient } from '@tanstack/react-query'

/** 工具栏可见状态（由 useScoreboardState 提供）。 */
interface BoardState {
  onlyEntry: boolean
  scope: string
  groupIds: number[]
  peakFilter: 'all' | 'exclude_up' | 'only_down'
  timeframe: 'daily' | 'weekly' | 'combined'
  aiParams: {
    scope: string
    group_ids?: string
    sort_by: 'total'
    dir: 'desc'
  }
  selected: string | null
}

/** Scoreboard 页面所有 useQuery 数据获取逻辑（列表/详情/combined/分组/扫描状态/完成刷新）。 */
export function useScoreboardData(state: BoardState) {
  const qc = useQueryClient()
  const { onlyEntry, scope, groupIds, peakFilter, timeframe, selected } = state

  // 自选分组列表（选"自选分组"范围时用）
  const groupsQ = useQuery({
    queryKey: ['groups'],
    queryFn: getGroups,
    enabled: scope === 'group',
  })
  const groups = groupsQ.data ?? []

  // 打分排行（选了自选分组范围时，按所选分组过滤显示）
  // scope/peakFilter/timeframe 进 queryKey：切范围/过峰过滤/周期时强制重查，避免显示上次的数据
  const activeGroupIds = scope === 'group' && groupIds.length ? groupIds.join(',') : undefined
  const listQ = useQuery({
    queryKey: ['score-list', scope, onlyEntry, activeGroupIds, peakFilter, timeframe],
    queryFn: () =>
      getScoreList({
        sort_by: 'total',
        dir: 'desc',
        limit: 200,
        can_entry: onlyEntry ? true : undefined,
        group_ids: activeGroupIds,
        scope,
        peak_filter: peakFilter,
        // combined 模式：/list 不被使用，但需要合法值FastAPI 校验 → 传 'daily'
        timeframe: timeframe === 'combined' ? 'daily' : timeframe,
      }),
    enabled: timeframe !== 'combined',
  })
  const items = listQ.data ?? []

  // 扫描状态轮询（扫描中 2s，空闲 30s）
  const statusQ = useQuery({
    queryKey: ['score-scan-status'],
    queryFn: getScanStatus,
    refetchInterval: (q: any) => (q.state.data?.running ? 2000 : 30_000),
  })
  const scan = statusQ.data
  const running = !!scan?.running

  // 扫描结束 → 刷新列表与详情
  // 两个完成信号：running true→false（正常慢扫描）；finished_at null→有值（兜底，
  // 防止扫描太快、空闲 30s 轮询没 poll 到 running=true 时漏掉完成事件）
  const prevRunning = useRef<boolean>(false)
  const prevFinishedNull = useRef<boolean>(false)
  useEffect(() => {
    const runningNow = !!scan?.running
    const finishedAtIsNull = scan?.finished_at == null
    const justFinished = prevRunning.current && !runningNow
    const finishedAppeared = prevFinishedNull.current && !finishedAtIsNull && !runningNow
    if (justFinished || finishedAppeared) {
      qc.invalidateQueries({ queryKey: ['score-list'] })
      if (selected) qc.invalidateQueries({ queryKey: ['score-detail', selected] })
      qc.invalidateQueries({ queryKey: ['combined-list'] })
    }
    prevRunning.current = runningNow
    prevFinishedNull.current = finishedAtIsNull
  }, [scan?.running, scan?.finished_at, qc, selected])

  // 详情：daily/weekly 走 score_detail
  const detailQ = useQuery({
    queryKey: ['score-detail', selected, timeframe],
    queryFn: () => getScoreDetail(selected!, timeframe as 'daily' | 'weekly'),
    enabled: !!selected && timeframe !== 'combined',
  })

  // combined detail：综合模式时单独拉
  const combinedDetailQ = useQuery({
    queryKey: ['combined-detail', selected],
    queryFn: () => getCombinedDetail(selected!),
    enabled: !!selected && timeframe === 'combined',
  })

  return {
    groups,
    items,
    scan,
    running,
    detailQ,
    detail: detailQ.data,
    combinedDetailQ,
    combinedDetail: combinedDetailQ.data,
  }
}
