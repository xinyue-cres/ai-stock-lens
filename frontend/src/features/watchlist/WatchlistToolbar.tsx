import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AutoComplete, Button, Space, Tooltip, Typography, message } from 'antd'
import { PlusOutlined, SyncOutlined } from '@ant-design/icons'
import { searchStocks, StockInfo } from '@/api/stocks'
import { syncSingleStock } from '@/api/sync'
import { useStock } from '@/features/stock-context'

const { Text } = Typography

interface Props {
  total: number
  onAdd: (code: string) => void
}

export function WatchlistToolbar({ total, onAdd }: Props) {
  const { code } = useStock()
  const qc = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)
  const [addValue, setAddValue] = useState('')

  const syncMut = useMutation({
    mutationFn: () => syncSingleStock(code),
    onSuccess: (r) => {
      message.success(`${code} 同步完成 · ${r.rows_inserted} 行`)
      qc.invalidateQueries({ queryKey: ['stock-analysis', code] })
      qc.invalidateQueries({ queryKey: ['signals-today'] })
    },
    onError: () => message.error('同步失败'),
  })

  const suggestQ = useQuery({
    queryKey: ['search', addValue],
    queryFn: () => searchStocks(addValue),
    enabled: addValue.length >= 1,
  })

  const options = (suggestQ.data || []).map((s: StockInfo) => ({
    value: s.code,
    label: (
      <Space size={6}>
        <Text strong>{s.name}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {s.code} · {s.market}
        </Text>
      </Space>
    ),
  }))

  const submit = (v: string) => {
    const trimmed = v.trim()
    if (!trimmed) return
    onAdd(trimmed)
    setAddValue('')
    setAddOpen(false)
  }

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Space size={4} style={{ width: '100%' }}>
        <Button
          icon={<PlusOutlined />}
          size="small"
          type={addOpen ? 'primary' : 'default'}
          onClick={() => setAddOpen((v) => !v)}
        >
          添加
        </Button>
        <Tooltip title={code ? `同步 ${code} 最新K线` : '请先选择股票'}>
          <Button
            icon={<SyncOutlined />}
            size="small"
            loading={syncMut.isPending}
            disabled={!code}
            onClick={() => syncMut.mutate()}
          />
        </Tooltip>
        <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
          共 {total} 只
        </Text>
      </Space>

      {addOpen && (
        <AutoComplete
          autoFocus
          size="small"
          style={{ width: '100%' }}
          placeholder="代码或名称"
          options={options}
          value={addValue}
          onChange={setAddValue}
          onSelect={submit}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && /^\d{6}$/.test(addValue.trim())) submit(addValue)
          }}
        />
      )}
    </Space>
  )
}
