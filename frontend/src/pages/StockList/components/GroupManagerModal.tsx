import { useEffect, useRef, useState } from 'react'
import { Button, Input, Modal, Space, Typography } from 'antd'
import { DeleteOutlined, EditOutlined } from '@ant-design/icons'
import { createGroup, deleteGroup, updateGroup, StockGroup } from '@/api/groups'

const { Text } = Typography

interface GroupManagerModalProps {
  open: boolean
  groups: StockGroup[]
  onClose: () => void
  onChange: () => void
}

export default function GroupManagerModal({ open, groups, onClose, onChange }: GroupManagerModalProps) {
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editingName, setEditingName] = useState('')
  // 本地排序列表（支持拖动），随外部 groups 同步
  const [list, setList] = useState<StockGroup[]>(groups)
  const dragIndex = useRef<number | null>(null)

  useEffect(() => {
    setList(groups)
  }, [groups])

  const handleAdd = async () => {
    const name = newName.trim()
    if (!name) return
    await createGroup(name, list.length)
    setNewName('')
    onChange()
  }

  const handleRename = async (id: number) => {
    const name = editingName.trim()
    if (!name) return
    await updateGroup(id, { name })
    setEditingId(null)
    onChange()
  }

  const handleDelete = async (id: number, name: string) => {
    Modal.confirm({
      title: `删除分组「${name}」？`,
      content: '组内股票将变为未分组，不会从自选中移除。',
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteGroup(id)
        onChange()
      },
    })
  }

  // 拖动排序：本地重排 + 按新顺序写回 sort_order（0,1,2...）
  const handleDrop = async (targetIndex: number) => {
    const from = dragIndex.current
    dragIndex.current = null
    if (from === null || from === targetIndex) return
    const arr = [...list]
    const [moved] = arr.splice(from, 1)
    arr.splice(targetIndex, 0, moved)
    setList(arr)
    await Promise.all(
      arr.map((g, i) => (g.sort_order !== i ? updateGroup(g.id, { sort_order: i }) : null)),
    )
    onChange()
  }

  return (
    <Modal title="管理分组" open={open} onCancel={onClose} footer={null} width={360}>
      <div style={{ marginBottom: 12 }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder="新分组名称"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onPressEnter={handleAdd}
          />
          <Button type="primary" onClick={handleAdd} disabled={!newName.trim()}>添加</Button>
        </Space.Compact>
      </div>
      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
        按住拖动分组可排序
      </Text>
      <div>
        {list.map((g, i) => (
          <div
            key={g.id}
            draggable
            onDragStart={() => { dragIndex.current = i }}
            onDragOver={e => e.preventDefault()}
            onDrop={() => handleDrop(i)}
            onDragEnd={() => { dragIndex.current = null }}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0',
              borderBottom: '1px solid #f5f5f5', cursor: 'grab',
            }}
          >
            {editingId === g.id ? (
              <Input
                size="small"
                autoFocus
                value={editingName}
                onChange={e => setEditingName(e.target.value)}
                onPressEnter={() => handleRename(g.id)}
                onBlur={() => setEditingId(null)}
                style={{ flex: 1 }}
              />
            ) : (
              <span style={{ flex: 1, fontSize: 13 }}>{g.name} <Text type="secondary" style={{ fontSize: 11 }}>({g.stock_count})</Text></span>
            )}
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => { setEditingId(g.id); setEditingName(g.name) }}
            />
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(g.id, g.name)}
            />
          </div>
        ))}
        {list.length === 0 && (
          <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: '16px 0' }}>
            还没有分组
          </Text>
        )}
      </div>
    </Modal>
  )
}
