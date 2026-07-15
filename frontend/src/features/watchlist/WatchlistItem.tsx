import { useState } from 'react'
import { Space, Spin, Tag, Tooltip, Typography } from 'antd'
import { PushpinFilled } from '@ant-design/icons'
import { Signal, SignalItem } from '@/api/signals'
import { accent, priceColor, verdictPalette, Verdict } from '@/shared/theme'
import { ItemActionMenu } from './ItemActionMenu'

const { Text } = Typography

interface Props {
  item: SignalItem
  active: boolean
  onSelect: (code: string) => void
  onPin: (code: string, pinned: boolean) => void
  onRemove: (code: string) => void
  onEditPosition: (code: string) => void
}

/** Trader stance 到显示的映射；覆盖后端可能返回的所有 overall_stance 值。 */
const stanceDisplay: Record<string, { label: string; color: string; bg: string; border: string }> = {
  opportunistic_buy: { label: '择机买入', color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
  wait: { label: '等待', color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  trim: { label: '逢高减', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  hold: { label: '持有', color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc' },
  reduce: { label: '减仓', color: '#ea580c', bg: '#fff7ed', border: '#fed7aa' },
  exit: { label: '离场', color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
}

function TopSignalTag({ s }: { s: Signal }) {
  const p = verdictPalette[s.direction]
  return (
    <Tag style={{ marginRight: 0, color: p.color, borderColor: p.color, background: p.bg }}>
      {s.label}
    </Tag>
  )
}

/** 需要额外展示的 Trader 强信号 stance（wait/hold 太普遍不展示） */
const strongStance = new Set(['opportunistic_buy', 'trim', 'reduce', 'exit'])

/** 右上角展示优先级：empty(同步中) → AI verdict + 强 stance → top_signal → 无 */
function StatusBadge({ item }: { item: SignalItem }) {
  if (item.empty) {
    return (
      <Tag color="default" style={{ marginRight: 0 }}>
        <Spin size="small" style={{ marginRight: 4 }} />
        同步中
      </Tag>
    )
  }

  const stance = item.stance
  const elements: React.ReactNode[] = []

  // AI verdict（stance.source=ai 或无 action_plan 时从 combined 拿的 verdict）
  // 若有 trader stance，还需拿 AI verdict — 改为后端直接带两个
  // 当前逻辑：stance.source=trader 时 value 是 stance 值；source=ai 时 value 是 verdict
  // 所以需要从 stance 里拆：
  if (stance) {
    if (stance.source === 'ai') {
      // 只有 AI verdict
      const p = verdictPalette[(stance.value as Verdict) || 'neutral']
      elements.push(
        <Tooltip key="verdict" title={`AI 综合 · ${stance.as_of}`}>
          <Tag style={{ marginRight: 0, color: p.color, borderColor: p.border, background: p.bg, fontWeight: 500 }}>
            {p.label}
          </Tag>
        </Tooltip>
      )
    } else {
      // source=trader：先展示 AI verdict（从 ai_verdict 字段），再看强 stance
      if (item.ai_verdict) {
        const p = verdictPalette[(item.ai_verdict as Verdict) || 'neutral']
        elements.push(
          <Tooltip key="verdict" title={`AI 综合分析`}>
            <Tag style={{ marginRight: 0, color: p.color, borderColor: p.border, background: p.bg, fontWeight: 500 }}>
              {p.label}
            </Tag>
          </Tooltip>
        )
      }
      // 强信号 stance 额外展示
      if (strongStance.has(stance.value)) {
        const sd = stanceDisplay[stance.value]
        if (sd) {
          elements.push(
            <Tooltip key="stance" title={`操作指示 · ${stance.as_of}`}>
              <Tag style={{ marginRight: 0, color: sd.color, borderColor: sd.border, background: sd.bg, fontSize: 11, padding: '0 4px' }}>
                {sd.label}
              </Tag>
            </Tooltip>
          )
        }
      }
    }
  }

  if (elements.length > 0) return <>{elements}</>
  if (item.top_signal) return <TopSignalTag s={item.top_signal} />
  return null
}

export function WatchlistItem({ item, active, onSelect, onPin, onRemove, onEditPosition }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const pct = item.pct_chg
  // 右下角 badge 沿用 top_signal.direction 决定颜色；无 top_signal 时默认 neutral
  const dir = item.top_signal?.direction || 'neutral'
  const badgeColor = verdictPalette[dir].color
  const badgeBg = verdictPalette[dir].bg
  const pos = item.position
  const posPnl = pos?.unrealized_pnl_pct

  return (
    <div
      onClick={() => onSelect(item.code)}
      style={{
        position: 'relative',
        padding: '10px 12px 26px',
        borderBottom: '1px solid #f5f5f5',
        cursor: 'pointer',
        background: active ? '#eff6ff' : menuOpen ? '#fafafa' : '#fff',
        borderLeft: active
          ? `3px solid ${accent.active}`
          : item.pinned
          ? `3px solid ${accent.pin}`
          : '3px solid transparent',
        transition: 'background 0.15s',
      }}
      onMouseEnter={(e) => {
        if (!active && !menuOpen) (e.currentTarget as HTMLDivElement).style.background = '#fafafa'
      }}
      onMouseLeave={(e) => {
        if (!active && !menuOpen) (e.currentTarget as HTMLDivElement).style.background = '#fff'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontWeight: 500,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            {item.pinned && <PushpinFilled style={{ color: accent.pin, fontSize: 12 }} />}
            {item.name || item.code}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>{item.code}</Text>
            {typeof pct === 'number' && (
              <Text
                style={{
                  fontSize: 12,
                  color: pct >= 0 ? priceColor.up : priceColor.down,
                  fontWeight: 500,
                }}
              >
                {pct >= 0 ? '+' : ''}
                {pct.toFixed(2)}%
              </Text>
            )}
            {typeof posPnl === 'number' && (
              <Text
                style={{
                  fontSize: 11,
                  color: posPnl >= 0 ? priceColor.up : priceColor.down,
                  fontWeight: 500,
                  border: `1px solid ${posPnl >= 0 ? priceColor.up : priceColor.down}`,
                  padding: '0 4px',
                  borderRadius: 3,
                  lineHeight: '14px',
                }}
                title={`持仓 ${pos?.quantity} 股 · 成本 ${pos?.cost_price} · 浮盈 ${(posPnl * 100).toFixed(2)}%`}
              >
                持仓 {posPnl >= 0 ? '+' : ''}
                {(posPnl * 100).toFixed(1)}%
              </Text>
            )}
          </div>
        </div>
        <Space size={4} direction="vertical" align="end">
          <StatusBadge item={item} />
        </Space>
      </div>

      {/* 右下角：+N Badge + 更多按钮 */}
      <div
        style={{
          position: 'absolute',
          right: 4,
          bottom: 2,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        {item.signals?.length > 1 && (
          <span
            style={{
              fontSize: 11,
              color: badgeColor,
              background: badgeBg,
              border: `1px solid ${badgeColor}`,
              padding: '0 6px',
              borderRadius: 8,
              lineHeight: '16px',
              fontWeight: 600,
            }}
          >
            +{item.signals.length - 1}
          </span>
        )}
        <ItemActionMenu
          item={item}
          open={menuOpen}
          onOpenChange={setMenuOpen}
          onPin={onPin}
          onRemove={onRemove}
          onEditPosition={onEditPosition}
        />
      </div>

      {/* 左下角：数据日期，陈旧时黄字 */}
      {item.as_of_date && (
        <span
          style={{
            position: 'absolute',
            left: 12,
            bottom: 4,
            fontSize: 10,
            color: isStale(item.as_of_date) ? '#d97706' : '#94a3b8',
            lineHeight: '14px',
          }}
          title={`数据截至 ${item.as_of_date}`}
        >
          {formatShortDate(item.as_of_date)}
        </span>
      )}
    </div>
  )
}

/** 显示成 MM-DD；跨年时补上年份。 */
function formatShortDate(iso: string): string {
  const now = new Date()
  const [y, m, d] = iso.split('-')
  if (String(now.getFullYear()) === y) return `${m}-${d}`
  return `${y.slice(2)}-${m}-${d}`
}

/** 与"最近应有交易日"比较：滞后 ≥1 交易日算陈旧。 */
function isStale(asOf: string): boolean {
  const today = new Date()
  const isTodayOver = today.getHours() >= 15
  const expected = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  if (!isTodayOver) expected.setDate(expected.getDate() - 1)
  while (expected.getDay() === 0 || expected.getDay() === 6) expected.setDate(expected.getDate() - 1)
  const asOfDate = new Date(asOf + 'T00:00:00')
  return asOfDate < expected
}
