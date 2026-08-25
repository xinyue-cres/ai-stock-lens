/** 持仓汇总统计卡：只数/总市值/总成本/累计浮盈/浮盈占比/今日浮盈/仓位占比。 */
import { Card, Space, Statistic } from 'antd'
import { priceColor } from '@/shared/theme'
import type { Aggregate } from '../utils/aggregate'

interface SummaryCardsProps {
  summary: Aggregate
  currentCapital: number | null
}

export function SummaryCards({ summary, currentCapital }: SummaryCardsProps) {
  return (
    <Card>
      <Space size={40} wrap>
        <Statistic title="持仓只数" value={summary.count} />
        <Statistic title="总市值" value={summary.marketValue ?? '-'} precision={2} prefix="¥" />
        <Statistic title="总成本" value={summary.totalCost ?? '-'} precision={2} prefix="¥" />
        <Statistic
          title="累计浮盈"
          value={summary.totalPnl ?? '-'}
          precision={2}
          prefix="¥"
          valueStyle={{ color: (summary.totalPnl ?? 0) >= 0 ? priceColor.up : priceColor.down }}
        />
        <Statistic
          title="浮盈占比"
          value={summary.pnlPct != null ? summary.pnlPct * 100 : '-'}
          precision={2}
          suffix="%"
          valueStyle={{ color: (summary.pnlPct ?? 0) >= 0 ? priceColor.up : priceColor.down }}
        />
        <Statistic
          title="今日浮盈"
          value={summary.todayPnl ?? '-'}
          precision={2}
          prefix="¥"
          valueStyle={{ color: (summary.todayPnl ?? 0) >= 0 ? priceColor.up : priceColor.down }}
        />
        {currentCapital && summary.marketValue != null && (
          <Statistic
            title="仓位占比"
            value={(summary.marketValue / currentCapital) * 100}
            precision={1}
            suffix="%"
          />
        )}
      </Space>
    </Card>
  )
}
