import { useState } from 'react'
import { Button, Checkbox, Dropdown, Tag, Tooltip, Typography } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, DeleteOutlined, FolderOutlined, LoadingOutlined, MoreOutlined, SyncOutlined } from '@ant-design/icons'
import { SignalItem, ReportTimes } from '@/api/signals'
import { StockGroup } from '@/api/groups'
import { BatchItemStatus } from '@/api/batchTask'
import { priceColor, verdictPalette, Verdict } from '@/shared/theme'
import { stanceLabel, actionableStances } from '../constants'

const { Text } = Typography

function getHeatColor(item: SignalItem): string | null {
  if (item.stance && actionableStances.has(item.stance.value)) return '#dc2626'
  const pct = item.pct_chg ?? 0
  if (Math.abs(pct) >= 3) return '#f59e0b'
  return null
}

interface StockRowProps {
  item: SignalItem
  groups: StockGroup[]
  selectMode: boolean
  checked: boolean
  batchStatus?: BatchItemStatus | null
  onToggle: (code: string) => void
  onClick: () => void
  onRemove: () => void
  onGroupChange: (gids: number[]) => void
  onSync: () => void
}

export default function StockRow({ item, groups, selectMode, checked, batchStatus, onToggle, onClick, onRemove, onGroupChange, onSync }: StockRowProps) {
  const [hovered, setHovered] = useState(false)
  const heat = getHeatColor(item)
  const pct = item.pct_chg
  const pos = item.position
  const posPnl = pos?.unrealized_pnl_pct
  const curIds = item.group_ids || []

  const groupMenu = groups.map(g => {
    const inGroup = curIds.includes(g.id)
    return {
      key: `g-${g.id}`,
      label: inGroup ? `✓ ${g.name}` : `  ${g.name}`,
      onClick: () => {
        if (inGroup) {
          onGroupChange(curIds.filter(id => id !== g.id))
        } else {
          onGroupChange([...curIds, g.id])
        }
      },
    }
  })
  if (curIds.length > 0) {
    groupMenu.push({ key: 'g-none', label: '清除所有分组', onClick: () => onGroupChange([]) })
  }

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '10px 16px',
        borderBottom: '1px solid #f5f5f5',
        cursor: 'pointer',
        background: hovered ? '#f9fafb' : '#fff',
        borderLeft: `3px solid ${heat || 'transparent'}`,
        transition: 'background 0.1s',
      }}
    >
      {selectMode && (
        <Checkbox
          checked={checked}
          onClick={e => { e.stopPropagation(); onToggle(item.code) }}
          style={{ marginRight: 8 }}
        />
      )}
      <div style={{ width: 140, flexShrink: 0 }}>
        <div style={{ fontWeight: 500, fontSize: 13, lineHeight: 1.3 }}>{item.name || item.code}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>{item.code}</Text>
          {typeof pct === 'number' && (
            <span style={{ fontSize: 12, fontWeight: 600, color: pct >= 0 ? priceColor.up : priceColor.down }}>
              {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
            </span>
          )}
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 6 }}>
        {item.ai_verdict && (() => {
          const p = verdictPalette[(item.ai_verdict as Verdict) || 'neutral']
          return <Tag style={{ margin: 0, color: p.color, borderColor: p.border, background: p.bg, fontSize: 11 }}>{p.label}</Tag>
        })()}
        {item.stance && stanceLabel[item.stance.value] && (
          <Tag color={stanceLabel[item.stance.value].color} style={{ margin: 0, fontSize: 11 }}>
            {stanceLabel[item.stance.value].label}
          </Tag>
        )}
        {item.note && (
          <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>{item.note}</Text>
        )}
        {batchStatus && <BatchStatusBadge status={batchStatus} />}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        {item.report_times && <ReportTimesIndicator times={item.report_times} />}
        {typeof posPnl === 'number' && (
          <span style={{ fontSize: 12, fontWeight: 500, color: posPnl >= 0 ? priceColor.up : priceColor.down, minWidth: 60, textAlign: 'right' }}>
            持仓 {posPnl >= 0 ? '+' : ''}{(posPnl * 100).toFixed(1)}%
          </span>
        )}
        {item.as_of_date && (() => {
          const diffD = Math.floor((Date.now() - new Date(item.as_of_date).getTime()) / 86_400_000)
          const color = diffD <= 1 ? '#16a34a' : diffD <= 3 ? '#f59e0b' : '#dc2626'
          return (
            <span style={{ fontSize: 11, color, border: `1px solid ${color}`, borderRadius: 3, padding: '0 5px', lineHeight: '20px' }}>
              数据 {item.as_of_date.slice(5)}
            </span>
          )
        })()}

        <div style={{ width: 56, display: 'flex', gap: 2, visibility: hovered ? 'visible' : 'hidden' }}>
          <Tooltip title="同步">
            <Button type="text" size="small" icon={<SyncOutlined style={{ fontSize: 12 }} />} onClick={e => { e.stopPropagation(); onSync() }} />
          </Tooltip>
          <Dropdown
            menu={{
              items: [
                { key: 'group', label: '移动到分组', icon: <FolderOutlined />, children: groupMenu.length ? groupMenu : [{ key: 'empty', label: '暂无分组', disabled: true }] },
                { type: 'divider' as const },
                { key: 'remove', label: '移除', icon: <DeleteOutlined />, danger: true, onClick: () => { onRemove() } },
              ],
            }}
            trigger={['click']}
            placement="bottomRight"
          >
            <Button type="text" size="small" icon={<MoreOutlined style={{ fontSize: 12 }} />} onClick={e => e.stopPropagation()} />
          </Dropdown>
        </div>
      </div>
    </div>
  )
}

