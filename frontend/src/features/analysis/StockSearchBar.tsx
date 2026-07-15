import { useState } from 'react'
import { AutoComplete, Card, Space, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { searchStocks, StockInfo } from '@/api/stocks'
import { useStock, useStockName } from '@/features/stock-context'

const { Title, Text } = Typography

/** 右栏顶部：搜索任意 A 股 + 展示当前股票标题。 */
export function StockSearchBar() {
  const { code, setCode } = useStock()
  const name = useStockName()
  const [value, setValue] = useState('')

  const suggestQ = useQuery({
    queryKey: ['search', value],
    queryFn: () => searchStocks(value),
    enabled: value.length >= 1,
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

  const submit = (c: string) => {
    setCode(c.trim())
    setValue('')
  }

  return (
    <Card size="small">
      <Space wrap size={16} align="center" style={{ width: '100%' }}>
        <AutoComplete
          style={{ width: 320 }}
          placeholder="搜索任意 A 股（代码或名称，如 600519、茅台）"
          options={options}
          value={value}
          onChange={setValue}
          onSelect={submit}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && /^\d{6}$/.test(value.trim())) submit(value)
          }}
        />
        {code && (
          <Title level={5} style={{ margin: 0 }}>
            {name ? (
              <>
                {name}{' '}
                <Text type="secondary" style={{ fontSize: 14, fontWeight: 400 }}>
                  {code}
                </Text>
              </>
            ) : (
              <Text type="secondary">{code} · 加载中…</Text>
            )}
          </Title>
        )}
      </Space>
    </Card>
  )
}
