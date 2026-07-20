import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AutoComplete, Button, Dropdown, Input, message, Modal, Segmented, Space, Tag, Tooltip, Typography } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, EditOutlined, FolderOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, SettingOutlined, SortAscendingOutlined, SyncOutlined } from '@ant-design/icons'
import { getTodaySignals, SignalItem } from '@/api/signals'
import { createGroup, deleteGroup, getGroups, patchStock, StockGroup, updateGroup } from '@/api/groups'
import { addWatchlist, removeWatchlist } from '@/api/watchlist'
import { syncSingleStock, runSync } from '@/api/sync'
import { searchStocks, StockInfo } from '@/api/stocks'
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

const actionableStances = new Set(['opportunistic_buy', 'trim', 'reduce', 'exit'])

type SortKey = 'default' | 'pct_chg' | 'position' | 'confidence' | 'name'
type SortDir = 'asc' | 'desc'

const sortLabels: Record<SortKey, string> = {
  default: '默认',
  pct_chg: '涨跌幅',
  position: '持仓盈亏',
  confidence: 'AI 置信度',
  name: '名称',
}

export default function StockListPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [groupFilter, setGroupFilter] = useState<number | 'all'>('all')
  const [sortKey, setSortKey] = useState<SortKey>('default')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [search, setSearch] = useState('')
  const [addValue, setAddValue] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [groupMgrOpen, setGroupMgrOpen] = useState(false)

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

  // --- 摘要统计 ---
  const summary = useMemo(() => {
    let up = 0, down = 0, flat = 0
    let posTotal = 0, posCount = 0
    let attention = 0
    for (const item of items) {
      if (item.empty) continue
      const pct = item.pct_chg ?? 0
      if (pct > 0.1) up++
      else if (pct < -0.1) down++
      else flat++
      if (item.position?.unrealized_pnl_pct != null) {
        posTotal += item.position.unrealized_pnl_pct
        posCount++
      }
      if (item.stance && actionableStances.has(item.stance.value)) attention++
    }
    return { up, down, flat, posTotal, posCount, attention }
  }, [items])

  // --- 过滤 + 排序 ---
  const filtered = useMemo(() => {
    let arr = items
    if (search) {
      const k = search.toLowerCase()
      arr = arr.filter(i => i.code.includes(k) || (i.name || '').toLowerCase().includes(k))
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
    } else if (sortKey === 'confidence') {
      sorted.sort((a, b) => {
        const ca = (a.stance as any)?.confidence ?? 0
        const cb = (b.stance as any)?.confidence ?? 0
        return (ca - cb) * dir
      })
    } else if (sortKey === 'name') {
      sorted.sort((a, b) => (a.name || '').localeCompare(b.name || '') * dir)
    } else {
      sorted.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
    }
    return sorted
  }, [items, search, sortKey, sortDir])

  // --- 按分组分 section ---
  const sections = useMemo(() => {
    if (groupFilter !== 'all') return [{ groupName: null, items: filtered }]
    const grouped: Record<string, SignalItem[]> = {}
    const order: string[] = []
    for (const item of filtered) {
      const key = item.group_name || '未分组'
      if (!grouped[key]) { grouped[key] = []; order.push(key) }
      grouped[key].push(item)
    }
    // 按 group sort_order 排，未分组排最后
    const groupOrder = groups.map(g => g.name)
    order.sort((a, b) => {
      if (a === '未分组') return 1
      if (b === '未分组') return -1
      const ia = groupOrder.indexOf(a)
      const ib = groupOrder.indexOf(b)
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
    return order.map(name => ({ groupName: name, items: grouped[name] }))
  }, [filtered, groupFilter, groups])

  const segOptions = [
    { label: `全部 (${items.length})`, value: 'all' as const },
    ...groups.map(g => ({ label: `${g.name} (${g.stock_count})`, value: g.id })),
  ]

  return (
    <div>
      {/* 摘要条 */}
      <div style={{ display: 'flex', gap: 24, marginBottom: 16, padding: '12px 16px', background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0' }}>
        <SummaryCard
          label="涨跌分布"
          content={
            <span style={{ fontSize: 15, fontWeight: 600 }}>
              <span style={{ color: priceColor.up }}>{summary.up}↑</span>
              {' '}<span style={{ color: '#9ca3af' }}>{summary.flat}→</span>
              {' '}<span style={{ color: priceColor.down }}>{summary.down}↓</span>
            </span>
          }
        />
        <SummaryCard
          label="持仓盈亏"
          content={
            summary.posCount > 0 ? (
              <span style={{ fontSize: 15, fontWeight: 600, color: summary.posTotal >= 0 ? priceColor.up : priceColor.down }}>
                {summary.posTotal >= 0 ? '+' : ''}{(summary.posTotal * 100 / summary.posCount).toFixed(1)}% 均
              </span>
            ) : <span style={{ color: '#9ca3af' }}>无持仓</span>
          }
        />
        <SummaryCard
          label="需关注"
          content={
            <span style={{ fontSize: 15, fontWeight: 600, color: summary.attention > 0 ? '#dc2626' : '#9ca3af' }}>
              {summary.attention} 只
            </span>
          }
        />
      </div>

      {/* 操作栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <Segmented options={segOptions} value={groupFilter} onChange={(v) => setGroupFilter(v as any)} size="small" />
        <Tooltip title="管理分组">
          <Button size="small" icon={<SettingOutlined />} onClick={() => setGroupMgrOpen(true)} />
        </Tooltip>
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索"
          size="small"
          style={{ width: 140 }}
          value={search}
          onChange={e => setSearch(e.target.value)}
          allowClear
        />
        <Dropdown
          menu={{
            items: (Object.keys(sortLabels) as SortKey[]).map(k => ({
              key: k,
              label: sortLabels[k],
              onClick: () => { setSortKey(k); if (k === 'default') setSortDir('desc') },
            })),
            selectedKeys: [sortKey],
          }}
          trigger={['click']}
        >
          <Button size="small" icon={<SortAscendingOutlined />}>
            {sortLabels[sortKey]}
          </Button>
        </Dropdown>
        {sortKey !== 'default' && (
          <Button
            size="small"
            icon={sortDir === 'desc' ? <ArrowDownOutlined /> : <ArrowUpOutlined />}
            onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
          />
        )}
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

      {/* 分组列表 */}
      <div style={{ background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0', overflow: 'hidden' }}>
        {sections.map((section, si) => (
          <div key={section.groupName || si}>
            {section.groupName && sections.length > 1 && (
              <div style={{ padding: '8px 16px', background: '#fafafa', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Text strong style={{ fontSize: 12, color: '#6b7280' }}>{section.groupName}</Text>
                <Text type="secondary" style={{ fontSize: 11 }}>({section.items.length})</Text>
              </div>
            )}
            {section.items.map(item => (
              <StockRow
                key={item.code}
                item={item}
                groups={groups}
                onClick={() => navigate(`/stock/${item.code}`)}
                onRemove={() => {
                  Modal.confirm({
                    title: '移除自选？',
                    content: `将从自选中移除 ${item.name || item.code}`,
                    okText: '移除',
                    okButtonProps: { danger: true },
                    onOk: () => removeMut.mutate(item.code),
                  })
                }}
                onGroupChange={(gid) => {
                  patchStock(item.code, { group_id: gid }).then(() => {
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
          </div>
        ))}
        {filtered.length === 0 && (
          <div style={{ padding: '40px 0', textAlign: 'center', color: '#9ca3af' }}>
            {items.length === 0 ? '还没有自选股，点击「添加」开始' : '当前筛选无结果'}
          </div>
        )}
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
    </div>
  )
}

function SummaryCard({ label, content }: { label: string; content: React.ReactNode }) {
  return (
    <div>
      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 2 }}>{label}</Text>
      {content}
    </div>
  )
}

function getHeatColor(item: SignalItem): string | null {
  if (item.stance && actionableStances.has(item.stance.value)) return '#dc2626'
  const pct = item.pct_chg ?? 0
  if (Math.abs(pct) >= 3) return '#f59e0b'
  return null
}

function StockRow({ item, groups, onClick, onRemove, onGroupChange, onSync }: {
  item: SignalItem
  groups: StockGroup[]
  onClick: () => void
  onRemove: () => void
  onGroupChange: (gid: number | null) => void
  onSync: () => void
}) {
  const [hovered, setHovered] = useState(false)
  const heat = getHeatColor(item)
  const pct = item.pct_chg
  const pos = item.position
  const posPnl = pos?.unrealized_pnl_pct

  const groupMenu = groups.map(g => ({
    key: `g-${g.id}`,
    label: g.name,
    onClick: () => onGroupChange(g.id),
  }))
  if (item.group_id) {
    groupMenu.push({ key: 'g-none', label: '取消分组', onClick: () => onGroupChange(0) })
  }

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '10px 16px',
        borderBottom: '1px solid #f5f5f5',
        cursor: 'pointer',
        background: hovered ? '#f9fafb' : '#fff',
        borderLeft: `3px solid ${heat || 'transparent'}`,
        transition: 'background 0.1s',
      }}
    >
      {/* 左：名称 + 涨跌 */}
      <div style={{ width: 160, flexShrink: 0 }}>
        <div style={{ fontWeight: 500, fontSize: 13, lineHeight: 1.3 }}>{item.name || item.code}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>{item.code}</Text>
          {typeof pct === 'number' && (
            <span style={{ fontSize: 12, fontWeight: 600, color: pct >= 0 ? priceColor.up : priceColor.down }}>
              {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
            </span>
          )}
        </div>
      </div>

      {/* 中：AI verdict + stance */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 6 }}>
        {item.ai_verdict && (() => {
          const p = verdictPalette[(item.ai_verdict as Verdict) || 'neutral']
          return <Tag style={{ margin: 0, color: p.color, borderColor: p.border, background: p.bg, fontSize: 11 }}>{p.label}</Tag>
        })()}
        {item.stance && stanceLabel[item.stance.value] && (
          <Tag color={stanceLabel[item.stance.value].color} style={{ margin: 0, fontSize: 11 }}>
            {stanceLabel[item.stance.value].label}
          </Tag>
        )}
        {item.note && (
          <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>{item.note}</Text>
        )}
      </div>

      {/* 右：持仓 + 日期 + 操作 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        {typeof posPnl === 'number' && (
          <span style={{ fontSize: 12, fontWeight: 500, color: posPnl >= 0 ? priceColor.up : priceColor.down, minWidth: 60, textAlign: 'right' }}>
            持仓 {posPnl >= 0 ? '+' : ''}{(posPnl * 100).toFixed(1)}%
          </span>
        )}
        {item.as_of_date && (
          <Text type="secondary" style={{ fontSize: 10, minWidth: 40, textAlign: 'right' }}>{item.as_of_date.slice(5)}</Text>
        )}

        {/* hover 快捷操作 */}
        <div style={{ width: 56, display: 'flex', gap: 2, visibility: hovered ? 'visible' : 'hidden' }}>
          <Tooltip title="同步">
            <Button type="text" size="small" icon={<SyncOutlined style={{ fontSize: 12 }} />} onClick={e => { e.stopPropagation(); onSync() }} />
          </Tooltip>
          <Dropdown
            menu={{
              items: [
                { key: 'group', label: '移动到分组', icon: <FolderOutlined />, children: groupMenu.length ? groupMenu : [{ key: 'empty', label: '暂无分组', disabled: true }] },
                { type: 'divider' },
                { key: 'remove', label: '移除', icon: <DeleteOutlined />, danger: true, onClick: (e: any) => { onRemove() } },
              ],
            }}
            trigger={['click']}
            placement="bottomRight"
          >
            <Button type="text" size="small" icon={<MoreOutlined style={{ fontSize: 12 }} />} onClick={e => e.stopPropagation()} />
          </Dropdown>
        </div>
      </div>
    </div>
  )
}

function GroupManagerModal({ open, groups, onClose, onChange }: {
  open: boolean
  groups: StockGroup[]
  onClose: () => void
  onChange: () => void
}) {
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editingName, setEditingName] = useState('')

  const handleAdd = async () => {
    const name = newName.trim()
    if (!name) return
    await createGroup(name, groups.length)
    setNewName('')
    onChange()
  }

  const handleRename = async (id: number) => {
    const name = editingName.trim()
    if (!name) return
    await updateGroup(id, { name })
    setEditingId(null)
    onChange()
  }

  const handleDelete = async (id: number, name: string) => {
    Modal.confirm({
      title: `删除分组「${name}」？`,
      content: '组内股票将变为未分组，不会从自选中移除。',
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteGroup(id)
        onChange()
      },
    })
  }

  return (
    <Modal title="管理分组" open={open} onCancel={onClose} footer={null} width={360}>
      <div style={{ marginBottom: 12 }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder="新分组名称"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onPressEnter={handleAdd}
          />
          <Button type="primary" onClick={handleAdd} disabled={!newName.trim()}>添加</Button>
        </Space.Compact>
      </div>
      <div>
        {groups.map(g => (
          <div key={g.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid #f5f5f5' }}>
            {editingId === g.id ? (
              <Input
                size="small"
                autoFocus
                value={editingName}
                onChange={e => setEditingName(e.target.value)}
                onPressEnter={() => handleRename(g.id)}
                onBlur={() => setEditingId(null)}
                style={{ flex: 1 }}
              />
            ) : (
              <span style={{ flex: 1, fontSize: 13 }}>{g.name} <Text type="secondary" style={{ fontSize: 11 }}>({g.stock_count})</Text></span>
            )}
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => { setEditingId(g.id); setEditingName(g.name) }}
            />
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(g.id, g.name)}
            />
          </div>
        ))}
        {groups.length === 0 && (
          <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: '16px 0' }}>
            还没有分组
          </Text>
        )}
      </div>
    </Modal>
  )
}
