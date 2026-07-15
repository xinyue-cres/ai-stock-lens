import { Button, Dropdown, Modal } from 'antd'
import type { MenuProps } from 'antd'
import {
  DeleteOutlined,
  DollarOutlined,
  ExclamationCircleFilled,
  MoreOutlined,
  PushpinFilled,
  PushpinOutlined,
} from '@ant-design/icons'
import { SignalItem } from '@/api/signals'
import { accent } from '@/shared/theme'

interface Props {
  item: SignalItem
  open: boolean
  onOpenChange: (open: boolean) => void
  onPin: (code: string, pinned: boolean) => void
  onRemove: (code: string) => void
  onEditPosition: (code: string) => void
}

/**
 * item 右下角的 ⋯ 菜单：编辑持仓 / 置顶 / 移除。
 */
export function ItemActionMenu({ item, open, onOpenChange, onPin, onRemove, onEditPosition }: Props) {
  const menu: MenuProps['items'] = [
    {
      key: 'position',
      icon: <DollarOutlined style={{ color: '#7c3aed' }} />,
      label: item.position ? '编辑持仓' : '录入持仓',
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation()
        onOpenChange(false)
        onEditPosition(item.code)
      },
    },
    {
      key: 'pin',
      icon: item.pinned ? <PushpinFilled style={{ color: accent.pin }} /> : <PushpinOutlined />,
      label: item.pinned ? '取消置顶' : '置顶',
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation()
        onPin(item.code, !item.pinned)
        onOpenChange(false)
      },
    },
    { type: 'divider' },
    {
      key: 'remove',
      icon: <DeleteOutlined />,
      danger: true,
      label: '移除',
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation()
        onOpenChange(false)
        Modal.confirm({
          title: '移除自选？',
          icon: <ExclamationCircleFilled style={{ color: '#dc2626' }} />,
          content: `将从自选中移除 ${item.name || item.code}`,
          okText: '移除',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: () => onRemove(item.code),
        })
      },
    },
  ]

  return (
    <Dropdown menu={{ items: menu }} trigger={['click']} open={open} onOpenChange={onOpenChange} placement="bottomRight">
      <Button
        type="text"
        size="small"
        icon={<MoreOutlined style={{ fontSize: 16 }} />}
        onClick={(e) => {
          e.stopPropagation()
          onOpenChange(!open)
        }}
        style={{
          width: 24,
          height: 22,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: open ? accent.active : accent.mute,
        }}
      />
    </Dropdown>
  )
}
