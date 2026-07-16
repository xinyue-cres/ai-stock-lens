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

export interface TriggeredScenario {
  horizon: string
  trigger: string
  direction: string
  triggered_date: string
}

export interface SignalItem {
  code: string
  name: string
  market: string
  pinned?: boolean
  as_of_date?: string
  close?: number
  pct_chg?: number
  signals: Signal[]
  top_signal: Signal | null
  empty?: boolean
  position?: PositionSummary | null
  stance?: StanceInfo | null
  ai_verdict?: string | null
  triggered_scenarios?: TriggeredScenario[]
}

export async function getTodaySignals(params: { direction?: string; category?: string } = {}) {
  const { data } = await api.get<{ count: number; items: SignalItem[] }>('/signals/today', { params })
  return data
}
