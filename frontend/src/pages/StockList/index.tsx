import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useIsMutating, useMutation, useQueryClient } from '@tanstack/react-query'
import { message, Modal } from 'antd'
import { patchStock } from '@/api/groups'
import { addWatchlist, removeWatchlist } from '@/api/watchlist'
import { syncSingleStock, runSync } from '@/api/sync'
import { useSignalsQuery } from '@/hooks/useSignalsQuery'
import { SYNC_ALL_KEY, useInvalidation } from '@/hooks/useInvalidation'
import { SortKey, SortDir } from './constants'
import SummaryBar from './components/SummaryBar'
import Toolbar from './components/Toolbar'
import StockRow from './components/StockRow'
import GroupNav from './components/GroupNav'
import GroupManagerModal from './components/GroupManagerModal'
import BatchActionBar from './components/BatchActionBar'
import { useStockListData } from './hooks/useStockListData'
import { useBatchTask } from './hooks/useBatchTask'

export default function StockListPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const qc = useQueryClient()
  const globalInv = useInvalidation()
  const syncingElsewhere = useIsMutating({ mutationKey: SYNC_ALL_KEY }) > 0
  // useMemo 稳定引用：作为 useCallback 依赖时不让每次 render 重建把回调失效（L3-3）
  const inv = useMemo(() => ({
    signals: () => qc.invalidateQueries({ queryKey: ['signals-today'] }),
    groups: () => qc.invalidateQueries({ queryKey: ['groups'] }),
    both: () => {
      qc.invalidateQueries({ queryKey: ['signals-today'] })
      qc.invalidateQueries({ queryKey: ['groups'] })
    },
  }), [qc])

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

  const { items, groups, market, filtered } = useStockListData({
    groupFilter, search, dirFilter, sortKey, sortDir,
  })

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

  const batch = useBatchTask(
    () => { setSelectMode(false); setSelected(new Set()) },
    inv.signals,
    items,
  )

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
        <SummaryBar items={items} market={market} />

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
              batchStatus={batch.getStatus(item.code)}
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
        batchRunning={batch.running}
        batchType={batch.type}
        batchCompleted={batch.completed}
        batchTotal={batch.total}
        onBatchStart={(type) => batch.start(type, selected)}
      />
    </div>
  )
}
