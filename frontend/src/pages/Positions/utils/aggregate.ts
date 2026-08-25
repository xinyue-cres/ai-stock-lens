/** 持仓聚合（纯函数，从 Positions/index.tsx 抽出）。 */
import type { PositionSummary } from '@/api/positions'

export interface Aggregate {
  count: number
  totalCost: number | null
  marketValue: number | null
  totalPnl: number | null
  pnlPct: number | null
  todayPnl: number | null
}

export function aggregate(list: PositionSummary[]): Aggregate {
  if (list.length === 0) {
    return {
      count: 0,
      totalCost: null,
      marketValue: null,
      totalPnl: null,
      pnlPct: null,
      todayPnl: null,
    }
  }
  let totalCost = 0
  let marketValue = 0
  let todayPnl = 0
  let hasMV = true
  let hasToday = true
  for (const p of list) {
    totalCost += p.quantity * p.cost_price
    if (p.market_value != null) marketValue += p.market_value
    else hasMV = false
    if (p.today_pnl != null) todayPnl += p.today_pnl
    else hasToday = false
  }
  const totalPnl = hasMV ? marketValue - totalCost : null
  const pnlPct = hasMV && totalCost > 0 ? totalPnl! / totalCost : null
  return {
    count: list.length,
    totalCost,
    marketValue: hasMV ? marketValue : null,
    totalPnl,
    pnlPct,
    todayPnl: hasToday ? todayPnl : null,
  }
}
