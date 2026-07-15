import { Space, Tag } from 'antd'
import { useStockAnalysis } from '@/features/stock-context'
import { priceColor } from '@/shared/theme'
import { ClosedBadge } from '@/features/status-bar/ClosedBadge'

const arrangementLabel: Record<string, { label: string; color: string }> = {
  bullish: { label: '多头排列', color: 'red' },
  bearish: { label: '空头排列', color: 'green' },
  tangled: { label: '均线纠缠', color: 'gold' },
  insufficient: { label: '数据不足', color: 'default' },
}

const crossLabel: Record<string, { label: string; color: string }> = {
  golden: { label: '金叉', color: 'red' },
  death: { label: '死叉', color: 'green' },
}

const kdjLabel: Record<string, { label: string; color: string }> = {
  overbought: { label: '超买', color: 'orange' },
  oversold: { label: '超卖', color: 'blue' },
  neutral: { label: '中性', color: 'default' },
}

const volumeLabel: Record<string, { label: string; color: string }> = {
  big_volume_up: { label: '放量上涨', color: 'red' },
  big_volume_down: { label: '放量下跌', color: 'green' },
  big_volume_flat: { label: '放量滞涨', color: 'orange' },
  shrink_volume: { label: '缩量整理', color: 'blue' },
  normal: { label: '量能正常', color: 'default' },
}

const bollPosLabel: Record<string, { label: string; color: string }> = {
  above_upper: { label: '突破上轨', color: 'red' },
  below_lower: { label: '跌破下轨', color: 'green' },
  above_middle: { label: '中轨之上', color: 'gold' },
  below_middle: { label: '中轨之下', color: 'blue' },
}

const fmt = (v: unknown, d = 2) =>
  typeof v === 'number' && !Number.isNaN(v) ? v.toFixed(d) : '-'

function TagFor({
  dict,
  value,
}: {
  dict: Record<string, { label: string; color: string }>
  value?: string
}) {
  if (!value) return null
  const t = dict[value]
  if (!t) return null
  return <Tag color={t.color}>{t.label}</Tag>
}

/**
 * 关键指标横排胶囊：收盘 · 涨跌幅 · 均线排列 · 量能形态 · MACD 交叉 · KDJ 信号 · BOLL · 20日相对涨幅 · 量比。
 * K 线上方、AI 分析卡片内均可复用，从当前股票的 useStockAnalysis 拉数据。
 */
export function KeyMetricsStrip({ size = 'default' }: { size?: 'small' | 'default' } = {}) {
  const { data } = useStockAnalysis()
  if (!data || data.empty) return null
  const ind = (data as any).indicators || {}
  const ma = ind.ma || {}
  const osc = ind.oscillators || {}
  const vol = ind.volume || {}
  const rs = ind.rs || {}
  const price = ind.latest_price || {}
  const finalized = ind.finalized as boolean | undefined
  const pctCol = (price.pct_chg ?? 0) >= 0 ? priceColor.up : priceColor.down

  const fontSize = size === 'small' ? 12 : 13
  const padding = size === 'small' ? '2px 8px' : '3px 10px'

  return (
    <Space wrap size={[6, 6]}>
      <ClosedBadge finalized={finalized} size={size} />
      <Tag style={{ fontSize, padding }}>
        收盘 <strong>{fmt(price.close)}</strong>
      </Tag>
      <Tag style={{ fontSize, padding, color: pctCol, borderColor: pctCol }}>
        {(price.pct_chg ?? 0) >= 0 ? '+' : ''}
        {fmt(price.pct_chg)}%
      </Tag>
      {typeof vol.vol_ratio === 'number' && (
        <Tag style={{ fontSize, padding }}>量比 {vol.vol_ratio}</Tag>
      )}
      <TagFor dict={arrangementLabel} value={ma.arrangement} />
      <TagFor dict={volumeLabel} value={vol.volume_pattern} />
      {osc.macd?.cross && (
        <Tag color={crossLabel[osc.macd.cross]?.color} style={{ fontSize, padding }}>
          MACD {crossLabel[osc.macd.cross]?.label}
        </Tag>
      )}
      {osc.kdj?.signal && osc.kdj.signal !== 'neutral' && (
        <TagFor dict={kdjLabel} value={osc.kdj.signal} />
      )}
      <TagFor dict={bollPosLabel} value={osc.boll?.position} />
      {typeof rs.pct_20d === 'number' && (
        <Tag style={{ fontSize, padding }}>
          20 日 {rs.pct_20d >= 0 ? '+' : ''}
          {rs.pct_20d}%
        </Tag>
      )}
    </Space>
  )
}
