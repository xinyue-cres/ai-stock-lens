import { api } from './client'

export type TrendStage =
  | 'strong_uptrend'
  | 'pullback_entry'
  | 'overheat'
  | 'downtrend'
  | 'range'
  | 'insufficient'

export interface ScoreItem {
  code: string
  name: string
  is_fund: boolean
  scan_date: string
  as_of_date: string | null
  total_score: number
  signal_score: number
  band_score: number
  dividend_score: number
  close: number | null
  pct_chg: number | null
  turnover: number | null
  hist_vol: number | null
  adx: number | null
  dividend_yield: number | null
  trend_stage: TrendStage | null
  can_entry: boolean | null
  entry_reason: string | null
  // MACD DIF 当前斜率 + 状态（列表行展示参考，不参与评分）
  dif_slope: number | null
  dif_slope_dir: 'up' | 'down' | 'flat' | null
  current_state: string | null
}

// 各维度明细（components_json 解析后的结构，字段可能缺省）
export interface SignalComponent {
  post_golden_gain?: number | null
  whipsaw_score?: number | null
  adx?: number | null
  signal_count?: number | null
  current_golden?: boolean | null
  current_state?: string | null
  dif_slope?: number | null
  dif_slope_dir?: 'up' | 'down' | 'flat' | null
  peak_signal?: '上涨过峰' | '下跌过峰' | '涨势延续' | '跌势延续' | null
  // 信号汇总（趋势判断卡展示用）
  current_signal?: 'golden' | 'death' | null
  signal_days?: number | null
  signal_gain_pct?: number | null
  hist_golden_days?: number | null
  hist_golden_samples?: number | null
  hist_golden_peak_pct?: number | null
  hist_golden_peak_median?: number | null
  hist_golden_peak_winrate?: number | null
  hist_death_samples?: number | null
  hist_death_trough_pct?: number | null
  hist_death_trough_median?: number | null
  hist_death_trough_winrate?: number | null
}

export interface BandComponent {
  amplitude_score?: number | null
  rhythm_score?: number | null
  sigma_20d?: number | null
  ma5_stay_days?: number | null
}

export interface DividendComponent {
  dividend_yield?: number | null
}

export interface TrendComponent {
  key_prices?: Record<string, number | null>
  indicators?: Record<string, number | string | null>
}

export interface ScoreComponents {
  signal?: SignalComponent
  band?: BandComponent
  dividend?: DividendComponent
  trend?: TrendComponent
}

export interface ScoreDetail extends ScoreItem {
  components: ScoreComponents
}

export interface ScanStatus {
  running: boolean
  scope: string | null
  total: number
  done: number
  failed: number
  current: string | null
  started_at: string | null
  finished_at: string | null
  cancel_requested: boolean
}

export interface ScoreListParams {
  sort_by?: string
  dir?: 'desc' | 'asc'
  limit?: number
  min_score?: number
  can_entry?: boolean
  stage?: string
  group_ids?: string // 逗号分隔的自选分组 id，如 "9,10"
  scope?: string // all/watchlist/group，决定取哪个范围的最近扫描批次
}

export async function getScoreList(params: ScoreListParams = {}): Promise<ScoreItem[]> {
  const { data } = await api.get('/score/list', { params })
  return data
}

export async function getScoreDetail(code: string): Promise<ScoreDetail> {
  const { data } = await api.get(`/score/${code}`)
  return data
}

export async function runScan(body: {
  scope: string
  codes?: string[]
  force?: boolean
  group_id?: number
  group_ids?: number[]
}) {
  const { data } = await api.post('/score/scan', body, { timeout: 30_000 })
  return data
}

export async function cancelScan() {
  const { data } = await api.post('/score/scan/cancel')
  return data
}

export async function getScanStatus(): Promise<ScanStatus> {
  const { data } = await api.get('/score/scan/status')
  return data
}

export interface TrendResult {
  code: string
  trend_stage: TrendStage
  can_entry: boolean
  entry_reason: string
  key_prices: Record<string, number | null>
  indicators: Record<string, number | string | null>
}

export async function judgeTrend(code: string): Promise<TrendResult> {
  const { data } = await api.post(`/score/trend/${code}`, {}, { timeout: 30_000 })
  return data
}

export interface ScoreSummary {
  scope: string
  count: number
  summary: string
  highlights: string[]
  watch: { code: string; name: string; reason: string }[]
  risk_note: string
  report_md: string
}

export async function summarizeScore(body: {
  scope?: string
  group_ids?: string
  sort_by?: string
  dir?: 'desc' | 'asc'
  limit?: number
  can_entry?: boolean
}): Promise<ScoreSummary> {
  // AI 调用可能较慢，单独放宽超时（AI 端 55s）
  const { data } = await api.post('/score/summarize', body, { timeout: 65_000 })
  return data
}

export interface StockComment extends ScoreItem {
  verdict: string
  score_comment?: string
  summary?: string
  key_point?: string
}

export async function analyzeBatchScore(body: {
  scope?: string
  group_ids?: string
  sort_by?: string
  dir?: 'desc' | 'asc'
  limit?: number
  can_entry?: boolean
}): Promise<{ count: number; items: StockComment[] }> {
  // 逐只并发调用 AI，可能较慢，单独放宽超时
  const { data } = await api.post('/score/analyze-batch', body, { timeout: 65_000 })
  return data
}
