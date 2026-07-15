/**
 * 全站主题/色彩配置。
 * 所有涉及"偏多/偏空/中性/谨慎"和"信号方向"的地方都从这里取。
 */

export type Direction = 'bullish' | 'bearish' | 'neutral'
export type Verdict = Direction | 'caution'

export interface Palette {
  label: string
  color: string
  bg: string
  border: string
}

export const verdictPalette: Record<Verdict, Palette> = {
  bullish: { label: '偏多', color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
  bearish: { label: '偏空', color: '#059669', bg: '#ecfdf5', border: '#a7f3d0' },
  neutral: { label: '中性', color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  caution: { label: '谨慎', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
}

export const directionEmoji: Record<Direction, string> = {
  bullish: '↗',
  bearish: '↘',
  neutral: '→',
}

/** 涨/跌颜色（K 线、涨跌幅数字） */
export const priceColor = {
  up: '#ef4444',
  down: '#10b981',
}

/** 强调色 */
export const accent = {
  pin: '#f59e0b',       // 置顶
  active: '#2563eb',    // 当前选中
  mute: '#94a3b8',      // 次要
}
