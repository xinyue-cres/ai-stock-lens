import { useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Empty,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  DeleteOutlined,
  DollarOutlined,
  EditOutlined,
  PlusOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { deletePosition, listPositions, PositionSummary } from '@/api/positions'
import { getCapital, saveCapital } from '@/api/settings'
import { PositionEditModal } from '@/features/watchlist/PositionEditModal'
import { priceColor, verdictPalette } from '@/shared/theme'

const { Title, Text } = Typography

type FilterKey = 'all' | 'profit' | 'loss' | 'bullish' | 'bearish'

const filters: { key: FilterKey; label: string; match: (p: PositionSummary) => boolean }[] = [
  { key: 'all', label: '全部', match: () => true },
  { key: 'profit', label: '盈利', match: (p) => (p.unrealized_pnl_pct ?? 0) > 0 },
  { key: 'loss', label: '亏损', match: (p) => (p.unrealized_pnl_pct ?? 0) < 0 },
  { key: 'bullish', label: 'AI 看多', match: (p) => p.verdict === 'bullish' },
  { key: 'bearish', label: 'AI 看空', match: (p) => p.verdict === 'bearish' },
]

/**
 * 持仓总览页：汇总卡片 + Tag 筛选 + 表格。
 * 支持顶栏新增、行内编辑/删除、点击跳工作台。
 */
export default function Positions() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [filter, setFilter] = useState<FilterKey>('all')
  const [addOpen, setAddOpen] = useState(false)
  const [editingCode, setEditingCode] = useState<string | null>(null)
  const [editingName, setEditingName] = useState<string | undefined>(undefined)

  const { data: positions = [], isLoading } = useQuery({
    queryKey: ['positions-list'],
    queryFn: listPositions,
    refetchOnWindowFocus: false,
  })

  const capitalQ = useQuery({
    queryKey: ['total-capital'],
    queryFn: getCapital,
  })
  const capitalMut = useMutation({
    mutationFn: (amount: number) => saveCapital(amount),
    onSuccess: () => {
      message.success('总资金已保存')
      qc.invalidateQueries({ queryKey: ['total-capital'] })
    },
  })
  const [capitalInput, setCapitalInput] = useState<number | null>(null)
  const currentCapital = capitalQ.data?.total_capital ?? null

  const summary = useMemo(() => aggregate(positions), [positions])
  const filtered = useMemo(
    () => positions.filter(filters.find((f) => f.key === filter)!.match),
    [positions, filter],
  )

  const filterCounts = useMemo(() => {
    return filters.reduce<Record<FilterKey, number>>(
      (acc, f) => ({ ...acc, [f.key]: positions.filter(f.match).length }),
      { all: 0, profit: 0, loss: 0, bullish: 0, bearish: 0 },
    )
  }, [positions])

  const delMut = useMutation({
    mutationFn: (code: string) => deletePosition(code),
    onSuccess: () => {
      message.success('已清除持仓')
      qc.invalidateQueries({ queryKey: ['positions-list'] })
      qc.invalidateQueries({ queryKey: ['signals'] })
      qc.invalidateQueries({ queryKey: ['watchlist'] })
    },
    onError: () => message.error('删除失败'),
  })

  return (
    <div style={{ maxWidth: 1300, margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          <DollarOutlined style={{ color: '#7c3aed', marginRight: 8 }} />
          持仓总览
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
          新增持仓
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="持仓仅用于让 Trader Agent 出个性化建议（加仓/止盈/止损），本工具不涉及任何交易执行"
      />

      {positions.length === 0 && !isLoading && (
        <Card>
          <Empty description="尚未录入任何持仓">
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
              录入第一笔持仓
            </Button>
          </Empty>
        </Card>
      )}

      {positions.length > 0 && (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card>
            <Space size={40} wrap>
              <Statistic title="持仓只数" value={summary.count} />
              <Statistic
                title="总市值"
                value={summary.marketValue ?? '-'}
                precision={2}
                prefix="¥"
              />
              <Statistic
                title="总成本"
                value={summary.totalCost ?? '-'}
                precision={2}
                prefix="¥"
              />
              <Statistic
                title="累计浮盈"
                value={summary.totalPnl ?? '-'}
                precision={2}
                prefix="¥"
                valueStyle={{
                  color: (summary.totalPnl ?? 0) >= 0 ? priceColor.up : priceColor.down,
                }}
              />
              <Statistic
                title="浮盈占比"
                value={summary.pnlPct != null ? summary.pnlPct * 100 : '-'}
                precision={2}
                suffix="%"
                valueStyle={{
                  color: (summary.pnlPct ?? 0) >= 0 ? priceColor.up : priceColor.down,
                }}
              />
              <Statistic
                title="今日浮盈"
                value={summary.todayPnl ?? '-'}
                precision={2}
                prefix="¥"
                valueStyle={{
                  color: (summary.todayPnl ?? 0) >= 0 ? priceColor.up : priceColor.down,
                }}
              />
              <div>
                <Tooltip title="总资金用于 Trader 计算具体仓位建议（股数 = 100 的整数倍）">
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <WalletOutlined style={{ marginRight: 4 }} />
                    总资金
                  </Text>
                </Tooltip>
                <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <InputNumber
                    size="small"
                    style={{ width: 130 }}
                    min={1000}
                    step={10000}
                    placeholder="如 100000"
                    value={capitalInput ?? currentCapital ?? undefined}
                    onChange={(v) => setCapitalInput(v)}
                    formatter={(v) => v ? `¥ ${Number(v).toLocaleString()}` : ''}
                    parser={(v) => Number((v || '').replace(/[¥,\s]/g, '')) as any}
                  />
                  <Button
                    size="small"
                    type="primary"
                    disabled={!capitalInput || capitalInput === currentCapital}
                    loading={capitalMut.isPending}
                    onClick={() => capitalInput && capitalMut.mutate(capitalInput)}
                  >
                    保存
                  </Button>
                </div>
                {currentCapital && summary.marketValue != null && (
                  <Text type="secondary" style={{ fontSize: 11, marginTop: 2, display: 'block' }}>
                    仓位占比 {((summary.marketValue / currentCapital) * 100).toFixed(1)}%
                  </Text>
                )}
              </div>
            </Space>
          </Card>

          {/* Tag 筛选器 */}
          <Card size="small" styles={{ body: { padding: '12px 16px' } }}>
            <Space wrap size={[6, 8]}>
              {filters.map((f) => (
                <Tag.CheckableTag
                  key={f.key}
                  checked={filter === f.key}
                  onChange={() => setFilter(f.key)}
                  style={{ fontSize: 13, padding: '4px 10px', borderRadius: 4 }}
                >
                  {f.label}
                  <span
                    style={{
                      marginLeft: 6,
                      color: filter === f.key ? 'rgba(255,255,255,0.85)' : '#94a3b8',
                      fontSize: 11,
                    }}
                  >
                    {filterCounts[f.key]}
                  </span>
                </Tag.CheckableTag>
              ))}
            </Space>
          </Card>

          <Card styles={{ body: { padding: 0 } }}>
            <Table
              rowKey="code"
              dataSource={filtered}
              loading={isLoading}
              pagination={false}
              size="middle"
              locale={{ emptyText: '当前筛选无结果' }}
              columns={[
                {
                  title: '股票',
                  dataIndex: 'code',
                  fixed: 'left' as const,
                  width: 140,
                  render: (v, r?: PositionSummary) => (
                    <div style={{ cursor: 'pointer' }} onClick={() => navigate(`/stock/${v}`)}>
                      <div style={{ fontWeight: 500 }}>{r?.name || v}</div>
                      <Text type="secondary" style={{ fontFamily: 'monospace', fontSize: 11 }}>
                        {v}
                      </Text>
                    </div>
                  ),
                },
                {
                  title: 'AI',
                  dataIndex: 'verdict',
                  width: 76,
                  render: (v?: string | null) => {
                    if (!v) return <Text type="secondary" style={{ fontSize: 11 }}>-</Text>
                    const p = verdictPalette[v as keyof typeof verdictPalette] || verdictPalette.neutral
                    return (
                      <Tag color={p.color} style={{ margin: 0, color: '#fff', border: 'none' }}>
                        {p.label}
                      </Tag>
                    )
                  },
                },
                {
                  title: '持股',
                  dataIndex: 'quantity',
                  align: 'right' as const,
                  render: (v: number) => v.toLocaleString(),
                },
                {
                  title: '成本',
                  dataIndex: 'cost_price',
                  align: 'right' as const,
                  render: (v: number) => v.toFixed(3),
                },
                {
                  title: '现价',
                  dataIndex: 'latest_close',
                  align: 'right' as const,
                  render: (v?: number | null) =>
                    v != null ? v.toFixed(2) : <Text type="secondary">-</Text>,
                },
                {
                  title: '市值',
                  dataIndex: 'market_value',
                  align: 'right' as const,
                  render: (v?: number | null) =>
                    v != null
                      ? '¥' + v.toLocaleString(undefined, { maximumFractionDigits: 0 })
                      : '-',
                },
                {
                  title: '浮盈%',
                  dataIndex: 'unrealized_pnl_pct',
                  align: 'right' as const,
                  sorter: (a, b) => (a?.unrealized_pnl_pct ?? 0) - (b?.unrealized_pnl_pct ?? 0),
                  render: (v?: number | null) =>
                    v != null ? (
                      <Tag
                        color={v >= 0 ? 'red' : 'green'}
                        style={{ margin: 0, fontWeight: 500 }}
                      >
                        {v >= 0 ? '+' : ''}
                        {(v * 100).toFixed(2)}%
                      </Tag>
                    ) : (
                      <Text type="secondary">-</Text>
                    ),
                },
                {
                  title: '今日',
                  dataIndex: 'today_pnl_pct',
                  align: 'right' as const,
                  sorter: (a, b) => (a?.today_pnl_pct ?? 0) - (b?.today_pnl_pct ?? 0),
                  render: (v?: number | null, r?: PositionSummary) => {
                    if (v == null) return <Text type="secondary">-</Text>
                    const color = v >= 0 ? priceColor.up : priceColor.down
                    return (
                      <div style={{ lineHeight: 1.2 }}>
                        <div style={{ color, fontWeight: 500 }}>
                          {v >= 0 ? '+' : ''}
                          {(v * 100).toFixed(2)}%
                        </div>
                        {r?.today_pnl != null && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {r.today_pnl >= 0 ? '+' : ''}
                            {r.today_pnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                          </Text>
                        )}
                      </div>
                    )
                  },
                },
                {
                  title: '持有',
                  dataIndex: 'hold_days',
                  align: 'right' as const,
                  sorter: (a, b) => (a?.hold_days ?? 0) - (b?.hold_days ?? 0),
                  render: (v?: number | null, r?: PositionSummary) => (
                    <div style={{ lineHeight: 1.2 }}>
                      <div>{v} 天</div>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {r?.opened_at}
                      </Text>
                    </div>
                  ),
                },
                {
                  title: '备注',
                  dataIndex: 'note',
                  ellipsis: true,
                  render: (v?: string | null) =>
                    v ? (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {v}
                      </Text>
                    ) : null,
                },
                {
                  title: '',
                  key: 'ops',
                  width: 90,
                  align: 'center' as const,
                  render: (_v, r?: PositionSummary) => (
                    <Space size={2}>
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (!r) return
                          setEditingCode(r.code)
                          setEditingName(r.name || undefined)
                        }}
                      />
                      <Popconfirm
                        title="清除该持仓？"
                        onConfirm={() => r && delMut.mutate(r.code)}
                        okText="清除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                      >
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        </Space>
      )}

      {/* 新增持仓 Modal（带股票搜索） */}
      <PositionEditModal
        code={null}
        open={addOpen}
        onClose={() => setAddOpen(false)}
      />
      {/* 编辑持仓 Modal */}
      <PositionEditModal
        code={editingCode}
        name={editingName}
        open={!!editingCode}
        onClose={() => setEditingCode(null)}
      />
    </div>
  )
}

interface Aggregate {
  count: number
  totalCost: number | null
  marketValue: number | null
  totalPnl: number | null
  pnlPct: number | null
  todayPnl: number | null
}

function aggregate(list: PositionSummary[]): Aggregate {
  if (list.length === 0) {
    return {
      count: 0,
      totalCost: null,
      marketValue: null,
      totalPnl: null,
      pnlPct: null,
      todayPnl: null,
    }
  }
  let totalCost = 0
  let marketValue = 0
  let todayPnl = 0
  let hasMV = true
  let hasToday = true
  for (const p of list) {
    totalCost += p.quantity * p.cost_price
    if (p.market_value != null) marketValue += p.market_value
    else hasMV = false
    if (p.today_pnl != null) todayPnl += p.today_pnl
    else hasToday = false
  }
  const totalPnl = hasMV ? marketValue - totalCost : null
  const pnlPct = hasMV && totalCost > 0 ? totalPnl! / totalCost : null
  return {
    count: list.length,
    totalCost,
    marketValue: hasMV ? marketValue : null,
    totalPnl,
    pnlPct,
    todayPnl: hasToday ? todayPnl : null,
  }
}
