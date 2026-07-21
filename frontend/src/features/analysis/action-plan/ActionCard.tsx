import { Alert, Space, Tag, Tooltip, Typography } from 'antd'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DollarOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons'
import { ActionType, OverallStance, TraderAction } from '@/api/actionPlan'
import { priceColor } from '@/shared/theme'

const { Text } = Typography

const actionTypeLabel: Record<ActionType, { label: string; color: string }> = {
  buy_dip: { label: '逢低买入', color: 'red' },
  add_position: { label: '加仓', color: 'red' },
  trim_position: { label: '减仓', color: 'orange' },
  take_profit: { label: '止盈', color: 'gold' },
  stop_loss: { label: '止损', color: 'volcano' },
  wait_breakout: { label: '等突破', color: 'blue' },
  wait_pullback: { label: '等回踩', color: 'cyan' },
  observe: { label: '观望', color: 'default' },
}

export const stanceLabel: Record<OverallStance, { label: string; color: string; bg: string }> = {
  opportunistic_buy: { label: '择机买入', color: '#dc2626', bg: '#fef2f2' },
  wait: { label: '等待信号', color: '#2563eb', bg: '#eff6ff' },
  trim: { label: '逢高减仓', color: '#d97706', bg: '#fffbeb' },
  hold: { label: '持有观察', color: '#0891b2', bg: '#ecfeff' },
  reduce: { label: '主动减仓', color: '#ea580c', bg: '#fff7ed' },
  exit: { label: '离场', color: '#dc2626', bg: '#fef2f2' },
}

const horizonAbbrev: Record<string, string> = {
  combined: '综合',
  medium: '中',
  short: '短',
  anti_quant: '反量',
  reflexivity: '反身',
  mean_reversion: '左侧',
}

export function PriorityBadge({ p }: { p: number }) {
  const colors: Record<number, string> = {
    1: '#dc2626',
    2: '#ea580c',
    3: '#d97706',
    4: '#65a30d',
    5: '#94a3b8',
  }
  const color = colors[p] || '#94a3b8'
  return (
    <span
      style={{
        width: 22,
        height: 22,
        borderRadius: '50%',
        background: color,
        color: '#fff',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 12,
        fontWeight: 600,
        flexShrink: 0,
      }}
      title={`优先级 ${p}`}
    >
      {p}
    </span>
  )
}

export function ActionCard({ action }: { action: TraderAction }) {
  const t = actionTypeLabel[action.type] || actionTypeLabel.observe
  const dist = action.distance_pct
  const distColor =
    typeof dist === 'number'
      ? Math.abs(dist) < 3
        ? priceColor.up
        : dist > 0
        ? priceColor.up
        : priceColor.down
      : '#94a3b8'

  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 6,
        padding: '10px 12px',
        background: '#fafafa',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <PriorityBadge p={action.priority} />
        <Tag color={t.color} style={{ margin: 0 }}>
          {t.label}
        </Tag>
        {typeof dist === 'number' && (
          <Tooltip title="触发价距当前价百分比">
            <Tag
              style={{
                margin: 0,
                color: distColor,
                borderColor: distColor,
                fontSize: 12,
              }}
            >
              {dist > 0 ? <ArrowUpOutlined /> : dist < 0 ? <ArrowDownOutlined /> : null}
              {dist >= 0 ? '+' : ''}
              {dist.toFixed(2)}%
            </Tag>
          </Tooltip>
        )}
        <div style={{ flex: 1 }} />
        <Space size={2}>
          {action.sourced_from?.map((h) => (
            <Tag key={h} style={{ margin: 0, fontSize: 10, padding: '0 4px' }}>
              {horizonAbbrev[h] || h}
            </Tag>
          ))}
        </Space>
      </div>

      <Text style={{ display: 'block', marginBottom: 4 }}>{action.trigger_desc}</Text>

      <Space size={8} wrap style={{ fontSize: 12 }}>
        {action.size_hint && (
          <Text type="secondary">
            <DollarOutlined /> {action.size_hint}
          </Text>
        )}
        {typeof action.target_price === 'number' && action.target_price > 0 && (
          <Text type="secondary" style={{ color: priceColor.up }}>
            目标 {action.target_price}
          </Text>
        )}
        {typeof action.stop_loss === 'number' && action.stop_loss > 0 && (
          <Text type="secondary" style={{ color: priceColor.down }}>
            止损 {action.stop_loss}
          </Text>
        )}
      </Space>

      {action.rationale && (
        <Text
          type="secondary"
          style={{ display: 'block', marginTop: 6, fontSize: 12, fontStyle: 'italic' }}
        >
          → {action.rationale}
        </Text>
      )}
    </div>
  )
}

export function ConflictsSection({ conflicts }: { conflicts: string[] }) {
  if (!conflicts || conflicts.length === 0) return null
  return (
    <Alert
      type="warning"
      showIcon
      icon={<ExclamationCircleOutlined />}
      message="各视角冲突"
      description={
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          {conflicts.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      }
    />
  )
}
