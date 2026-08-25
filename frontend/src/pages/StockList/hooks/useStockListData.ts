/** StockList 数据与过滤：分组/搜索/AI 方向筛选 + 排序（从 index.tsx 抽出）。 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getGroups, type StockGroup } from '@/api/groups'
import { getMarketSummary } from '@/api/market'
import { useSignalsQuery } from '@/hooks/useSignalsQuery'
import type { SortKey, SortDir } from '../constants'

export interface StockListFilters {
  groupFilter: number | 'all'
  search: string
  dirFilter: '' | 'bullish' | 'bearish' | 'neutral'
  sortKey: SortKey
  sortDir: SortDir
}

export function useStockListData(filters: StockListFilters) {
  const { items } = useSignalsQuery()
  const groupsQ = useQuery({ queryKey: ['groups'], queryFn: getGroups })
  const marketQ = useQuery({
    queryKey: ['market-summary'],
    queryFn: () => getMarketSummary(),
    staleTime: 5 * 60_000,
  })
  const groups: StockGroup[] = groupsQ.data ?? []

  const filtered = useMemo(() => {
    let arr = items
    if (filters.groupFilter !== 'all') {
      arr = arr.filter(i => (i.group_ids || []).includes(filters.groupFilter as number))
    }
    if (filters.search) {
      const k = filters.search.toLowerCase()
      arr = arr.filter(i => i.code.includes(k) || (i.name || '').toLowerCase().includes(k))
    }
    if (filters.dirFilter) {
      arr = arr.filter(i => {
        const v = i.ai_verdict
        if (!v) return filters.dirFilter === 'neutral'
        if (v === 'caution') return filters.dirFilter === 'neutral'
        return v === filters.dirFilter
      })
    }
    const sorted = [...arr]
    const dir = filters.sortDir === 'asc' ? 1 : -1
    if (filters.sortKey === 'pct_chg') {
      sorted.sort((a, b) => ((a.pct_chg ?? 0) - (b.pct_chg ?? 0)) * dir)
    } else if (filters.sortKey === 'position') {
      sorted.sort((a, b) => {
        const pa = a.position?.unrealized_pnl_pct ?? -999
        const pb = b.position?.unrealized_pnl_pct ?? -999
        return (pa - pb) * dir
      })
    } else if (filters.sortKey === 'verdict') {
      const verdictRank: Record<string, number> = { bullish: 2, neutral: 1, caution: 1, bearish: 0 }
      sorted.sort((a, b) => {
        const va = verdictRank[a.ai_verdict || ''] ?? 1
        const vb = verdictRank[b.ai_verdict || ''] ?? 1
        return (va - vb) * dir
      })
    } else if (filters.sortKey === 'name') {
      sorted.sort((a, b) => (a.name || '').localeCompare(b.name || '') * dir)
    } else {
      sorted.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
    }
    return sorted
  }, [items, filters.groupFilter, filters.search, filters.dirFilter, filters.sortKey, filters.sortDir])

  return { items, groups, market: marketQ.data, filtered }
}
