import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message, Modal } from 'antd'
import { getTodaySignals, SignalItem } from '@/api/signals'
import { getGroups, patchStock, StockGroup } from '@/api/groups'
import { getMarketSummary } from '@/api/market'
import { addWatchlist, removeWatchlist } from '@/api/watchlist'
import { syncSingleStock, runSync } from '@/api/sync'
import { batchRun, BatchItemStatus, BatchState, BatchTaskType } from '@/api/batchTask'
import { SortKey, SortDir } from './constants'
import SummaryBar from './components/SummaryBar'
import Toolbar from './components/Toolbar'
import StockRow from './components/StockRow'
import GroupNav from './components/GroupNav'
import GroupManagerModal from './components/GroupManagerModal'
import BatchActionBar from './components/BatchActionBar'

export default function StockListPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const qc = useQueryClient()
  const initGroup = searchParams.get('group')
  const [groupFilter, setGroupFilter] = useState<number | 'all'>(initGroup ? Number(initGroup) : 'all')
  const [dirFilter, setDirFilter] = useState<'' | 'bullish' | 'bearish' | 'neutral'>('')
  const [sortKey, setSortKey] = useState<SortKey>('default')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [search, setSearch] = useState('')
  const [addValue, setAddValue] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [groupMgrOpen, setGroupMgrOpen] = useState(false)
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  // 批量任务状态
  const [batchState, setBatchState] = useState<BatchState | null>(null)

  const groupsQ = useQuery({ queryKey: ['groups'], queryFn: getGroups })
  const marketQ = useQuery({ queryKey: ['market-summary'], queryFn: () => getMarketSummary(), staleTime: 5 * 60_000 })
  const signalsQ = useQuery({
    queryKey: ['signals-today'],
    queryFn: () => getTodaySignals(),
    refetchInterval: (q) => {
      const items = (q.state.data as any)?.items ?? []
      return items.some((i: any) => i.empty) ? 3_000 : 5 * 60_000
    },
  })

  const syncMut = useMutation({
    mutationFn: runSync,
    onSuccess: () => {
      message.success('同步完成')
      qc.invalidateQueries({ queryKey: ['signals-today'] })
      qc.invalidateQueries({ queryKey: ['market-summary'] })
    },
  })

  const addMut = useMutation({
    mutationFn: (code: string) => addWatchlist(code),
    onSuccess: (d) => {
      message.success(`已加入 ${d.name || d.code}`)
      qc.invalidateQueries({ queryKey: ['signals-today'] })
      qc.invalidateQueries({ queryKey: ['groups'] })
      setAddValue('')
      setAddOpen(false)
    },
  })

  const items: SignalItem[] = signalsQ.data?.items ?? []
  const groups: StockGroup[] = groupsQ.data ?? []

  const filtered = useMemo(() => {
    let arr = items
    if (groupFilter !== 'all') {
      arr = arr.filter(i => (i.group_ids || []).includes(groupFilter as number))
    }
    if (search) {
      const k = search.toLowerCase()
      arr = arr.filter(i => i.code.includes(k) || (i.name || '').toLowerCase().includes(k))
    }
    if (dirFilter) {
      arr = arr.filter(i => {
        const v = i.ai_verdict
        if (!v) return dirFilter === 'neutral'
        if (v === 'caution') return dirFilter === 'neutral'
        return v === dirFilter
      })
    }
    const sorted = [...arr]
    const dir = sortDir === 'asc' ? 1 : -1
    if (sortKey === 'pct_chg') {
      sorted.sort((a, b) => ((a.pct_chg ?? 0) - (b.pct_chg ?? 0)) * dir)
    } else if (sortKey === 'position') {
      sorted.sort((a, b) => {
        const pa = a.position?.unrealized_pnl_pct ?? -999
        const pb = b.position?.unrealized_pnl_pct ?? -999
        return (pa - pb) * dir
      })
    } else if (sortKey === 'verdict') {
      const verdictRank: Record<string, number> = { bullish: 2, neutral: 1, caution: 1, bearish: 0 }
      sorted.sort((a, b) => {
        const va = verdictRank[a.ai_verdict || ''] ?? 1
        const vb = verdictRank[b.ai_verdict || ''] ?? 1
        return (va - vb) * dir
      })
    } else if (sortKey === 'name') {
      sorted.sort((a, b) => (a.name || '').localeCompare(b.name || '') * dir)
    } else {
      sorted.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
    }
    return sorted
  }, [items, groupFilter, search, dirFilter, sortKey, sortDir])

  const handleBatchStart = useCallback((type: BatchTaskType) => {
    const codes = [...selected]
    if (codes.length === 0) return
    batchRun(type, codes, 3, (state) => {
      setBatchState(state)
      if (!state.running) {
        const errors = [...state.items.values()].filter(s => s.status === 'error').length
        if (errors === 0) {
          message.success(`${state.total} 只${type === 'ai' ? ' AI 分析' : '操作指示'}全部完成`)
        } else {
          message.warning(`完成 ${state.completed}/${state.total}，${errors} 只失败`)
        }
        qc.invalidateQueries({ queryKey: ['signals-today'] })
        if (type === 'ai') {
          qc.invalidateQueries({ queryKey: ['ai-report-cached'] })
        } else {
          qc.invalidateQueries({ queryKey: ['action-plan'] })
        }
        setTimeout(() => setBatchState(null), 5000)
      }
    })
    setSelectMode(false)
    setSelected(new Set())
  }, [selected, qc])

  const getBatchStatus = useCallback((code: string): BatchItemStatus | null => {
    if (!batchState) return null
    const item = batchState.items.get(code)
    return item?.status ?? null
  }, [batchState])

  return (
    <div style={{ position: 'relative' }}>
      <GroupNav
        groups={groups}
        totalCount={items.length}
        activeGroup={groupFilter}
        onGroupChange={setGroupFilter}
        onManage={() => setGroupMgrOpen(true)}
      />

      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <SummaryBar items={items} market={marketQ.data} />

        <Toolbar
          search={search}
          onSearchChange={setSearch}
          dirFilter={dirFilter}
          onDirFilterChange={setDirFilter}
          sortKey={sortKey}
          onSortKeyChange={(k) => { setSortKey(k); if (k === 'default') setSortDir('desc') }}
          sortDir={sortDir}
          onSortDirChange={setSortDir}
          addOpen={addOpen}
          onAddOpenChange={setAddOpen}
          addValue={addValue}
          onAddValueChange={setAddValue}
          onAddSelect={(v) => addMut.mutate(v)}
          addLoading={addMut.isPending}
          syncLoading={syncMut.isPending}
          onSync={() => syncMut.mutate()}
          selectMode={selectMode}
          onSelectModeToggle={() => { setSelectMode(m => !m); if (selectMode) setSelected(new Set()) }}
          onSelectAll={() => setSelected(new Set(filtered.map(i => i.code)))}
          onSelectInvert={() => {
            const all = new Set(filtered.map(i => i.code))
            setSelected(prev => {
              const next = new Set<string>()
              for (const code of all) { if (!prev.has(code)) next.add(code) }
              return next
            })
          }}
        />

        <div style={{ background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0', overflow: 'hidden' }}>
          {filtered.map(item => (
            <StockRow
              key={item.code}
              item={item}
              groups={groups}
              selectMode={selectMode}
              checked={selected.has(item.code)}
              batchStatus={getBatchStatus(item.code)}
              onToggle={(code) => setSelected(prev => {
                const next = new Set(prev)
                if (next.has(code)) next.delete(code); else next.add(code)
                return next
              })}
              onClick={() => {
                if (selectMode) {
                  setSelected(prev => {
                    const next = new Set(prev)
                    if (next.has(item.code)) next.delete(item.code); else next.add(item.code)
                    return next
                  })
                } else {
                  const gParam = groupFilter !== 'all' ? `?group=${groupFilter}` : ''
                  navigate(`/stock/${item.code}${gParam}`)
                }
              }}
              onRemove={() => {
                Modal.confirm({
                  title: '移除自选？',
                  content: `将从自选中移除 ${item.name || item.code}`,
                  okText: '移除',
                  okButtonProps: { danger: true },
                  onOk: () => {
                    removeWatchlist(item.code).then(() => {
                      qc.invalidateQueries({ queryKey: ['signals-today'] })
                      qc.invalidateQueries({ queryKey: ['groups'] })
                    })
                  },
                })
              }}
              onGroupChange={(gids) => {
                patchStock(item.code, { group_ids: gids }).then(() => {
                  qc.invalidateQueries({ queryKey: ['signals-today'] })
                  qc.invalidateQueries({ queryKey: ['groups'] })
                })
              }}
              onSync={() => {
                syncSingleStock(item.code).then(() => {
                  message.success(`${item.name} 同步完成`)
                  qc.invalidateQueries({ queryKey: ['signals-today'] })
                })
              }}
            />
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: '40px 0', textAlign: 'center', color: '#9ca3af' }}>
              {items.length === 0 ? '还没有自选股，点击「添加」开始' : '当前筛选无结果'}
            </div>
          )}
        </div>
      </div>

      <GroupManagerModal
        open={groupMgrOpen}
        groups={groups}
        onClose={() => setGroupMgrOpen(false)}
        onChange={() => {
          qc.invalidateQueries({ queryKey: ['groups'] })
          qc.invalidateQueries({ queryKey: ['signals-today'] })
        }}
      />

      <BatchActionBar
        selected={selected}
        groups={groups}
        allItems={items}
        onClear={() => { setSelected(new Set()); setSelectMode(false) }}
        batchRunning={batchState?.running ?? false}
        batchType={batchState?.type ?? null}
        batchCompleted={batchState?.completed ?? 0}
        batchTotal={batchState?.total ?? 0}
        onBatchStart={handleBatchStart}
      />
    </div>
  )
}
