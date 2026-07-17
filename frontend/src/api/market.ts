import { api } from './client'

export interface IndexInfo {
  code: string
  name: string
  pct_1d: number | null
  pct_5d: number | null
  pct_20d: number | null
  latest_close: number | null
}

export type MarketMood = 'strong' | 'positive' | 'neutral' | 'weak' | 'panic'
export type StockRelative = 'far_outperform' | 'outperform' | 'inline' | 'underperform' | 'far_underperform'

export interface MarketSummary {
  indices: IndexInfo[]
  mood: MarketMood
  avg_pct_1d: number
  stock_relative: StockRelative | null
}

export async function getMarketSummary(stockPct?: number): Promise<MarketSummary> {
  const params: Record<string, any> = {}
  if (stockPct !== undefined) params.stock_pct = stockPct
  const { data } = await api.get('/market/summary', { params })
  return data
}
