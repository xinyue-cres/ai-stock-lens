import { api } from './client'

export interface DiaryReviewItem {
  review_date: string
  days_after: number
  verdict_hit: 'hit' | 'miss' | 'pending' | 'n/a' | null
  price_change_pct: number | null
  triggered_count: number
  total_scenarios: number
  scenarios: DiaryScenarioEval[]
  notes?: string | null
}

export interface DiaryScenarioEval {
  index: number
  direction: 'bullish' | 'bearish' | 'neutral' | null
  trigger: string | null
  triggered: boolean | null
  condition_results: Array<{
    kind: 'price' | 'volume_ratio'
    op: '>=' | '<='
    value: number
    target?: 'close' | 'high' | 'low' | null
    actual: number | null
    ok: boolean
  }>
}

export interface DiaryReportEntry {
  report_id: number
  code: string
  as_of_date: string
  created_at?: string | null
  horizon: 'short' | 'medium' | 'combined'
  verdict: 'bullish' | 'bearish' | 'neutral' | 'caution'
  confidence: number | null
  summary: string | null
  reflection?: string | null
  scenarios: Array<{
    trigger?: string
    action?: string
    direction?: 'bullish' | 'bearish' | 'neutral'
    probability?: number | null
    conditions?: Array<{ kind: string; op: string; value: number; target?: string | null }>
  }>
  latest_verdict_hit: 'hit' | 'miss' | 'pending' | 'n/a' | null
  latest_pct: number | null
  reviews: DiaryReviewItem[]
}

export async function getDiary(code: string): Promise<DiaryReportEntry[]> {
  const { data } = await api.get<DiaryReportEntry[]>(`/stocks/${code}/diary`)
  return data
}

export async function refreshDiary(code: string): Promise<{ code: string; reports: number; new_reviews: number }> {
  const { data } = await api.post(`/stocks/${code}/diary/refresh`)
  return data
}
