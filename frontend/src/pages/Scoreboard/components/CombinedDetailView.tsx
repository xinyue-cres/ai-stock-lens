import { Button, Card, Empty, Space, Tag, Typography, Divider } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { CombinedItem } from '@/api/score'
import { COMBINED_PALETTE, STAGE_PALETTE } from '../constants'

const { Text, Paragraph } = Typography

/** 一腿（weekly / daily）的核心数据块 */
function LegBlock({ title, leg }: { title: '周线' | '日线'; leg: CombinedItem['weekly'] }) {
  const stage = leg.trend_stage ? STAGE_PALETTE[leg.trend_stage] : null
  return (
    <div style={{ padding: '10px 14px', background: '#fafafa', borderRadius: 6, marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text strong style={{ fontSize: 13 }}>{title}</Text>
        <span style={{ fontWeight: 700, fontSize: 16 }}>{leg.total_score?.toFixed(1) ?? '-'}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'rgba(0,0,0,0.65)', flexWrap: 'wrap' }}>
        {leg.signal_score != null && <span>signal {leg.signal_score.toFixed(0)}</span>}
        {stage && (
          <Tag style={{ fontSize: 11, color: stage.color, background: stage.bg, borderColor: stage.border }}>
            {stage.label}
          </Tag>
        )}
        {leg.peak_signal && (
          <Text type="secondary" style={{ fontSize: 11 }}>
            {leg.peak_signal}{leg.peak_conf ? `（置信度${leg.peak_conf}）` : ''}
          </Text>
        )}
      </div>
    </div>
  )
}

interface CombinedDetailViewProps {
  detail: CombinedItem
  onAddWatchlist: (code: string) => void
}

/** 综合详情视图：放在综合模式 master-detail 的右侧 */
export default function CombinedDetailView({ detail, onAddWatchlist }: CombinedDetailViewProps) {
  const palette = COMBINED_PALETTE[detail.combined_stage] ?? COMBINED_PALETTE.watch

  return (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      {/* 头部：名称 + 综合 stage + 加自选 */}
      <Card size="small">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <span style={{ fontSize: 16, fontWeight: 700 }}>{detail.name || detail.code}</span>
            <Text type="secondary" style={{ marginLeft: 8 }}>{detail.code}</Text>
            {detail.is_fund && <Tag style={{ marginLeft: 6 }}>ETF/LOF</Tag>}
            <Tag
              style={{
                marginLeft: 6,
                color: '#1677ff', borderColor: '#91caff', background: '#e6f4ff',
              }}
            >
              综合
            </Tag>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 18 }}>{palette.icon}</span>
            <Tag style={{ fontSize: 13, padding: '2px 8px', color: palette.color, background: palette.bg, borderColor: palette.border }}>
              {palette.label}
            </Tag>
            <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => onAddWatchlist(detail.code)}>
              加入自选
            </Button>
          </div>
        </div>
      </Card>

      {/* 综合分 + 操作建议 */}
      <Card size="small" title="综合评判">
        {/* 第一行：score + action/reason/hint */}
        <div style={{ display: 'flex', gap: 20, marginBottom: 12, alignItems: 'flex-start' }}>
          <div style={{ textAlign: 'center', padding: '8px 16px', background: palette.bg, borderRadius: 6, border: `1px solid ${palette.border}`, flexShrink: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 26, color: palette.color }}>{detail.combined_score.toFixed(1)}</div>
            <Text type="secondary" style={{ fontSize: 11 }}>综合分</Text>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
              {palette.action}
            </div>
            <Paragraph style={{ fontSize: 13, lineHeight: 1.7, marginBottom: 8 }}>
              {detail.entry_reason}
            </Paragraph>
            {/* 降级原因（如果有）：黄色提示条 */}
            {detail.demote_reason && (
              <div style={{
                marginBottom: 8, padding: '6px 10px', borderRadius: 4,
                background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e',
                fontSize: 12, lineHeight: 1.5,
              }}>
                ⚠️ {detail.demote_reason}
              </div>
            )}
            {detail.trade_hint && (
              <Text type="secondary" style={{ fontSize: 12, display: 'block', lineHeight: 1.6 }}>
                <Text strong style={{ color: palette.color }}>操作提示：</Text>{detail.trade_hint}
              </Text>
            )}
          </div>
        </div>

        {/* 第二行：涨幅空间（整宽 4 列网格大字）*/}
        {(detail.hist_golden_peak_median != null || detail.weekly_signal_gain_pct != null) && (() => {
          const cur = detail.weekly_signal_gain_pct ?? 0
          const med = detail.hist_golden_peak_median ?? 0
          const avg = detail.hist_golden_peak_pct ?? 0
          const remain_med = med - cur
          const remain_avg = avg - cur
          const Item = ({ val, label, hint }: { val: string; label: string; hint: string }) => (
            <div style={{ textAlign: 'center', padding: '10px 8px', background: '#fafafa', borderRadius: 6, border: '1px solid #f0f0f0' }}>
              <div style={{ fontWeight: 700, fontSize: 18, color: hint }}>{val}</div>
              <Text type="secondary" style={{ fontSize: 11 }}>{label}</Text>
            </div>
          )
          return (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, borderTop: '1px dashed #e5e7eb', paddingTop: 12 }}>
              <Item
                val={cur > 0 ? `+${cur.toFixed(1)}%` : `${cur.toFixed(1)}%`}
                label="当前已涨"
                hint={cur > 0 ? '#16a34a' : '#dc2626'}
              />
              <Item
                val={remain_med > 0 ? `+${remain_med.toFixed(1)}%` : `${remain_med.toFixed(1)}%`}
                label="剩余中位预期"
                hint={remain_med >= 10 ? '#16a34a' : remain_med > 0 ? '#0891b2' : '#d97706'}
              />
              <Item
                val={remain_avg > 0 ? `+${remain_avg.toFixed(1)}%` : `${remain_avg.toFixed(1)}%`}
                label="剩余平均预期"
                hint={remain_avg >= 10 ? '#16a34a' : remain_avg > 0 ? '#0891b2' : '#d97706'}
              />
              <Item
                val={`${med > 0 ? `+${med.toFixed(1)}` : '-'} / ${avg > 0 ? `+${avg.toFixed(1)}` : '-'}%`}
                label="历史中位 / 平均"
                hint="#6b7280"
              />
            </div>
          )
        })()}
      </Card>

      {/* 双腿 detail */}
      <Card size="small" title="周期详情">
        <LegBlock title="周线" leg={detail.weekly} />
        <Divider style={{ margin: '8px 0' }} />
        <LegBlock title="日线" leg={detail.daily} />
      </Card>
    </Space>
  )
}
