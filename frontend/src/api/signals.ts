import { api } from './client'
import type { PositionSummary } from './positions'

export interface Signal {
  key: string
  category: string
  direction: 'bullish' | 'bearish' | 'neutral'
  label: string
  detail?: string
  weight: number
}

export interface StanceInfo {
  /** trader = action_plan.overall_stance；ai = combined 报告的 verdict */
  source: 'trader' | 'ai'
  value: string
  as_of: string
}

export interface ReportTimes {
  combined?: string | null
  anti_quant?: string | null
  reflexivity?: string | null
  mean_reversion?: string | null
  action_plan?: string | null
}

export interface SignalItem {
  code: string
  name: string
  market: string
  pinned?: boolean
  group_ids?: number[]
  group_names?: string[]
  note?: string | null
  as_of_date?: string
  close?: number
  pct_chg?: number
  signals: Signal[]
  top_signal: Signal | null
  empty?: boolean
  position?: PositionSummary | null
  stance?: StanceInfo | null
  ai_verdict?: string | null
  report_times?: ReportTimes
}

export async function getTodaySignals(params: { direction?: string; category?: string; group_id?: number } = {}) {
  const { data } = await api.get<{ count: number; items: SignalItem[] }>('/signals/today', { params })
  return data
}
