import { Tag, Tooltip } from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined } from '@ant-design/icons'

interface Props {
  finalized: boolean | null | undefined
  size?: 'small' | 'default'
}

/**
 * 已收盘/仅盘中 徽标。
 * - finalized=true → 绿色"已收盘"：这根 K 线为完整交易日
 * - finalized=false → 琥珀"仅盘中"：数据来自盘中快照，收盘/量能仍会变动
 * - undefined/null → 不渲染
 */
export function ClosedBadge({ finalized, size = 'default' }: Props) {
  if (finalized === null || finalized === undefined) return null
  const fontSize = size === 'small' ? 12 : 13
  const padding = size === 'small' ? '2px 8px' : '3px 10px'

  if (finalized) {
    return (
      <Tooltip title="该 K 线为完整交易日的收盘数据（15:00 后）">
        <Tag icon={<CheckCircleOutlined />} color="success" style={{ fontSize, padding, margin: 0 }}>
          已收盘
        </Tag>
      </Tooltip>
    )
  }
  return (
    <Tooltip title="该 K 线为盘中快照，收盘价、量能仍可能变动；15:00 收盘后再同步以获取最终数据">
      <Tag icon={<ClockCircleOutlined />} color="warning" style={{ fontSize, padding, margin: 0 }}>
        仅盘中
      </Tag>
    </Tooltip>
  )
}
