export const stanceLabel: Record<string, { label: string; color: string }> = {
  opportunistic_buy: { label: '择机买入', color: 'red' },
  wait: { label: '等待', color: 'blue' },
  trim: { label: '逢高减', color: 'orange' },
  hold: { label: '持有', color: 'cyan' },
  reduce: { label: '减仓', color: 'volcano' },
  exit: { label: '离场', color: 'red' },
}

export const actionableStances = new Set(['opportunistic_buy', 'trim', 'reduce', 'exit'])

export type SortKey = 'default' | 'pct_chg' | 'position' | 'confidence' | 'name'
export type SortDir = 'asc' | 'desc'

export const sortLabels: Record<SortKey, string> = {
  default: '默认',
  pct_chg: '涨跌幅',
  position: '持仓盈亏',
  confidence: 'AI 置信度',
  name: '名称',
}
