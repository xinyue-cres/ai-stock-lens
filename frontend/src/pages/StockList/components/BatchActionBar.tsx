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
      position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
      background: '#1f2937', color: '#fff', borderRadius: 8, padding: '10px 20px',
      display: 'flex', alignItems: 'center', gap: 12, boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
      zIndex: 100,
    }}>
      <Text style={{ color: '#fff', fontSize: 13 }}>
        {batchRunning ? `处理中 ${batchCompleted}/${batchTotal}` : `已选 ${selected.size} 只`}
      </Text>
      {!batchRunning && (
        <>
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
          >
            <Button size="small" ghost icon={<FolderOutlined />}>移组</Button>
          </Dropdown>
          <Button size="small" ghost icon={<SyncOutlined />} onClick={() => {
            Promise.all([...selected].map(code => syncSingleStock(code))).then(() => {
              message.success(`${selected.size} 只同步完成`)
              onClear()
              qc.invalidateQueries({ queryKey: ['signals-today'] })
            })
          }}>同步</Button>
          <Button
            size="small"
            ghost
            icon={<ExperimentOutlined />}
            onClick={() => onBatchStart('ai')}
          >
            AI 分析
          </Button>
          <Button
            size="small"
            ghost
            icon={<ThunderboltOutlined />}
            onClick={() => onBatchStart('action_plan')}
          >
            操作指示
          </Button>
          <Button size="small" ghost danger icon={<DeleteOutlined />} onClick={() => {
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
          }}>移除</Button>
          <Button size="small" type="text" style={{ color: '#9ca3af' }} onClick={onClear}>取消</Button>
        </>
      )}
    </div>
  )
}
