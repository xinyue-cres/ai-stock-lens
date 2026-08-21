import { Button, Card, Empty, Space, Tag, Typography, Divider } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { CombinedItem, CombinedStage } from '@/api/score'
import { STAGE_PALETTE } from '../constants'

const { Title, Text, Paragraph } = Typography

const COMBINED_PALETTE: Record<CombinedStage, { color: string; bg: string; border: string; icon: string; label: string; action: string }> = {
  strong_buy:          { color: '#dc2626', bg: '#fef2f2', border: '#fecaca', icon: '🐂', label: '强买信号', action: '重仓买入' },
  buy:                 { color: '#ea580c', bg: '#fff7ed', border: '#fed7aa', icon: '📈', label: '买入',     action: '可买入' },
  watch_buy:           { color: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: '👀', label: '观察买',   action: '加自选盯日线' },
  deep_pullback_entry: { color: '#65a30d', bg: '#f7fee7', border: '#d9f99d', icon: '🎯', label: '深度回踩', action: '轻仓分批' },
  light_buy:           { color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', icon: '💡', label: '轻仓试',   action: '轻仓试仓' },
  watch:               { color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb', icon: '⏸️', label: '观望',     action: '不动' },
  avoid:               { color: '#4b5563', bg: '#f3f4f6', border: '#d1d5db', icon: '🚫', label: '回避',     action: '回避' },
}

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
        <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: 16 }}>
          <div style={{ textAlign: 'center', padding: '12px 8px', background: palette.bg, borderRadius: 6, border: `1px solid ${palette.border}` }}>
            <div style={{ fontWeight: 700, fontSize: 26, color: palette.color }}>{detail.combined_score.toFixed(1)}</div>
            <Text type="secondary" style={{ fontSize: 11 }}>综合分</Text>
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
              {palette.action}
            </div>
            <Paragraph style={{ fontSize: 13, lineHeight: 1.7, marginBottom: 8 }}>
              {detail.entry_reason}
            </Paragraph>
            {detail.trade_hint && (
              <Text type="secondary" style={{ fontSize: 12, display: 'block', lineHeight: 1.6 }}>
                <Text strong style={{ color: palette.color }}>操作提示：</Text>{detail.trade_hint}
              </Text>
            )}
          </div>
        </div>
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
