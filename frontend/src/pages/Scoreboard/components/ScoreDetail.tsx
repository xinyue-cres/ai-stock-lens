import type { ReactNode } from 'react'
import { Button, Card, Descriptions, Empty, Space, Tag, Typography } from 'antd'
import { LineChartOutlined, PlusOutlined } from '@ant-design/icons'
import type { ScoreDetail } from '@/api/score'
import { STAGE_PALETTE } from '../constants'

const { Text } = Typography

/** 均线结构英文值 → 中文 */
const ARRANGEMENT_LABEL: Record<string, string> = {
  bullish: '多头排列',
  bearish: '空头排列',
  tangled: '均线纠缠（方向不明）',
  insufficient: '数据不足',
}

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
            {/* 当前查看周期标识：daily 绿 / weekly 蓝，避免日/周数据混看 */}
            <Tag
              style={{
                marginLeft: 6,
                color: detail.timeframe === 'weekly' ? '#1d4ed8' : '#15803d',
                borderColor: detail.timeframe === 'weekly' ? '#bfdbfe' : '#bbf7d0',
                background: detail.timeframe === 'weekly' ? '#eff6ff' : '#f0fdf4',
              }}
            >
              {detail.timeframe === 'weekly' ? '当前：周线' : '当前：日线'}
            </Tag>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {stage && <Tag style={{ color: stage.color, borderColor: stage.border, background: stage.bg }}>{stage.label}</Tag>}
            {detail.trend_stage === 'left_entry' && (
              <Tag style={{ color: '#7c3aed', borderColor: '#ddd6fe', background: '#f5f3ff' }}>高风险·轻仓</Tag>
            )}
            <Button size="small" icon={<LineChartOutlined />} onClick={() => onOpenDetail(detail.code)}>
              完整详情
            </Button>
            <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => onAddWatchlist(detail.code)}>
              加入自选
            </Button>
          </div>
        </div>
        {detail.can_entry && detail.trend_stage === 'left_entry' && detail.entry_reason && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#7c3aed', background: '#f5f3ff', border: '1px solid #ddd6fe', borderRadius: 6, padding: '8px 10px' }}>
            ⚠ 左侧机会 · 高风险逆势，建议轻仓 · {detail.entry_reason}
          </div>
        )}
        {detail.can_entry && detail.trend_stage !== 'left_entry' && detail.entry_reason && (
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

      {/* 综合分 + 各维度（全部横向紧凑排：综合分大字 + 维度一行，指标快照一行） */}
      <Card size="small" title="打分构成">
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px 20px' }}>
          <span style={{ fontSize: 34, fontWeight: 700, lineHeight: 1, color: detail.total_score >= 70 ? '#16a34a' : detail.total_score >= 50 ? '#2563eb' : '#9ca3af' }}>
            {detail.total_score.toFixed(1)}
          </span>
          <Text type="secondary" style={{ fontSize: 11 }}>综合</Text>
          <Field label="金叉延续性 (70%)">{detail.signal_score.toFixed(1)}</Field>
          <Field label="波段适配 (20%)">{detail.band_score.toFixed(1)}</Field>
          <Field label="股息 (10%)">{detail.dividend_score.toFixed(1)}</Field>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', columnGap: 18, rowGap: 2, marginTop: 8 }}>
          <Field label="收盘">{detail.close ?? '-'}</Field>
          <Field label="涨跌幅">{pct(detail.pct_chg)}</Field>
          <Field label="换手率">{detail.turnover != null ? `${detail.turnover}%` : '-'}</Field>
          <Field label="年化波动率">{detail.hist_vol != null ? `${detail.hist_vol}%` : '-'}</Field>
          <Field label="ADX">{detail.adx ?? '-'}</Field>
          <Field label="股息率">{detail.dividend_yield != null ? `${detail.dividend_yield}%` : '-'}</Field>
        </div>
      </Card>

      {/* 趋势判断明细：金叉/死叉信号汇总（阶段/可入手在头部卡已展示，不重复） */}
      <Card size="small" title="趋势判断 · 信号汇总">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '2px 24px' }}>
          <Field label="当前信号">
            {sig.current_state ?? (sig.current_signal ? (sig.current_signal === 'golden' ? '金叉' : '死叉') : '-')}
          </Field>
          <Field label="过峰信号">
            {sig.peak_signal ? (
              <span style={{
                color:
                  sig.peak_signal === '上涨过峰' ? '#d97706' :
                  sig.peak_signal === '下跌过峰' ? '#2563eb' :
                  sig.peak_signal === '底部反转' ? '#16a34a' :
                  sig.peak_signal === '顶部回落' ? '#dc2626' :
                  undefined,
              }}>
                {sig.peak_signal}
                {sig.peak_conf ? `（置信度${sig.peak_conf}）` : ''}
              </span>
            ) : '-'}
          </Field>
          <Field label="信号持续">
            {sig.signal_days === 0
              ? (sig.current_signal === 'death' ? '今日死叉' : '今日金叉')
              : sig.signal_days != null ? `${sig.signal_days} 天` : '-'}
          </Field>
          <Field label="历史金叉持续">
            {sig.hist_golden_days != null ? (
              <span>
                均值 {sig.hist_golden_days} 天
                {sig.hist_golden_days_median != null ? ` · 中位 ${sig.hist_golden_days_median} 天` : ''}
              </span>
            ) : '-'}
          </Field>
          <Field label="信号期间涨跌">{sig.signal_gain_pct != null ? pct(sig.signal_gain_pct) : '-'}</Field>
          <Field label="当日涨跌">{pct(detail.pct_chg)}</Field>
          <Field label="历史金叉周期峰值涨幅">
            {sig.hist_golden_peak_pct != null ? (
              <span>
                均值 {pct(sig.hist_golden_peak_pct)}
                {sig.hist_golden_peak_median != null ? ` · 中位 ${pct(sig.hist_golden_peak_median)}` : ''}
                {sig.hist_golden_peak_winrate != null ? ` · 胜率 ${sig.hist_golden_peak_winrate}%` : ''}
                {sig.hist_golden_samples != null ? `（${sig.hist_golden_samples}次）` : ''}
              </span>
            ) : '-'}
          </Field>
          <Field label="历史死叉周期谷值跌幅">
            {sig.hist_death_trough_pct != null ? (
              <span>
                均值 {pct(sig.hist_death_trough_pct)}
                {sig.hist_death_trough_median != null ? ` · 中位 ${pct(sig.hist_death_trough_median)}` : ''}
                {sig.hist_death_trough_winrate != null ? ` · 胜率 ${sig.hist_death_trough_winrate}%` : ''}
                {sig.hist_death_samples != null ? `（${sig.hist_death_samples}次）` : ''}
              </span>
            ) : '-'}
          </Field>
          <Field label="DIF 斜率">
            {sig.dif_slope != null
              ? `${sig.dif_slope > 0 ? '+' : ''}${sig.dif_slope}${sig.dif_slope_dir === 'up' ? ' ↗' : sig.dif_slope_dir === 'down' ? ' ↘' : ''}`
              : '-'}
          </Field>
          <Field label="ADX">{sig.adx ?? trendInd.adx ?? '-'}</Field>
          <Field label="均线结构" full>
            {trendInd.arrangement ? ARRANGEMENT_LABEL[trendInd.arrangement] ?? trendInd.arrangement : '-'}
          </Field>
        </div>
        {detail.entry_reason && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280', background: '#f3f4f6', borderRadius: 6, padding: '8px 10px' }}>
            判断依据：{detail.entry_reason}
          </div>
        )}
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
