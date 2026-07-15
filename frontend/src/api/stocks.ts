import { api } from './client'

export interface StockInfo {
  code: string
  name: string
  market: string
}

export async function searchStocks(q: string): Promise<StockInfo[]> {
  const { data } = await api.get<StockInfo[]>('/stocks/search', { params: { q } })
  return data
}

export async function getKline(code: string) {
  const { data } = await api.get(`/stocks/${code}/kline`)
  return data
}
