import type { TrendStage } from '@/api/score'

// 选股标准说明（顶栏"选股标准?"弹窗用）
export interface ScoreCriterion {
  key: string
  label: string
  weight: string
  desc: string
}

export const SCORE_CRITERIA: ScoreCriterion[] = [
  {
    key: 'signal',
    label: '金叉延续性',
    weight: '70%',
    desc: '出现金叉（日线 MACD 的 DIF 上穿 DEA）后，能否成功上涨一大段、不反复横跳。看历史每次金叉周期内的峰值涨幅（到周期最高点，均值/中位/胜率，评分锚点 24%）+ 金叉寿命（反复横跳检测）+ ADX 趋势强度 + 当前金叉/死叉态。分高 = 金叉可信、涨得动、不反复。',
  },
  {
    key: 'band',
    label: '波段适配',
    weight: '20%',
    desc: '波段适配 = 幅度×节奏：20 日波动率适中最佳（太小没肉、太大风险高）+ MA5 下方停留节奏（越从容越好，快探快弹=赌博）。分高 = 波动有肉且节奏可操作。',
  },
  {
    key: 'dividend',
    label: '股息',
    weight: '10%',
    desc: '近 3 年平均股息率。ETF/LOF 无股息数据，给中性 50 分。',
  },
]

export interface StagePalette {
  label: string
  color: string
  bg: string
  border: string
}

export const STAGE_PALETTE: Record<TrendStage, StagePalette> = {
  pullback_entry: { label: '可入手', color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
  left_entry: { label: '左侧·轻仓', color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe' },
  strong_uptrend: { label: '上升趋势', color: '#b91c1c', bg: '#fff7ed', border: '#fed7aa' },
  overheat: { label: '过热', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  weak_golden: { label: '弱势金叉', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  range: { label: '震荡', color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  downtrend: { label: '下跌趋势', color: '#059669', bg: '#ecfdf5', border: '#a7f3d0' },
  insufficient: { label: '数据不足', color: '#6b7280', bg: '#f3f4f6', border: '#e5e7eb' },
}

import type { CombinedStage } from '@/api/score'

export interface CombinedStagePalette extends StagePalette {
  action?: string
}

// 12 档综合状态（v1.4.0 对称化，docs/state-machine-redesign.md）：
// 买侧 5 + hold（中央）+ 卖侧 5 + avoid（场外）。与后端 combined_judge._STAGE_META 同步。
export const COMBINED_PALETTE: Record<CombinedStage, CombinedStagePalette> = {
  strong_buy:          { label: '强买信号', color: '#dc2626', bg: '#fef2f2', border: '#fecaca', action: '重仓买入' },
  buy:                 { label: '买入',     color: '#ea580c', bg: '#fff7ed', border: '#fed7aa', action: '可买入' },
  deep_pullback_entry: { label: '深度回踩', color: '#65a30d', bg: '#f7fee7', border: '#d9f99d', action: '轻仓分批' },
  watch_buy:           { label: '观察买',   color: '#d97706', bg: '#fffbeb', border: '#fde68a', action: '先盯' },
  light_buy:           { label: '轻仓试',   color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', action: '轻仓' },
  hold:                { label: '持有',     color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb', action: '不动' },
  watch_sell:          { label: '观察卖',   color: '#d97706', bg: '#fffbeb', border: '#fde68a', action: '先盯' },
  light_sell:          { label: '轻仓减',   color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', action: '减仓' },
  deep_rally_exit:     { label: '反弹离场', color: '#65a30d', bg: '#f7fee7', border: '#d9f99d', action: '分批减仓' },
  sell:                { label: '卖出',     color: '#ea580c', bg: '#fff7ed', border: '#fed7aa', action: '中大仓减' },
  strong_sell:         { label: '强卖信号', color: '#dc2626', bg: '#fef2f2', border: '#fecaca', action: '清仓' },
  avoid:               { label: '场外回避', color: '#4b5563', bg: '#f3f4f6', border: '#d1d5db', action: '不介入' },
}

// 买侧 / 卖侧聚合（前端侧过滤用）
export const BUY_SIDE_STAGES: CombinedStage[] = [
  'strong_buy', 'buy', 'watch_buy', 'deep_pullback_entry', 'light_buy',
]
export const SELL_SIDE_STAGES: CombinedStage[] = [
  'watch_sell', 'light_sell', 'deep_rally_exit', 'sell', 'strong_sell',
]

// 卖侧镜像顺序：从强到轻排，与买侧 BUY_SIDE_STAGES 逐档对应
// （强卖↔强买、卖出↔买入、观察卖↔观察买、反弹离场↔深度回踩、轻仓减↔轻仓试）
export const SELL_MIRROR_ORDER: CombinedStage[] = [
  'strong_sell', 'sell', 'watch_sell', 'deep_rally_exit', 'light_sell',
]

// 各档信号含义（综合视图问号提示用；与后端 combined_judge._STAGE_META 的 reason 对齐）
export const STAGE_MEANING: Record<CombinedStage, string> = {
  strong_buy: '日周线同向看多共振，重仓买入',
  buy: '周线看好 + 日线已反弹，可买入',
  watch_buy: '周看多但日线整理，等升级',
  deep_pullback_entry: '周趋势内日超跌，轻仓分批',
  light_buy: '周中性 + 日线有起涨信号，轻仓试',
  hold: '可交易但无明确方向，不动',
  watch_sell: '周定调偏坏，日线未确认走坏，先盯',
  light_sell: '周走弱但日线未确认，先减仓',
  deep_rally_exit: '周已走坏，日线反弹是离场窗口',
  sell: '日周均走坏，尽快出清',
  strong_sell: '双周共振走弱，清仓',
  avoid: '系统不评估（数据不足/双周假弱），不介入',
}
