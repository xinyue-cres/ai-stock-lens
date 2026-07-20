import { Typography } from 'antd'
import { priceColor } from '@/shared/theme'
import { SignalItem } from '@/api/signals'
import { actionableStances } from '../constants'

const { Text } = Typography

interface MarketIndex {
  code: string
  name: string
  pct_1d: number | null
}

interface MarketData {
  indices: MarketIndex[]
}

interface SummaryBarProps {
  items: SignalItem[]
  market: MarketData | undefined
}

export default function SummaryBar({ items, market }: SummaryBarProps) {
  let up = 0, down = 0, flat = 0
  let posTotal = 0, posCount = 0
  let attention = 0
  for (const item of items) {
    if (item.empty) continue
    const pct = item.pct_chg ?? 0
    if (pct > 0.1) up++
    else if (pct < -0.1) down++
    else flat++
    if (item.position?.unrealized_pnl_pct != null) {
      posTotal += item.position.unrealized_pnl_pct
      posCount++
    }
    if (item.stance && actionableStances.has(item.stance.value)) attention++
  }

  return (
    <div style={{ display: 'flex', gap: 24, marginBottom: 16, padding: '12px 16px', background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0' }}>
      <SummaryCard
        label="涨跌分布"
        content={
          <span style={{ fontSize: 15, fontWeight: 600 }}>
            <span style={{ color: priceColor.up }}>{up}↑</span>
            {' '}<span style={{ color: '#9ca3af' }}>{flat}→</span>
            {' '}<span style={{ color: priceColor.down }}>{down}↓</span>
          </span>
        }
      />
      <SummaryCard
        label="持仓盈亏"
        content={
          posCount > 0 ? (
            <span style={{ fontSize: 15, fontWeight: 600, color: posTotal >= 0 ? priceColor.up : priceColor.down }}>
              {posTotal >= 0 ? '+' : ''}{(posTotal * 100 / posCount).toFixed(1)}% 均
            </span>
          ) : <span style={{ color: '#9ca3af' }}>无持仓</span>
        }
      />
      <SummaryCard
        label="需关注"
        content={
          <span style={{ fontSize: 15, fontWeight: 600, color: attention > 0 ? '#dc2626' : '#9ca3af' }}>
            {attention} 只
          </span>
        }
      />
      {market && (
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 16, alignItems: 'center' }}>
          {market.indices.map(idx => (
            <span key={idx.code} style={{ fontSize: 12 }}>
              <span style={{ color: '#6b7280' }}>{idx.name.replace('指数', '')}</span>
              {' '}
              <span style={{ fontWeight: 600, color: (idx.pct_1d ?? 0) >= 0 ? priceColor.up : priceColor.down }}>
                {(idx.pct_1d ?? 0) >= 0 ? '+' : ''}{(idx.pct_1d ?? 0).toFixed(2)}%
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryCard({ label, content }: { label: string; content: React.ReactNode }) {
  return (
    <div>
      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 2 }}>{label}</Text>
      {content}
    </div>
  )
}
