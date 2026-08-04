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

/** 选股页工具栏/过滤状态：范围 + 分组 + 排序 + 只看可入手 + 强制重扫。
 *
 * scope / groupIds 持久化到 localStorage（切页面回来不丢）；其余为会话级。
 * aiParams 统一 AI 点评/汇总共用的过滤口径，避免两处各拼一遍。
 */
export function useScoreboardState() {
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')
  const [onlyEntry, setOnlyEntry] = useState(false)
  const [scope, setScopeState] = useState<string>(loadScope)
  const [groupIds, setGroupIdsState] = useState<number[]>(loadGroupIds)
  const [force, setForce] = useState(false)

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

  // AI 调用参数：与列表一致的总分降序过滤口径，点评/汇总共用
  const aiParams = useMemo(
    () => ({
      scope,
      group_ids: scope === 'group' && groupIds.length ? groupIds.join(',') : undefined,
      sort_by: 'total' as const,
      dir: sortDir,
    }),
    [scope, groupIds, sortDir],
  )

  return {
    sortDir,
    setSortDir,
    onlyEntry,
    setOnlyEntry,
    scope,
    setScope,
    groupIds,
    setGroupIds,
    force,
    setForce,
    aiParams,
  }
}
