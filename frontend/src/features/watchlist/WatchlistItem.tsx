import { useState } from 'react'
import { Spin, Tag, Tooltip, Typography } from 'antd'
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

const strongStance = new Set(['opportunistic_buy', 'trim', 'reduce', 'exit'])

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

  if (stance) {
    if (stance.source === 'ai') {
      const p = verdictPalette[(stance.value as Verdict) || 'neutral']
      elements.push(
        <Tooltip key="verdict" title={`AI 综合 · ${stance.as_of}`}>
          <Tag style={{ marginRight: 0, color: p.color, borderColor: p.border, background: p.bg, fontWeight: 500 }}>
            {p.label}
          </Tag>
        </Tooltip>
      )
    } else {
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
  const pos = item.position
  const posPnl = pos?.unrealized_pnl_pct

  return (
    <div
      onClick={() => onSelect(item.code)}
      style={{
        padding: '8px 12px',
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
      {/* 第一排：名称 + 涨跌幅 + StatusBadge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            fontWeight: 500,
            fontSize: 13,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {item.pinned && <PushpinFilled style={{ color: accent.pin, fontSize: 11 }} />}
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.name || item.code}</span>
          {typeof pct === 'number' && (
            <span
              style={{
                fontSize: 12,
                color: pct >= 0 ? priceColor.up : priceColor.down,
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
            </span>
          )}
        </div>
        <div style={{ flexShrink: 0, display: 'flex', gap: 3, alignItems: 'center' }}>
          <StatusBadge item={item} />
        </div>
      </div>

      {/* 第二排：code + 日期 + 持仓浮盈 + 操作菜单 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>{item.code}</Text>
        {item.as_of_date && (
          <Text
            style={{
              fontSize: 10,
              color: isStale(item.as_of_date) ? '#d97706' : '#b0b8c4',
            }}
            title={`数据截至 ${item.as_of_date}`}
          >
            {formatShortDate(item.as_of_date)}
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
            持仓 {posPnl >= 0 ? '+' : ''}{(posPnl * 100).toFixed(1)}%
          </Text>
        )}
        <div style={{ marginLeft: 'auto', flexShrink: 0 }}>
          <ItemActionMenu
            item={item}
            open={menuOpen}
            onOpenChange={setMenuOpen}
            onPin={onPin}
            onRemove={onRemove}
            onEditPosition={onEditPosition}
          />
        </div>
      </div>
    </div>
  )
}

function formatShortDate(iso: string): string {
  const now = new Date()
  const [y, m, d] = iso.split('-')
  if (String(now.getFullYear()) === y) return `${m}-${d}`
  return `${y.slice(2)}-${m}-${d}`
}

function isStale(asOf: string): boolean {
  const today = new Date()
  const isTodayOver = today.getHours() >= 15
  const expected = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  if (!isTodayOver) expected.setDate(expected.getDate() - 1)
  while (expected.getDay() === 0 || expected.getDay() === 6) expected.setDate(expected.getDate() - 1)
  const asOfDate = new Date(asOf + 'T00:00:00')
  return asOfDate < expected
}
