import type { ReactNode } from 'react'
import { Button, Card, Descriptions, Empty, Progress, Space, Tag, Typography } from 'antd'
import { LineChartOutlined, PlusOutlined } from '@ant-design/icons'
import type { ScoreDetail } from '@/api/score'
import { STAGE_PALETTE } from '../constants'

const { Text } = Typography

function pct(v: number | null | undefined): string {
  if (v == null) return '-'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

/** 「标签：值」紧凑行：值紧跟标签，天然对齐，不依赖列宽 */
function Field({ label, children, full }: { label: ReactNode; children: ReactNode; full?: boolean }) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'baseline',
        columnGap: 4,
        lineHeight: '22px',
        gridColumn: full ? '1 / -1' : undefined,
      }}
    >
      <span style={{ color: 'rgba(0, 0, 0, 0.45)', whiteSpace: 'nowrap' }}>{label}:</span>
      <span style={{ fontWeight: 500 }}>{children}</span>
    </div>
  )
}

interface ScoreDetailProps {
  detail: ScoreDetail
  onAddWatchlist: (code: string) => void
  onOpenDetail: (code: string) => void
}

function DimensionBar({ label, score }: { label: string; score: number }) {
  const color = score >= 70 ? '#16a34a' : score >= 50 ? '#2563eb' : '#f59e0b'
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
        <span>{label}</span>
        <b style={{ color }}>{score.toFixed(1)}</b>
      </div>
      <Progress percent={score} showInfo={false} strokeColor={color} size="small" />
    </div>
  )
}

