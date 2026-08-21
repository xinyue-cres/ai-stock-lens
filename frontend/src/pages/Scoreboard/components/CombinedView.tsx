import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Segmented, Spin, Tag, Typography } from 'antd'
import { getCombinedList, type CombinedItem, type CombinedStage } from '@/api/score'
import { STAGE_PALETTE } from '../constants'

const { Text } = Typography

/** 7 档 combined_stage → 卡片主题色 + icon + label */
const COMBINED_PALETTE: Record<CombinedStage, { color: string; bg: string; border: string; icon: string; label: string }> = {
  strong_buy:          { color: '#dc2626', bg: '#fef2f2', border: '#fecaca', icon: '🐂', label: '强买信号' },
  buy:                 { color: '#ea580c', bg: '#fff7ed', border: '#fed7aa', icon: '📈', label: '买入' },
  watch_buy:           { color: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: '👀', label: '观察买' },
  deep_pullback_entry: { color: '#65a30d', bg: '#f7fee7', border: '#d9f99d', icon: '🎯', label: '深度回踩' },
  light_buy:           { color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', icon: '💡', label: '轻仓试' },
  watch:               { color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb', icon: '⏸️', label: '观望' },
  avoid:               { color: '#4b5563', bg: '#f3f4f6', border: '#d1d5db', icon: '🚫', label: '回避' },
}

/** 周期 stage 标签的小展示（卡片里一行小字） */
function LegInfo({ label, leg }: { label: string; leg: CombinedItem['weekly'] }) {
  const stage = leg.trend_stage ? STAGE_PALETTE[leg.trend_stage] : null
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 12, lineHeight: '20px' }}>
      <span style={{ color: 'rgba(0,0,0,0.45)', width: 30 }}>{label}</span>
      <span style={{ fontWeight: 600, fontSize: 13 }}>{leg.total_score?.toFixed(1) ?? '-'}</span>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {leg.signal_score != null ? `signal ${leg.signal_score.toFixed(0)}` : ''}
      </Text>
      {stage && (
        <Tag style={{ fontSize: 11, lineHeight: '16px', padding: '0 6px', color: stage.color, background: stage.bg, borderColor: stage.border, marginInlineEnd: 0 }}>
          {stage.label}
        </Tag>
      )}
      {leg.peak_signal && (
        <Text type="secondary" style={{ fontSize: 11 }}>{leg.peak_signal}{leg.peak_conf ? `(${leg.peak_conf})` : ''}</Text>
      )}
    </div>
  )
}

interface CombinedViewProps {
  scope: string
  /** 点击卡片：切回 weekly + 选中改 code（父组件 discipline） */
  onSelectCode: (code: string) => void
}

export default function CombinedView({ scope, onSelectCode }: CombinedViewProps) {
  // 过滤 stage；undefined 表示全部
  const [stageFilter, setStageFilter] = useState<CombinedStage | 'entry' | 'all'>('entry')

  const listQ = useQuery({
    queryKey: ['combined-list', scope, stageFilter],
    queryFn: () =>
      getCombinedList({
        scope,
        limit: 200,
        // 'entry' 模式 = 只看可入手
        can_entry: stageFilter === 'entry' ? true : undefined,
        // 具体 stage 过滤
        combined_stage:
          stageFilter !== 'all' && stageFilter !== 'entry' ? stageFilter : undefined,
      }),
  })
  const items = listQ.data ?? []

  return (
    <Card
      size="small"
      title={`日周合并评判 (${items.length})`}
      style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
      styles={{ header: { flexShrink: 0, minHeight: 45, padding: '8px 16px' }, body: { padding: 16, flex: 1, overflowY: 'auto' } }}
    >
      {/* 阶段筛选 */}
      <div style={{ marginBottom: 12 }}>
        <Segmented
          size="small"
          value={stageFilter}
          onChange={(v) => setStageFilter(v as typeof stageFilter)}
          options={[
            { value: 'entry', label: '可入手' },
            { value: 'strong_buy', label: '🐂 强买' },
            { value: 'buy', label: '📈 买入' },
            { value: 'watch_buy', label: '👀 观察买' },
            { value: 'deep_pullback_entry', label: '🎯 深度回踩' },
            { value: 'light_buy', label: '💡 轻仓试' },
            { value: 'all', label: '全部' },
          ]}
        />
      </div>

      {listQ.isLoading && (
        <div style={{ padding: 32, textAlign: 'center' }}>
          <Spin />
        </div>
      )}
      {!listQ.isLoading && items.length === 0 && (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无综合评判记录，先扫一次" style={{ padding: 24 }} />
      )}

      {/* 卡片网格：3 列自适应 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
          gap: 12,
        }}
      >
        {items.map((item) => {
          const palette = COMBINED_PALETTE[item.combined_stage] ?? COMBINED_PALETTE.watch
          return (
            <div
              key={item.code}
              onClick={() => onSelectCode(item.code)}
              style={{
                border: `1px solid ${palette.border}`,
                background: palette.bg,
                borderRadius: 8,
                padding: 12,
                cursor: 'pointer',
                transition: 'transform 0.15s ease, box-shadow 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)'
                e.currentTarget.style.boxShadow = `0 4px 12px ${palette.border}66`
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = ''
                e.currentTarget.style.boxShadow = ''
              }}
            >
              {/* 头部：stage chip + name + score */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 16 }}>{palette.icon}</span>
                  <span style={{ fontWeight: 700, fontSize: 13, color: palette.color }}>{palette.label}</span>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>{item.name || item.code}</span>
                  <Text type="secondary" style={{ fontSize: 11 }}>{item.code}</Text>
                </div>
                <div style={{ fontWeight: 700, fontSize: 15, color: palette.color }}>{item.combined_score.toFixed(1)}</div>
              </div>

              {/* 双腿核心数据 */}
              <div style={{ marginBottom: 10, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <LegInfo label="周线" leg={item.weekly} />
                <LegInfo label="日线" leg={item.daily} />
              </div>

              {/* 操作建议 */}
              <div style={{ borderTop: `1px dashed ${palette.border}`, paddingTop: 8, fontSize: 12 }}>
                <div style={{ lineHeight: 1.5, color: 'rgba(0,0,0,0.85)' }}>{item.entry_reason}</div>
                {item.trade_hint && (
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4, lineHeight: 1.5 }}>
                    {item.trade_hint}
                  </Text>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
