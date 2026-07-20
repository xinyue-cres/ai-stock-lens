import { Button, Dropdown, Modal, Typography, message } from 'antd'
import { DeleteOutlined, ExperimentOutlined, FolderOutlined, SyncOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { SignalItem } from '@/api/signals'
import { patchStock, StockGroup } from '@/api/groups'
import { removeWatchlist } from '@/api/watchlist'
import { syncSingleStock } from '@/api/sync'
import { BatchTaskType } from '@/api/batchTask'

const { Text } = Typography

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
  batchRunning, batchType, batchCompleted, batchTotal, onBatchStart,
}: BatchActionBarProps) {
  const qc = useQueryClient()

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
            <ActionItem
              label="移组"
              dropdown={
                <Dropdown
                  menu={{
                    items: [
                      ...groups.map(g => ({
                        key: `g-${g.id}`,
                        label: `加入「${g.name}」`,
                        onClick: () => {
                          Promise.all([...selected].map(code => {
                            const cur = allItems.find(i => i.code === code)
                            const curIds = cur?.group_ids || []
                            if (curIds.includes(g.id)) return Promise.resolve()
                            return patchStock(code, { group_ids: [...curIds, g.id] })
                          })).then(() => {
                            message.success(`${selected.size} 只已加入「${g.name}」`)
                            onClear()
                            qc.invalidateQueries({ queryKey: ['signals-today'] })
                            qc.invalidateQueries({ queryKey: ['groups'] })
                          })
                        },
                      })),
                      { key: 'g-none', label: '清除所有分组', onClick: () => {
                        Promise.all([...selected].map(code => patchStock(code, { group_ids: [] }))).then(() => {
                          message.success('已清除分组')
                          onClear()
                          qc.invalidateQueries({ queryKey: ['signals-today'] })
                          qc.invalidateQueries({ queryKey: ['groups'] })
                        })
                      }},
                    ],
                  }}
                  trigger={['click']}
                  placement="bottomRight"
                >
                  <div style={{ padding: '7px 14px', cursor: 'pointer', fontSize: 14, color: '#374151', transition: 'background 0.1s' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f9fafb')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    <FolderOutlined style={{ marginRight: 6 }} />移组
                  </div>
                </Dropdown>
              }
            />
            <NavItem icon={<SyncOutlined />} label="同步" onClick={() => {
              Promise.all([...selected].map(code => syncSingleStock(code))).then(() => {
                message.success(`${selected.size} 只同步完成`)
                onClear()
                qc.invalidateQueries({ queryKey: ['signals-today'] })
              })
            }} />
            <NavItem icon={<ExperimentOutlined />} label="AI 分析" onClick={() => onBatchStart('ai')} />
            <NavItem icon={<ThunderboltOutlined />} label="操作指示" onClick={() => onBatchStart('action_plan')} />
            <div style={{ borderTop: '1px solid #f0f0f0', margin: '4px 0' }} />
            <NavItem icon={<DeleteOutlined />} label="移除" danger onClick={() => {
              Modal.confirm({
                title: `批量移除 ${selected.size} 只自选？`,
                okText: '移除',
                okButtonProps: { danger: true },
                onOk: () => {
                  Promise.all([...selected].map(code => removeWatchlist(code))).then(() => {
                    message.success(`已移除 ${selected.size} 只`)
                    onClear()
                    qc.invalidateQueries({ queryKey: ['signals-today'] })
                    qc.invalidateQueries({ queryKey: ['groups'] })
                  })
                },
              })
            }} />
            <NavItem label="取消" muted onClick={onClear} />
          </>
        )}
      </div>
    </div>
  )
}

function NavItem({ icon, label, onClick, danger, muted }: {
  icon?: React.ReactNode
  label: string
  onClick: () => void
  danger?: boolean
  muted?: boolean
}) {
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

function ActionItem({ label, dropdown }: { label: string; dropdown: React.ReactNode }) {
  return <>{dropdown}</>
}
