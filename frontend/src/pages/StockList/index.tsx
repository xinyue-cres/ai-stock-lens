import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useIsMutating, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message, Modal } from 'antd'
import { getGroups, patchStock, StockGroup } from '@/api/groups'
import { getMarketSummary } from '@/api/market'
import { addWatchlist, removeWatchlist } from '@/api/watchlist'
import { syncSingleStock, runSync } from '@/api/sync'
import { batchRun, BatchItemStatus, BatchState, BatchTaskType } from '@/api/batchTask'
import { useSignalsQuery } from '@/hooks/useSignalsQuery'
import { SYNC_ALL_KEY, useInvalidation } from '@/hooks/useInvalidation'
import { SortKey, SortDir } from './constants'
import SummaryBar from './components/SummaryBar'
import Toolbar from './components/Toolbar'
import StockRow from './components/StockRow'
import GroupNav from './components/GroupNav'
import GroupManagerModal from './components/GroupManagerModal'
import BatchActionBar from './components/BatchActionBar'

export default function StockListPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const qc = useQueryClient()
  const globalInv = useInvalidation()
  const syncingElsewhere = useIsMutating({ mutationKey: SYNC_ALL_KEY }) > 0
  const inv = {
    signals: () => qc.invalidateQueries({ queryKey: ['signals-today'] }),
    groups: () => qc.invalidateQueries({ queryKey: ['groups'] }),
    both: () => {
      qc.invalidateQueries({ queryKey: ['signals-today'] })
      qc.invalidateQueries({ queryKey: ['groups'] })
    },
  }
  const initGroup = searchParams.get('group')
  const [groupFilter, setGroupFilterState] = useState<number | 'all'>(initGroup ? Number(initGroup) : 'all')

  const setGroupFilter = useCallback((g: number | 'all') => {
    setGroupFilterState(g)
    if (g === 'all') {
      setSearchParams({}, { replace: true })
    } else {
      setSearchParams({ group: String(g) }, { replace: true })
    }
  }, [setSearchParams])
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
  const batchDoneRef = useRef(false)

  const groupsQ = useQuery({ queryKey: ['groups'], queryFn: getGroups })
  const marketQ = useQuery({ queryKey: ['market-summary'], queryFn: () => getMarketSummary(), staleTime: 5 * 60_000 })
  const { items } = useSignalsQuery()

  useEffect(() => {
    if (batchDoneRef.current && batchState && !batchState.running) {
      setBatchState(null)
      batchDoneRef.current = false
    }
  }, [items])

  const syncMut = useMutation({
    mutationKey: SYNC_ALL_KEY,
    mutationFn: runSync,
    onSuccess: () => {
      message.success('同步完成')
      globalInv.afterSync()
    },
  })

  const addMut = useMutation({
    mutationFn: (code: string) => addWatchlist(code),
    onSuccess: (d) => {
      message.success(`已加入 ${d.name || d.code}`)
      inv.both()
      setAddValue('')
      setAddOpen(false)
    },
  })

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
          inv.signals()
        } else {
          qc.invalidateQueries({ queryKey: ['action-plan'] })
          inv.signals()
        }
        setTimeout(() => { batchDoneRef.current = true }, 2000)
      }
    })
    setSelectMode(false)
    setSelected(new Set())
  }, [selected, qc, globalInv, inv])

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
          syncLoading={syncingElsewhere}
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
                  onOk: () => removeWatchlist(item.code).then(() => inv.both()).catch(() => message.error('移除失败')),
                })
              }}
              onGroupChange={(gids) => {
                patchStock(item.code, { group_ids: gids }).then(() => inv.both()).catch(() => message.error('分组修改失败'))
              }}
              onSync={() => {
                syncSingleStock(item.code).then(() => {
                  message.success(`${item.name} 同步完成`)
                  globalInv.afterSyncSingle(item.code)
                }).catch(() => message.error(`${item.name} 同步失败`))
              }}
              onOpenScore={(code) => navigate(`/scoreboard?code=${code}`)}
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
        onChange={() => inv.both()}
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
