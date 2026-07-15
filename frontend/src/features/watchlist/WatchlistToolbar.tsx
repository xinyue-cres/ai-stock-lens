import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AutoComplete, Button, Space, Tooltip, Typography } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { searchStocks, StockInfo } from '@/api/stocks'

const { Text } = Typography

interface Props {
  total: number
  syncLoading: boolean
  onAdd: (code: string) => void
  onSync: () => void
}

export function WatchlistToolbar({ total, syncLoading, onAdd, onSync }: Props) {
  const [addOpen, setAddOpen] = useState(false)
  const [addValue, setAddValue] = useState('')

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
        <Tooltip title="立即同步自选股">
          <Button icon={<ReloadOutlined />} size="small" loading={syncLoading} onClick={onSync} />
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
