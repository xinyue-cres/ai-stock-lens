import { api } from './client'

export interface ScenarioCondition {
  kind: 'price' | 'volume_ratio'
  op: '>=' | '<='
  value: number
  target?: 'close' | 'high' | 'low'
}

export interface Scenario {
  trigger: string
  action: string
  direction: 'bullish' | 'bearish' | 'neutral'
  probability?: number | null
  conditions?: ScenarioCondition[]
}

export interface DebaterView {
  stance: 'bullish' | 'bearish'
  confidence?: number
  thesis?: string
  arguments?: (string | { claim: string; failure_mode?: string })[]
  concessions?: string[]
  invalidation?: string
}

export interface JudgeView {
  verdict: 'bullish' | 'bearish' | 'neutral' | 'caution'
  confidence?: number
  who_wins?: 'bull' | 'bear' | 'draw'
  consensus?: string[]
  disputes?: string[]
  verdict_reasoning?: string
}

export interface QuantFlow {
  type: string
  trigger?: string
  probability?: number
  size_hint?: string
  expected_horizon_days?: number
}

export interface QuantOutput {
  quant_flows?: QuantFlow[]
  positioning_bias?: string
  crowding_level?: 'low' | 'medium' | 'high' | 'extreme'
  dominant_quant_style?: 'trend_following' | 'mean_reversion' | 'intraday_liquidity' | 'mixed'
  crowded_trade?: {
    direction: 'long' | 'short' | 'neutral'
    logic: string
    failure_trigger: string
    unwind_risk: 'low' | 'medium' | 'high'
  }
  factor_conflicts?: { conflict: string; impact: string }[]
  next_5d_pressure?: string
  key_factors?: string[]
  reasoning?: string
}

export interface FeedbackLoop {
  direction?: 'positive' | 'negative'
  strength?: 'accelerating' | 'stable' | 'weakening' | 'reversing'
  key_evidence?: string[]
}

export type ReflexivityStage =
  | 'self_reinforcing_up'
  | 'peak_exhaustion'
  | 'reversal_top'
  | 'self_reinforcing_down'
  | 'capitulation'
  | 'reversal_bottom'
  | 'range_bound'

export type Tradability = 'worth_entry' | 'wait_better_rr' | 'no_clear_edge'

export interface EvidenceReview {
  side: 'bull' | 'bear'
  claim: string
  rating: 'strong' | 'medium' | 'weak'
  reason: string
}

export interface TrapRisk {
  type: 'false_breakout' | 'crowded_chase' | 'stop_loss_cascade' | 'none'
  level: 'low' | 'medium' | 'high'
  evidence: string[]
}

export interface RetailTrapRisk {
  type: 'chasing_top' | 'panic_selling' | 'none'
  probability: number
  evidence: string[]
  warning: string
}

export interface AiReport {
  cached: boolean
  code: string
  name?: string | null
  horizon: 'combined' | 'anti_quant' | 'reflexivity' | 'mean_reversion'
  verdict: 'bullish' | 'bearish' | 'neutral' | 'caution'
  confidence?: number | null
  summary?: string | null
  report_md?: string | null
  as_of_date?: string
  created_at?: string
  model?: string
  key_signals?: string[]
  risks?: string[]
  scenarios?: Scenario[]
  bull?: DebaterView | null
  bear?: DebaterView | null
  judge?: JudgeView | null
  reflection?: string | null
  quant_output?: QuantOutput | null
  trap_risk?: TrapRisk | null
  tradability?: Tradability | null
  evidence_review?: EvidenceReview[] | null
  reflexivity_stage?: ReflexivityStage | null
  narrative?: string | null
  feedback_loop?: FeedbackLoop | null
  retail_trap_risk?: RetailTrapRisk | null
}

export interface AiReportOptions {
  horizon?: 'combined' | 'anti_quant' | 'reflexivity' | 'mean_reversion'
  force?: boolean
}

export async function generateAiReport(code: string, opts: AiReportOptions = {}): Promise<AiReport> {
  const { data } = await api.post(`/stocks/${code}/ai-report`, {
    horizon: opts.horizon ?? 'combined',
    force: opts.force ?? false,
  })
  return data
}

export interface GenerateAllResult {
  code: string
  generated: string[]
  failed: Record<string, string>
  reports: Record<string, AiReport>
}

export async function generateAllAiReports(code: string, force = false): Promise<GenerateAllResult> {
  const { data } = await api.post(`/stocks/${code}/ai-report/all`, { force })
  return data
}

export interface CachedAiReport extends Partial<AiReport> {
  empty?: boolean
  cached?: boolean
  horizon?: 'combined' | 'anti_quant' | 'reflexivity' | 'mean_reversion'
}

export async function getCachedAiReport(
  code: string,
  horizon: 'combined' | 'anti_quant' | 'reflexivity' | 'mean_reversion' = 'combined',
): Promise<CachedAiReport> {
  const { data } = await api.get(`/stocks/${code}/ai-report`, {
    params: { horizon },
  })
  return data
}