function BatchStatusBadge({ status }: { status: BatchItemStatus }) {
  if (status === 'running') {
    return <span style={{ fontSize: 11, color: '#3b82f6', display: 'inline-flex', alignItems: 'center', gap: 3 }}><LoadingOutlined spin /> 生成中</span>
  }
  if (status === 'done') {
    return <span style={{ fontSize: 11, color: '#16a34a', display: 'inline-flex', alignItems: 'center', gap: 3 }}><CheckCircleOutlined /> 完成</span>
  }
  if (status === 'error') {
    return <span style={{ fontSize: 11, color: '#dc2626', display: 'inline-flex', alignItems: 'center', gap: 3 }}><CloseCircleOutlined /> 失败</span>
  }
  if (status === 'pending') {
    return <span style={{ fontSize: 11, color: '#9ca3af' }}>等待中</span>
  }
  return null
}

const HORIZON_LABELS: Record<string, string> = {
  combined: '综合',
  anti_quant: '反量',
  reflexivity: '反身',
  action_plan: '指示',
}

const STALE_THRESHOLD_H = 24

function getTimeDiffHours(timeStr: string): number {
  const now = Date.now()
  const then = new Date(timeStr.replace(' ', 'T')).getTime()
  return (now - then) / 3_600_000
}

function formatRelativeTime(timeStr: string): string {
  const diffH = getTimeDiffHours(timeStr)
  const diffMin = Math.round(diffH * 60)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}m`
  if (diffH < 24) return `${Math.floor(diffH)}h`
  return `${Math.floor(diffH / 24)}d`
}

function timeColor(timeStr: string | null | undefined): string {
  if (!timeStr) return '#e5e7eb'
  const h = getTimeDiffHours(timeStr)
  if (h < STALE_THRESHOLD_H) return '#16a34a'
  if (h < STALE_THRESHOLD_H * 3) return '#f59e0b'
  return '#dc2626'
}

function ReportTimesIndicator({ times }: { times: ReportTimes }) {
  const entries = Object.entries(HORIZON_LABELS) as [keyof ReportTimes, string][]
  const hasAny = entries.some(([k]) => times[k])
  if (!hasAny) return null

  return (
    <span style={{ display: 'inline-flex', gap: 4, fontSize: 11, whiteSpace: 'nowrap' }}>
      {entries.map(([k, label]) => {
        const t = times[k]
        const color = timeColor(t)
        return (
          <Tooltip key={k} title={t || '未生成'}>
            <span style={{
              color,
              border: `1px solid ${color}`,
              borderRadius: 3,
              padding: '0 5px',
              fontSize: 11,
              lineHeight: '20px',
            }}>
              {label} {t ? formatRelativeTime(t) : '--'}
            </span>
          </Tooltip>
        )
      })}
    </span>
  )
}
