import { api } from './client'

export interface PositionSummary {
  code: string
  name?: string | null
  quantity: number
  cost_price: number
  opened_at: string
  note?: string | null
  latest_close?: number | null
  unrealized_pnl_pct?: number | null
  market_value?: number | null
  today_pnl?: number | null
  today_pnl_pct?: number | null
  verdict?: 'bullish' | 'bearish' | 'neutral' | 'caution' | null
  hold_days?: number | null
  updated_at?: string
}

export interface PositionPayload {
  code: string
  quantity: number
  cost_price: number
  opened_at: string  // YYYY-MM-DD
  note?: string | null
}

export async function listPositions() {
  const { data } = await api.get<PositionSummary[]>('/positions')
  return data
}

export async function getPosition(code: string) {
  const { data } = await api.get<PositionSummary>(`/positions/${code}`)
  return data
}

export async function upsertPosition(payload: PositionPayload) {
  const { data } = await api.post<PositionSummary>('/positions', payload)
  return data
}

export async function deletePosition(code: string) {
  const { data } = await api.delete(`/positions/${code}`)
  return data as { ok: boolean }
}
