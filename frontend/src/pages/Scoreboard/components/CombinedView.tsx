import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Segmented, Spin, Tag, Typography, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import { getCombinedList, type CombinedItem, type CombinedStage } from '@/api/score'
import { STAGE_PALETTE } from '../constants'

const { Text } = Typography

/** 7 档 combined_stage → 标签主题色 + icon + label */
const COMBINED_PALETTE: Record<CombinedStage, { color: string; bg: string; border: string; icon: string; label: string }> = {
  strong_buy:          { color: '#dc2626', bg: '#fef2f2', border: '#fecaca', icon: '🐂', label: '强买信号' },
  buy:                 { color: '#ea580c', bg: '#fff7ed', border: '#fed7aa', icon: '📈', label: '买入' },
  watch_buy:           { color: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: '👀', label: '观察买' },
  deep_pullback_entry: { color: '#65a30d', bg: '#f7fee7', border: '#d9f99d', icon: '🎯', label: '深度回踩' },
  light_buy:           { color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', icon: '💡', label: '轻仓试' },
  watch:               { color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb', icon: '⏸️', label: '观望' },
  avoid:               { color: '#4b5563', bg: '#f3f4f6', border: '#d1d5db', icon: '🚫', label: '回避' },
}

interface CombinedRowProps {
  item: CombinedItem
  active: boolean
  onClick: (code: string) => void
  onAddWatchlist: (code: string) => void
}

/** 单行综合 item（ScoreRow 风格，宽度自适应），显示代码 + 综合分 + combined_stage 标签 */
function CombinedRow({ item, active, onClick, onAddWatchlist }: CombinedRowProps) {
  const palette = COMBINED_PALETTE[item.combined_stage] ?? COMBINED_PALETTE.watch
  const wStage = item.weekly.trend_stage ? STAGE_PALETTE[item.weekly.trend_stage] : null
  const dStage = item.daily.trend_stage ? STAGE_PALETTE[item.daily.trend_stage] : null

  return (
    <div
      onClick={() => onClick(item.code)}
      style={{
        padding: '10px 14px',
        borderBottom: '1px solid #f0f0f0',
        cursor: 'pointer',
        background: active ? '#e6f4ff' : 'transparent',
        borderLeft: active ? '3px solid #1677ff' : '3px solid transparent',
        transition: 'background 0.15s ease',
      }}
      onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = '#fafafa' }}
      onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent' }}
    >
      {/* 第一行：名称 + 综合分 + combined_stage tag */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{item.name || item.code}</span>
          <Text type="secondary" style={{ fontSize: 11 }}>{item.code}</Text>
          {item.is_fund && <Tag style={{ fontSize: 10, lineHeight: '14px', padding: '0 4px', marginInlineEnd: 0 }}>ETF</Tag>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ fontSize: 14 }}>{palette.icon}</span>
          <Tag
            style={{
              color: palette.color, background: palette.bg, borderColor: palette.border,
              fontSize: 11, lineHeight: '16px', padding: '0 6px', marginInlineEnd: 0,
            }}
          >
            {palette.label}
          </Tag>
          <span style={{ fontWeight: 700, fontSize: 15, color: palette.color, minWidth: 36, textAlign: 'right' }}>
            {item.combined_score.toFixed(1)}
          </span>
        </div>
      </div>

      {/* 第二行：weekly / daily 两条腿的简版状态 */}
      <div style={{ display: 'flex', gap: 10, fontSize: 11, color: 'rgba(0,0,0,0.65)', marginBottom: 4, flexWrap: 'wrap', rowGap: 2 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span style={{ color: 'rgba(0,0,0,0.45)' }}>周</span>
          <span style={{ fontWeight: 600 }}>{item.weekly.total_score?.toFixed(0) ?? '-'}</span>
          {wStage && <span style={{ color: wStage.color }}>{wStage.label}</span>}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span style={{ color: 'rgba(0,0,0,0.45)' }}>日</span>
          <span style={{ fontWeight: 600 }}>{item.daily.total_score?.toFixed(0) ?? '-'}</span>
          {dStage && <span style={{ color: dStage.color }}>{dStage.label}</span>}
        </span>
        {/* signal_score 双腿 + 剩余中位预期 */}
        <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span style={{ color: 'rgba(0,0,0,0.45)' }}>信</span>
          <span style={{ fontWeight: 500 }}>
            {item.weekly.signal_score?.toFixed(0) ?? '-'}/{item.daily.signal_score?.toFixed(0) ?? '-'}
          </span>
        </span>
        {/* 历史可预期： 剩余中位（hist_med - signal_gain）*/}
        {item.hist_golden_peak_median != null && item.weekly_signal_gain_pct != null && (() => {
          const remain = item.hist_golden_peak_median - item.weekly_signal_gain_pct
          return (
            <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <span style={{ color: 'rgba(0,0,0,0.45)' }}>余中</span>
              <span style={{ fontWeight: 600, color: remain >= 10 ? '#16a34a' : remain > 0 ? '#0891b2' : '#d97706' }}>
                {remain > 0 ? `+${remain.toFixed(0)}%` : `${remain.toFixed(0)}%`}
              </span>
            </span>
          )
        })()}
        {!item.in_watchlist && (
          <Button
            size="small"
            type="text"
            icon={<PlusOutlined />}
            style={{ padding: 0, height: '16px', lineHeight: '16px', fontSize: 11, marginLeft: 'auto' }}
            onClick={(e) => { e.stopPropagation(); onAddWatchlist(item.code) }}
          >
            加自选
          </Button>
        )}
      </div>

      {/* 第三行：操作建议（一行截断） */}
      <Text
        type="secondary"
        style={{
          fontSize: 11, display: 'block',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}
      >
        {item.entry_reason}
      </Text>
    </div>
  )
}

interface CombinedViewProps {
  scope: string
  groupIds: number[]
  selected: string | null
  onSelect: (code: string) => void
  onAddWatchlist: (code: string) => void
  renderDetail?: (code: string) => React.ReactNode  // 右侧详情渲染（可选）
}

/** 左侧列表（ScoreRow 风格，含 stage 过滤 Segmented + 自选分组过滤） */
export function CombinedList({
  scope, groupIds, selected, onSelect, onAddWatchlist,
}: CombinedViewProps) {
  const [stageFilter, setStageFilter] = useState<CombinedStage | 'entry' | 'all'>('entry')
  const groupIdsKey = groupIds.length ? groupIds.join(',') : undefined

  const listQ = useQuery({
    queryKey: ['combined-list', scope, groupIdsKey, stageFilter],
    queryFn: () =>
      getCombinedList({
        scope,
        limit: 200,
        group_ids: groupIdsKey,
        can_entry: stageFilter === 'entry' ? true : undefined,
        combined_stage:
          stageFilter !== 'all' && stageFilter !== 'entry' ? stageFilter : undefined,
      }),
  })
  const items = listQ.data ?? []

  return (
    <Card
      size="small"
      title={`日周合并 (${items.length})`}
      style={{ width: 540, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
      styles={{
        header: { flexShrink: 0, minHeight: 45, padding: '8px 16px' },
        body: { padding: 0, flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' },
      }}
    >
      {/* stage 过滤 */}
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0', flexShrink: 0 }}>
        <Segmented
          size="small"
          value={stageFilter}
          onChange={(v) => setStageFilter(v as typeof stageFilter)}
          options={[
            { value: 'all', label: '全部' },
            { value: 'entry', label: '可入手' },
            { value: 'strong_buy', label: '🐂 强买' },
            { value: 'buy', label: '📈 买入' },
            { value: 'light_buy', label: '💡 轻仓' },
            { value: 'deep_pullback_entry', label: '🎯 回踩' },
            { value: 'watch_buy', label: '👀 观察' },
            { value: 'watch', label: '⏸️ 观望' },
            { value: 'avoid', label: '🚫 回避' },
          ]}
        />
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {listQ.isLoading && (
          <div style={{ padding: 32, textAlign: 'center' }}><Spin /></div>
        )}
        {!listQ.isLoading && items.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无综合评判记录"
            style={{ padding: 24 }}
          />
        )}
        {items.map((item) => (
          <CombinedRow
            key={item.code}
            item={item}
            active={selected === item.code}
            onClick={onSelect}
            onAddWatchlist={onAddWatchlist}
          />
        ))}
      </div>
    </Card>
  )
}

/** 兼容老 API：不再使用卡片网格。导出别名保留向后兼容。 */
export default CombinedList
