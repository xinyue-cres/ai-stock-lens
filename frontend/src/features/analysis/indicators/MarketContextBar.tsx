import { useQuery } from '@tanstack/react-query'
import { Space, Tag, Typography } from 'antd'
import { getMarketSummary, MarketMood, StockRelative } from '@/api/market'
import { useStockAnalysis } from '@/features/stock-context'
import { priceColor } from '@/shared/theme'

const { Text } = Typography

const moodLabel: Record<MarketMood, { label: string; color: string }> = {
  strong: { label: '市场强势', color: 'red' },
  positive: { label: '市场偏强', color: 'volcano' },
  neutral: { label: '市场震荡', color: 'default' },
  weak: { label: '市场偏弱', color: 'blue' },
  panic: { label: '市场恐慌', color: 'green' },
}

const relativeLabel: Record<StockRelative, { label: string; color: string }> = {
  far_outperform: { label: '大幅跑赢大盘', color: 'red' },
  outperform: { label: '跑赢大盘', color: 'volcano' },
  inline: { label: '与大盘同步', color: 'default' },
  underperform: { label: '跑输大盘', color: 'blue' },
  far_underperform: { label: '大幅跑输大盘', color: 'green' },
}

export function MarketContextBar() {
  const { data: kline } = useStockAnalysis()
  const stockPct = (kline as any)?.indicators?.latest_price?.pct_chg as number | undefined

  const { data } = useQuery({
    queryKey: ['market-summary', stockPct],
    queryFn: () => getMarketSummary(stockPct ?? undefined),
    refetchInterval: 5 * 60_000,
    staleTime: 60_000,
  })

  if (!data || data.indices.length === 0) return null

  const mood = moodLabel[data.mood]

  return (
    <Space wrap size={[6, 4]} style={{ padding: '4px 12px', fontSize: 12 }}>
      <Tag color={mood.color} style={{ margin: 0 }}>{mood.label}</Tag>
      {data.indices.map((idx) => (
        <Text key={idx.code} style={{ fontSize: 12 }}>
          <span style={{ color: '#6b7280' }}>{idx.name.replace('指数', '')}</span>
          {' '}
          <span style={{ color: (idx.pct_1d ?? 0) >= 0 ? priceColor.up : priceColor.down }}>
            {(idx.pct_1d ?? 0) >= 0 ? '+' : ''}{(idx.pct_1d ?? 0).toFixed(2)}%
          </span>
        </Text>
      ))}
      {data.stock_relative && relativeLabel[data.stock_relative] && (
        <Tag color={relativeLabel[data.stock_relative].color} style={{ margin: 0 }}>
          {relativeLabel[data.stock_relative].label}
        </Tag>
      )}
    </Space>
  )
}
