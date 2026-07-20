import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AutoComplete, Button, Dropdown, Input, message, Modal, Segmented, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, FolderOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getTodaySignals, SignalItem } from '@/api/signals'
import { getGroups, patchStock, StockGroup } from '@/api/groups'
import { addWatchlist, removeWatchlist } from '@/api/watchlist'
import { searchStocks, StockInfo } from '@/api/stocks'
import { runSync } from '@/api/sync'
import { priceColor, verdictPalette, Verdict } from '@/shared/theme'

const { Text } = Typography

const stanceLabel: Record<string, { label: string; color: string }> = {
  opportunistic_buy: { label: '择机买入', color: 'red' },
  wait: { label: '等待', color: 'blue' },
  trim: { label: '逢高减', color: 'orange' },
  hold: { label: '持有', color: 'cyan' },
  reduce: { label: '减仓', color: 'volcano' },
  exit: { label: '离场', color: 'red' },
}

type SortKey = 'default' | 'pct_chg' | 'position'

export default function StockListPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [groupFilter, setGroupFilter] = useState<number | 'all'>('all')
  const [sortKey, setSortKey] = useState<SortKey>('default')
  const [search, setSearch] = useState('')
  const [addValue, setAddValue] = useState('')
  const [addOpen, setAddOpen] = useState(false)

  const groupsQ = useQuery({ queryKey: ['groups'], queryFn: getGroups })
  const signalsQ = useQuery({
    queryKey: ['signals-today', groupFilter === 'all' ? undefined : groupFilter],
    queryFn: () => getTodaySignals(groupFilter === 'all' ? {} : { group_id: groupFilter }),
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

  const removeMut = useMutation({
    mutationFn: (code: string) => removeWatchlist(code),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['signals-today'] })
      qc.invalidateQueries({ queryKey: ['groups'] })
    },
  })

  const suggestQ = useQuery({
    queryKey: ['search', addValue],
    queryFn: () => searchStocks(addValue),
    enabled: addValue.length >= 1,
  })

  const items: SignalItem[] = signalsQ.data?.items ?? []
  const groups: StockGroup[] = groupsQ.data ?? []

  const filtered = useMemo(() => {
    let arr = items
    if (search) {
      const k = search.toLowerCase()
      arr = arr.filter(i => i.code.includes(k) || (i.name || '').toLowerCase().includes(k))
    }
    const sorted = [...arr]
    if (sortKey === 'pct_chg') {
      sorted.sort((a, b) => (b.pct_chg ?? 0) - (a.pct_chg ?? 0))
    } else if (sortKey === 'position') {
      sorted.sort((a, b) => {
        const pa = a.position?.unrealized_pnl_pct ?? -999
        const pb = b.position?.unrealized_pnl_pct ?? -999
        return pb - pa
      })
    } else {
      sorted.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
    }
    return sorted
  }, [items, search, sortKey])

  const columns: ColumnsType<SignalItem> = [
    {
      title: '股票',
      dataIndex: 'name',
      width: 140,
      render: (_, r) => (
        <div>
          <Text strong style={{ fontSize: 13 }}>{r.name}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>{r.code}</Text>
        </div>
      ),
    },
    {
      title: '涨跌',
      dataIndex: 'pct_chg',
      width: 80,
      align: 'right',
      render: (v: number | undefined) => v != null ? (
        <span style={{ color: v >= 0 ? priceColor.up : priceColor.down, fontWeight: 600, fontSize: 13 }}>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}%
        </span>
      ) : '-',
    },
    {
      title: 'AI',
      dataIndex: 'ai_verdict',
      width: 70,
      render: (v: string | null | undefined) => {
        if (!v) return null
        const p = verdictPalette[(v as Verdict) || 'neutral']
        return <Tag style={{ margin: 0, color: p.color, borderColor: p.border, background: p.bg }}>{p.label}</Tag>
      },
    },
    {
      title: '操作指示',
      dataIndex: 'stance',
      width: 90,
      render: (s: SignalItem['stance']) => {
        if (!s || !stanceLabel[s.value]) return null
        const sl = stanceLabel[s.value]
        return <Tag color={sl.color} style={{ margin: 0 }}>{sl.label}</Tag>
      },
    },
    {
      title: '持仓',
      dataIndex: 'position',
      width: 90,
      render: (pos: SignalItem['position']) => {
        if (!pos) return <Text type="secondary" style={{ fontSize: 11 }}>—</Text>
        const pnl = pos.unrealized_pnl_pct
        if (typeof pnl !== 'number') return null
        return (
          <span style={{ fontSize: 12, color: pnl >= 0 ? priceColor.up : priceColor.down, fontWeight: 500 }}>
            {pnl >= 0 ? '+' : ''}{(pnl * 100).toFixed(1)}%
          </span>
        )
      },
    },
    {
      title: '分组',
      dataIndex: 'group_name',
      width: 70,
      render: (v: string | null | undefined) => v ? <Tag style={{ margin: 0 }}>{v}</Tag> : null,
    },
    {
      title: '备注',
      dataIndex: 'note',
      width: 120,
      ellipsis: true,
      render: (v: string | null | undefined) => v ? <Text type="secondary" style={{ fontSize: 11 }}>{v}</Text> : null,
    },
    {
      title: '日期',
      dataIndex: 'as_of_date',
      width: 80,
      render: (v: string | undefined) => v ? <Text type="secondary" style={{ fontSize: 11 }}>{v.slice(5)}</Text> : null,
    },
    {
      title: '',
      width: 40,
      render: (_, r) => (
        <ItemActions
          item={r}
          groups={groups}
          onRemove={() => {
            Modal.confirm({
              title: '移除自选？',
              content: `将从自选中移除 ${r.name || r.code}`,
              okText: '移除',
              okButtonProps: { danger: true },
              onOk: () => removeMut.mutate(r.code),
            })
          }}
          onGroupChange={(gid) => {
            patchStock(r.code, { group_id: gid }).then(() => {
              qc.invalidateQueries({ queryKey: ['signals-today'] })
              qc.invalidateQueries({ queryKey: ['groups'] })
            })
          }}
        />
      ),
    },
  ]

  const segOptions = [
    { label: `全部 (${items.length})`, value: 'all' as const },
    ...groups.map(g => ({ label: `${g.name} (${g.stock_count})`, value: g.id })),
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <Segmented
          options={segOptions}
          value={groupFilter}
          onChange={(v) => setGroupFilter(v as any)}
        />
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索"
          size="small"
          style={{ width: 140 }}
          value={search}
          onChange={e => setSearch(e.target.value)}
          allowClear
        />
        <Segmented
          size="small"
          options={[
            { label: '默认', value: 'default' },
            { label: '涨跌', value: 'pct_chg' },
            { label: '持仓', value: 'position' },
          ]}
          value={sortKey}
          onChange={(v) => setSortKey(v as SortKey)}
        />
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {addOpen ? (
            <AutoComplete
              autoFocus
              size="small"
              style={{ width: 180 }}
              placeholder="代码或名称"
              options={(suggestQ.data || []).map((s: StockInfo) => ({
                value: s.code,
                label: <span>{s.name} <Text type="secondary" style={{ fontSize: 11 }}>{s.code}</Text></span>,
              }))}
              value={addValue}
              onChange={setAddValue}
              onSelect={(v) => addMut.mutate(v)}
              onBlur={() => { if (!addValue) setAddOpen(false) }}
            />
          ) : (
            <Button size="small" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>添加</Button>
          )}
          <Button size="small" icon={<ReloadOutlined />} loading={syncMut.isPending} onClick={() => syncMut.mutate()}>
            同步
          </Button>
        </div>
      </div>

      <Table
        rowKey="code"
        dataSource={filtered}
        columns={columns}
        size="small"
        pagination={false}
        loading={signalsQ.isLoading}
        onRow={(r) => ({ onClick: () => navigate(`/stock/${r.code}`), style: { cursor: 'pointer' } })}
      />
    </div>
  )
}

function ItemActions({ item, groups, onRemove, onGroupChange }: {
  item: SignalItem
  groups: StockGroup[]
  onRemove: () => void
  onGroupChange: (groupId: number | null) => void
}) {
  const groupMenu = groups.map(g => ({
    key: `g-${g.id}`,
    label: g.name,
    onClick: () => onGroupChange(g.id),
  }))
  if (item.group_id) {
    groupMenu.push({ key: 'g-none', label: '取消分组', onClick: () => onGroupChange(0) })
  }

  const menu = {
    items: [
      { key: 'group', label: '移动到分组', icon: <FolderOutlined />, children: groupMenu.length ? groupMenu : [{ key: 'empty', label: '暂无分组', disabled: true }] },
      { type: 'divider' as const },
      { key: 'remove', label: '移除', icon: <DeleteOutlined />, danger: true, onClick: onRemove },
    ],
  }

  return (
    <Dropdown menu={menu} trigger={['click']} placement="bottomRight">
      <Button type="text" size="small" icon={<MoreOutlined />} onClick={e => e.stopPropagation()} />
    </Dropdown>
  )
}
