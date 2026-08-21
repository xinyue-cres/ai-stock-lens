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
  icon: string
  action?: string
}

export const COMBINED_PALETTE: Record<CombinedStage, CombinedStagePalette> = {
  strong_buy:          { label: '强买信号', color: '#dc2626', bg: '#fef2f2', border: '#fecaca', icon: '🐂', action: '重仓买入' },
  buy:                 { label: '买入',     color: '#ea580c', bg: '#fff7ed', border: '#fed7aa', icon: '📈', action: '可买入' },
  watch_buy:           { label: '观察买',   color: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: '👀', action: '加自选盯日线' },
  deep_pullback_entry: { label: '深度回踩', color: '#65a30d', bg: '#f7fee7', border: '#d9f99d', icon: '🎯', action: '轻仓分批' },
  light_buy:           { label: '轻仓试',   color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', icon: '💡', action: '轻仓试仓' },
  watch:               { label: '观望',     color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb', icon: '⏸️', action: '不动' },
  avoid:               { label: '回避',     color: '#4b5563', bg: '#f3f4f6', border: '#d1d5db', icon: '🚫', action: '回避' },
}