export default function ScoreDetail({ detail, onAddWatchlist, onOpenDetail }: ScoreDetailProps) {
  const stage = detail.trend_stage ? STAGE_PALETTE[detail.trend_stage] : null
  const sig = detail.components?.signal ?? {}
  const band = detail.components?.band ?? {}
  const trend = detail.components?.trend ?? {}
  const trendInd = trend?.indicators ?? {}
  const keyPrices = trend?.key_prices ?? {}

  return (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      {/* 头部：名称 + 综合分 + 趋势 + 加自选 */}
      <Card size="small">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <span style={{ fontSize: 16, fontWeight: 700 }}>{detail.name || detail.code}</span>
            <Text type="secondary" style={{ marginLeft: 8 }}>{detail.code}</Text>
            {detail.is_fund && <Tag style={{ marginLeft: 6 }}>ETF/LOF</Tag>}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {stage && <Tag style={{ color: stage.color, borderColor: stage.border, background: stage.bg }}>{stage.label}</Tag>}
            <Button size="small" icon={<LineChartOutlined />} onClick={() => onOpenDetail(detail.code)}>
              完整详情
            </Button>
            <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => onAddWatchlist(detail.code)}>
              加入自选
            </Button>
          </div>
        </div>
        {detail.can_entry && detail.entry_reason && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#dc2626', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, padding: '8px 10px' }}>
            ✔ 可入手 · {detail.entry_reason}
          </div>
        )}
        {!detail.can_entry && detail.entry_reason && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280', background: '#f3f4f6', borderRadius: 6, padding: '8px 10px' }}>
            {detail.entry_reason}
          </div>
        )}
      </Card>

      {/* 综合分 + 各维度 */}
      <Card size="small" title="打分构成">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 34, fontWeight: 700, color: detail.total_score >= 70 ? '#16a34a' : detail.total_score >= 50 ? '#2563eb' : '#9ca3af' }}>
              {detail.total_score.toFixed(1)}
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>综合分</Text>
          </div>
          <div style={{ flex: 1 }}>
            <DimensionBar label="金叉延续性 (70%)" score={detail.signal_score} />
            <DimensionBar label="波段适配 (20%)" score={detail.band_score} />
            <DimensionBar label="股息 (10%)" score={detail.dividend_score} />
          </div>
        </div>

        <Descriptions column={2} size="small" title="指标快照">
          <Descriptions.Item label="收盘">{detail.close ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="涨跌幅">{pct(detail.pct_chg)}</Descriptions.Item>
          <Descriptions.Item label="换手率">{detail.turnover != null ? `${detail.turnover}%` : '-'}</Descriptions.Item>
          <Descriptions.Item label="年化波动率">{detail.hist_vol != null ? `${detail.hist_vol}%` : '-'}</Descriptions.Item>
          <Descriptions.Item label="ADX">{detail.adx ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="股息率">{detail.dividend_yield != null ? `${detail.dividend_yield}%` : '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 金叉延续性明细 */}
      <Card size="small" title="金叉延续性明细">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="金叉后涨幅/胜率分">{sig.post_golden_gain != null ? sig.post_golden_gain : '-'}</Descriptions.Item>
          <Descriptions.Item label="不横跳分">{sig.whipsaw_score != null ? sig.whipsaw_score : '-'}</Descriptions.Item>
          <Descriptions.Item label="历史信号次数">{sig.signal_count ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="当前状态">{sig.current_state ?? (sig.current_golden ? '金叉 (DIF>DEA)' : '死叉 (DIF<DEA)')}</Descriptions.Item>
          <Descriptions.Item label="DIF 斜率(当日−昨前均值)">{sig.dif_slope != null ? `${sig.dif_slope > 0 ? '+' : ''}${sig.dif_slope}` : '-'}</Descriptions.Item>
          <Descriptions.Item label="ADX">{sig.adx ?? '-'}</Descriptions.Item>
        </Descriptions>
        <Text type="secondary" style={{ fontSize: 11 }}>
          得分 = 0.60·金叉后涨幅（分开方放大区分度）+ 0.40·不横跳（MACD DIF/DEA 纯历史统计）；ADX / 斜率 / 状态仅供参考，不参与评分。
        </Text>
      </Card>

      {/* 波段适配明细 */}
      <Card size="small" title="波段适配明细">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="幅度分(波动适中)">
            {band.amplitude_score != null ? band.amplitude_score : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="节奏分(均线下方停留)">
            {band.rhythm_score != null ? band.rhythm_score : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="20日波动率">
            {band.sigma_20d != null ? `${band.sigma_20d}%` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="MA5下方平均停留">
            {band.ma5_stay_days != null ? `${band.ma5_stay_days}天` : '-'}
          </Descriptions.Item>
        </Descriptions>
        <Text type="secondary" style={{ fontSize: 11 }}>
          band = 0.60·幅度（波动适中最佳）+ 0.40·节奏（MA5下方停留越从容越好，太短=快探快弹赌博）。
        </Text>
      </Card>

      {/* 趋势判断明细：金叉/死叉信号汇总 */}
      <Card size="small" title="趋势判断 · 信号汇总">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '2px 24px' }}>
          <Field label="阶段">{stage?.label ?? '-'}</Field>
          <Field label="可入手">{detail.can_entry ? '是' : '否'}</Field>
          <Field label="当前信号">
            {sig.current_state ?? (sig.current_signal ? (sig.current_signal === 'golden' ? '金叉' : '死叉') : '-')}
          </Field>
          <Field label="信号持续">{sig.signal_days != null ? `${sig.signal_days} 天` : '-'}</Field>
          <Field label="信号期间涨跌">{sig.signal_gain_pct != null ? pct(sig.signal_gain_pct) : '-'}</Field>
          <Field label="当日涨跌">{pct(detail.pct_chg)}</Field>
          <Field label="历史金叉后20日均涨幅">
            {sig.hist_golden_avg_gain_pct != null ? pct(sig.hist_golden_avg_gain_pct) : '-'}
          </Field>
          <Field label="历史死叉后20日均涨跌">
            {sig.hist_death_avg_change_pct != null ? pct(sig.hist_death_avg_change_pct) : '-'}
          </Field>
          <Field label="DIF 斜率">
            {sig.dif_slope != null
              ? `${sig.dif_slope > 0 ? '+' : ''}${sig.dif_slope}${sig.dif_slope_dir === 'up' ? ' ↗' : sig.dif_slope_dir === 'down' ? ' ↘' : ''}`
              : '-'}
          </Field>
          <Field label="ADX">{sig.adx ?? trendInd.adx ?? '-'}</Field>
          <Field label="均线结构" full>{trendInd.arrangement ?? '-'}</Field>
        </div>
        {detail.entry_reason && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280', background: '#f3f4f6', borderRadius: 6, padding: '8px 10px' }}>
            判断依据：{detail.entry_reason}
          </div>
        )}
      </Card>

      {/* 趋势关键价位 */}
      <Card size="small" title="关键价位">
        <Descriptions column={3} size="small">
          <Descriptions.Item label="现价">{keyPrices.close ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="MA20">{keyPrices.ma20 ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="MA60">{keyPrices.ma60 ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="MA120">{keyPrices.ma120 ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="60日压力">{keyPrices.resistance_60d ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="止损参考">{keyPrices.stop_loss ?? '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      {Object.keys(detail.components ?? {}).length === 0 && (
        <Empty description="无指标明细（可能数据不完整）" />
      )}
    </Space>
  )
}
