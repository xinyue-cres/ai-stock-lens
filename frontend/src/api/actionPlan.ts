import { api } from './client'
import type { ScenarioCondition } from './analysis'

export type ActionType =
  | 'buy_dip'
  | 'add_position'
  | 'trim_position'
  | 'take_profit'
  | 'stop_loss'
  | 'wait_breakout'
  | 'wait_pullback'
  | 'observe'

export type OverallStance =
  | 'opportunistic_buy'
  | 'wait'
  | 'trim'
  | 'hold'
  | 'reduce'
  | 'exit'

export type BiasType =
  | 'anchoring'
  | 'endowment'
  | 'disposition'
  | 'confirmation'
  | 'recency'
  | 'availability'
  | 'loss_aversion'
  | 'overconfidence'
  | 'herding'
  | 'sunk_cost'

export interface BiasCheck {
  bias: BiasType
  label: string
  command?: string
  invalidation?: string
  do_not?: string
  do_instead?: string
}

export interface TraderAction {
  priority: number
  type: ActionType
  trigger_desc: string
  trigger_conditions: ScenarioCondition[]
  size_hint: string
  stop_loss?: number | null
  target_price?: number | null
  distance_pct?: number | null
  rationale: string
  sourced_from: ('combined' | 'anti_quant' | 'reflexivity' | 'mean_reversion')[]
}

export interface ActionPlan {
  cached?: boolean
  empty?: boolean
  code?: string
  name?: string | null
  as_of_date?: string
  overall_stance?: OverallStance
  summary?: string
  actions?: TraderAction[]
  position_advice?: string | null
  conflicts?: string[]
  bias_checks?: BiasCheck[]
  created_at?: string
}

export async function getActionPlan(code: string): Promise<ActionPlan> {
  const { data } = await api.get(`/stocks/${code}/action-plan`)
  return data
}

export async function generateActionPlan(code: string, force = false): Promise<ActionPlan> {
  const { data } = await api.post(`/stocks/${code}/action-plan`, { force })
  return data
}

// ------- 依赖状态检查 -------

export interface ActionPlanKlineStatus {
  as_of: string | null
  finalized: boolean | null
  empty: boolean
}

export interface ActionPlanReportStatus {
  as_of: string
  verdict: string
  trading_days_behind: number
  stale: boolean
  created_at?: string
}

export interface ActionPlanDeps {
  empty?: boolean
  reason?: string
  kline: ActionPlanKlineStatus
  reports: Record<string, ActionPlanReportStatus | null>
  position_dirty?: boolean
  ready: boolean
  warnings: string[]
}

export async function getActionPlanDeps(code: string): Promise<ActionPlanDeps> {
  const { data } = await api.get(`/stocks/${code}/action-plan/deps`)
  return data
}
