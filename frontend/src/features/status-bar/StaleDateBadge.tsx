import { Space, Tooltip, Typography } from 'antd'
import { CalendarOutlined } from '@ant-design/icons'

const { Text } = Typography

interface Props {
  asOf: string | null | undefined
  size?: 'small' | 'default'
}

/**
 * 数据日期标签：显示"截至 YYYY-MM-DD · 状态"。
 * - 与当日最近应有的交易日对齐 → 绿色"最新"
 * - 滞后 1 交易日 → 琥珀色
 * - 滞后 2+ → 红色
 */
export function StaleDateBadge({ asOf, size = 'default' }: Props) {
  if (!asOf) return null
  const s = computeStaleness(asOf)
  const fontSize = size === 'small' ? 12 : 13

  return (
    <Tooltip title={s.tooltip}>
      <Space size={4} style={{ lineHeight: 1 }}>
        <CalendarOutlined style={{ color: s.color, fontSize }} />
        <Text style={{ color: s.color, fontSize }}>
          截至 {asOf}
          {s.suffix && ` · ${s.suffix}`}
        </Text>
      </Space>
    </Tooltip>
  )
}

export function computeStaleness(asOf: string): {
  color: string
  suffix: string | null
  tooltip: string
} {
  const today = new Date()
  const isTradingDayOver = today.getHours() >= 15
  const expected = latestExpectedTradingDate(today, isTradingDayOver)
  const asOfDate = new Date(asOf + 'T00:00:00')
  const diffDays = Math.max(0, tradingDayDiff(asOfDate, expected))

  if (diffDays === 0) {
    return { color: '#059669', suffix: '最新', tooltip: `数据即最新交易日 ${asOf}` }
  }
  if (diffDays === 1) {
    return {
      color: '#d97706',
      suffix: '滞后 1 交易日',
      tooltip: `预期最新 ${expected.toISOString().slice(0, 10)}，当前 ${asOf} — 点顶栏"立即同步"`,
    }
  }
  return {
    color: '#dc2626',
    suffix: `滞后 ${diffDays} 交易日`,
    tooltip: `数据陈旧，建议立即同步`,
  }
}

function latestExpectedTradingDate(now: Date, isTodayOver: boolean): Date {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  if (!isTodayOver) d.setDate(d.getDate() - 1)
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1)
  return d
}

function tradingDayDiff(from: Date, to: Date): number {
  if (from >= to) return 0
  let count = 0
  const cur = new Date(from)
  while (cur < to) {
    cur.setDate(cur.getDate() + 1)
    if (cur.getDay() !== 0 && cur.getDay() !== 6) count++
  }
  return count
}
