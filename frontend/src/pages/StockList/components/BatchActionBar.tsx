import { forwardRef, useState } from 'react'
import { Dropdown, Modal, message } from 'antd'
import { DeleteOutlined, ExperimentOutlined, FolderOutlined, SwapOutlined, SyncOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { SignalItem } from '@/api/signals'
import { StockGroup } from '@/api/groups'
import { removeWatchlist } from '@/api/watchlist'
import { generateCompare } from '@/api/compare'
import { BatchTaskType } from '@/api/batchTask'
import { useBatchGroupOps } from '../hooks/useBatchGroupOps'

interface BatchActionBarProps {
  selected: Set<string>
  groups: StockGroup[]
  allItems: SignalItem[]
  onClear: () => void
  batchRunning: boolean
  batchType: BatchTaskType | null
  batchCompleted: number
  batchTotal: number
  onBatchStart: (type: BatchTaskType) => void
}

export default function BatchActionBar({
  selected, groups, allItems, onClear,
  batchRunning, batchCompleted, batchTotal, onBatchStart,
}: BatchActionBarProps) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [comparing, setComparing] = useState(false)

  const { addToGroup, removeFromGroup, clearAllGroups, invalidateBoth } =
    useBatchGroupOps(selected, allItems, onClear)

  const removeSelected = () => {
    Modal.confirm({
      title: `批量移除 ${selected.size} 只自选？`,
      okText: '移除',
      okButtonProps: { danger: true },
      onOk: () => {
        Promise.all([...selected].map(code => removeWatchlist(code))).then(() => {
          message.success(`已移除 ${selected.size} 只`)
          onClear()
          invalidateBoth()
        }).catch(() => message.error('批量移除失败'))
      },
    })
  }

  if (selected.size === 0 && !batchRunning) return null

  return (
    <div style={{
      position: 'fixed',
      top: '35%',
      right: 'max(8px, calc(50% - 450px - 154px))',
      transform: 'translateY(-50%)',
      width: 132,
      zIndex: 50,
    }}>
      <div style={{ background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0', padding: '10px 0', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
        <div style={{ padding: '5px 14px', fontSize: 14, fontWeight: 600, color: '#374151', borderBottom: '1px solid #f0f0f0', marginBottom: 4 }}>
          {batchRunning ? `处理 ${batchCompleted}/${batchTotal}` : `已选 ${selected.size} 只`}
        </div>
        {!batchRunning && (
          <>
            <NavItem
              icon={<FolderOutlined />}
              label="加入分组"
              dropdown={
                <Dropdown
                  menu={{
                    items: groups.map(g => ({
                      key: `g-${g.id}`,
                      label: g.name,
                      onClick: () => addToGroup('add', g.id, g.name),
                    })),
                  }}
                  trigger={['click']}
                  placement="bottomRight"
                >
                  <BatchItemLabel icon={<FolderOutlined />} label="加入分组" />
                </Dropdown>
              }
            />
            <NavItem
              icon={<FolderOutlined />}
              label="移出分组"
              dropdown={
                <Dropdown
                  menu={{
                    items: [
                      ...groups.map(g => ({
                        key: `g-${g.id}`,
                        label: g.name,
                        onClick: () => removeFromGroup('remove', g.id, g.name),
                      })),
                      { type: 'divider' as const },
                      { key: 'g-none', label: '清除所有分组', onClick: () => clearAllGroups('clear') },
                    ],
                  }}
                  trigger={['click']}
                  placement="bottomRight"
                >
                  <BatchItemLabel icon={<FolderOutlined />} label="移出分组" />
                </Dropdown>
              }
            />
            <NavItem icon={<SyncOutlined />} label="同步" onClick={() => onBatchStart('sync')} />
            <NavItem icon={<ExperimentOutlined />} label="AI 分析" onClick={() => onBatchStart('ai')} />
            <NavItem icon={<ThunderboltOutlined />} label="操作指示" onClick={() => onBatchStart('action_plan')} />
            <NavItem
              icon={<SwapOutlined />}
              label={comparing ? '对比中...' : '对比分析'}
              onClick={() => {
                if (selected.size < 2) { message.warning('至少选择 2 只'); return }
                if (selected.size > 6) { message.warning('最多选择 6 只'); return }
                setComparing(true)
                generateCompare([...selected]).then((res) => {
                  setComparing(false)
                  onClear()
                  navigate(`/compare?id=${res.id}`)
                }).catch(() => {
                  setComparing(false)
                  message.error('对比分析失败')
                })
              }}
            />
            <div style={{ borderTop: '1px solid #f0f0f0', margin: '4px 0' }} />
            <NavItem icon={<DeleteOutlined />} label="移除自选" danger onClick={removeSelected} />
            <NavItem label="取消" muted onClick={onClear} />
          </>
        )}
      </div>
    </div>
  )
}

function NavItem({ icon, label, onClick, dropdown, danger, muted }: {
  icon?: React.ReactNode
  label: string
  onClick?: () => void
  dropdown?: React.ReactNode
  danger?: boolean
  muted?: boolean
}) {
  if (dropdown) return <>{dropdown}</>
  return (
    <div
      onClick={onClick}
      style={{
        padding: '7px 14px',
        cursor: 'pointer',
        fontSize: 14,
        color: danger ? '#dc2626' : muted ? '#9ca3af' : '#374151',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = '#f9fafb')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
    >
      {icon && <span style={{ marginRight: 6 }}>{icon}</span>}
      {label}
    </div>
  )
}

/** Dropdown 触发器：统一外观与 NavItem 一致的左侧菜单项（菜单里的菜单）。
 * 必须 forwardRef + 透传 HTML props —— AntD Dropdown 以 cloneElement 注入 onClick/onPointerDown
 * 等事件处理；若自定义组件不把这些 props 转发到根节点，点击完全无反应（曾踩过的坑）。
 */
const BatchItemLabel = forwardRef<HTMLDivElement, {
  icon?: React.ReactNode
  label: string
} & React.HTMLAttributes<HTMLDivElement>>(({ icon, label, ...rest }, ref) => (
  <div ref={ref} {...rest} style={{ padding: '7px 14px', cursor: 'pointer', fontSize: 14, color: '#374151', transition: 'background 0.1s', ...rest.style }}
    onMouseEnter={e => (e.currentTarget.style.background = '#f9fafb')}
    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
  >
    {icon && <span style={{ marginRight: 6 }}>{icon}</span>}
    {label}
  </div>
))
BatchItemLabel.displayName = 'BatchItemLabel'
