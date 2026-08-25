import { useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Space, Tag, Typography } from 'antd'
import { DollarOutlined, PlusOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { listPositions, PositionSummary } from '@/api/positions'
import { PositionEditModal } from '@/features/watchlist/PositionEditModal'
import { CapitalCard } from './components/CapitalCard'
import { PositionTable } from './components/PositionTable'
import { SummaryCards } from './components/SummaryCards'
import { useTotalCapital } from './hooks/useTotalCapital'
import { aggregate } from './utils/aggregate'

const { Title } = Typography

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
  const [filter, setFilter] = useState<FilterKey>('all')
  const [addOpen, setAddOpen] = useState(false)
  const [editingCode, setEditingCode] = useState<string | null>(null)
  const [editingName, setEditingName] = useState<string | undefined>(undefined)

  const { data: positions = [], isLoading } = useQuery({
    queryKey: ['positions-list'],
    queryFn: listPositions,
    refetchOnWindowFocus: false,
  })
  const currentCapital = useTotalCapital()

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

  return (
    <div style={{ maxWidth: 1300, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
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

      {/* 总资金设置：无论是否有持仓都显示 */}
      <CapitalCard />

      {positions.length > 0 && (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <SummaryCards summary={summary} currentCapital={currentCapital} />

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

          <PositionTable
            filtered={filtered}
            isLoading={isLoading}
            onEdit={(code, name) => {
              setEditingCode(code)
              setEditingName(name)
            }}
          />
        </Space>
      )}

      {/* 新增持仓 Modal（带股票搜索） */}
      <PositionEditModal code={null} open={addOpen} onClose={() => setAddOpen(false)} />
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
