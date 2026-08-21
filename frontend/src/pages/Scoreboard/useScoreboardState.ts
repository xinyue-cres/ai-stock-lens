import { useMemo, useState } from 'react'

function loadScope(): string {
  return localStorage.getItem('scoreboard-scope') || 'all'
}

function loadGroupIds(): number[] {
  try {
    const arr = JSON.parse(localStorage.getItem('scoreboard-group-ids') ?? '[]')
    return Array.isArray(arr) ? arr.filter((x: unknown) => typeof x === 'number') : []
  } catch {
    return []
  }
}

/** 选股页工具栏/过滤状态：范围 + 分组 + 只看可入手 + 过峰过滤 + 周期切换 + 强制重扫。
 *
 * scope / groupIds / peakFilter / timeframe 持久化到 localStorage（切页面回来不丢）；其余为会话级。
 * aiParams 统一 AI 点评/汇总共用的过滤口径，避免两处各拼一遍。
 */
export function useScoreboardState() {
  const [onlyEntry, setOnlyEntry] = useState(false)
  const [scope, setScopeState] = useState<string>(loadScope)
  const [groupIds, setGroupIdsState] = useState<number[]>(loadGroupIds)
  const [force, setForce] = useState(false)
  // 过峰过滤：all 不过滤 / exclude_up 排除上涨过峰 / only_down 只看下跌过峰
  const [peakFilter, setPeakFilterState] = useState<'all' | 'exclude_up' | 'only_down'>(
    () => (localStorage.getItem('scoreboard-peak-filter') as any) || 'all',
  )
  // 打分基于的 K 线周期：daily 日线 / weekly 周五收盘周线
  const [timeframe, setTimeframeState] = useState<'daily' | 'weekly'>(
    () => (localStorage.getItem('scoreboard-timeframe') as 'daily' | 'weekly') || 'daily',
  )

  const setScope = (v: string) => {
    setScopeState(v)
    localStorage.setItem('scoreboard-scope', v)
    if (v !== 'group') {
      setGroupIdsState([])
      localStorage.setItem('scoreboard-group-ids', '[]')
    }
  }

  const setGroupIds = (v: number[]) => {
    setGroupIdsState(v)
    localStorage.setItem('scoreboard-group-ids', JSON.stringify(v))
  }

  const setPeakFilter = (v: 'all' | 'exclude_up' | 'only_down') => {
    setPeakFilterState(v)
    localStorage.setItem('scoreboard-peak-filter', v)
  }

  const setTimeframe = (v: 'daily' | 'weekly') => {
    setTimeframeState(v)
    localStorage.setItem('scoreboard-timeframe', v)
  }

  // AI 调用参数：与列表一致的总分降序过滤口径，点评/汇总共用
  const aiParams = useMemo(
    () => ({
      scope,
      group_ids: scope === 'group' && groupIds.length ? groupIds.join(',') : undefined,
      sort_by: 'total' as const,
      dir: 'desc' as const,
    }),
    [scope, groupIds],
  )

  return {
    onlyEntry,
    setOnlyEntry,
    scope,
    setScope,
    groupIds,
    setGroupIds,
    force,
    setForce,
    peakFilter,
    setPeakFilter,
    timeframe,
    setTimeframe,
    aiParams,
  }
}
