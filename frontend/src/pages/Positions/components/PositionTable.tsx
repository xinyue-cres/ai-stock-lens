/** 持仓表格：列定义 + 行内编辑/删除/跳转。columns 从 index.tsx 原样抽出。 */
import { Button, Card, Popconfirm, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined, EditOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { message } from 'antd'
import { deletePosition, type PositionSummary } from '@/api/positions'
import { priceColor, verdictPalette } from '@/shared/theme'

const { Text } = Typography

interface PositionTableProps {
  filtered: PositionSummary[]
  isLoading: boolean
  onEdit: (code: string, name?: string) => void
}

export function PositionTable({ filtered, isLoading, onEdit }: PositionTableProps) {
  const navigate = useNavigate()
  const qc = useQueryClient()

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

  const columns = [
    {
      title: '股票',
      dataIndex: 'code',
      fixed: 'left' as const,
      width: 140,
      render: (v: string, r?: PositionSummary) => (
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
      sorter: (a: PositionSummary, b: PositionSummary) => (a?.unrealized_pnl_pct ?? 0) - (b?.unrealized_pnl_pct ?? 0),
      render: (v?: number | null) =>
        v != null ? (
          <Tag color={v >= 0 ? 'red' : 'green'} style={{ margin: 0, fontWeight: 500 }}>
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
      sorter: (a: PositionSummary, b: PositionSummary) => (a?.today_pnl_pct ?? 0) - (b?.today_pnl_pct ?? 0),
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
      sorter: (a: PositionSummary, b: PositionSummary) => (a?.hold_days ?? 0) - (b?.hold_days ?? 0),
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
      render: (_v: unknown, r?: PositionSummary) => (
        <Space size={2}>
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={(e) => {
              e.stopPropagation()
              if (!r) return
              onEdit(r.code, r.name || undefined)
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
  ]

  return (
    <Card styles={{ body: { padding: 0 } }}>
      <Table
        rowKey="code"
        dataSource={filtered}
        loading={isLoading}
        pagination={false}
        size="middle"
        locale={{ emptyText: '当前筛选无结果' }}
        columns={columns}
      />
    </Card>
  )
}
