import { Space, Tag, Typography } from 'antd'

const { Text } = Typography

interface Props {
  signals?: string[]
  risks?: string[]
}

/** 关键信号 + 风险提示两个 tag 列表（共 0-2 行）。 */
export function SignalsAndRisks({ signals, risks }: Props) {
  const hasSignals = signals && signals.length > 0
  const hasRisks = risks && risks.length > 0
  if (!hasSignals && !hasRisks) return null

  return (
    <Space direction="vertical" size={10} style={{ width: '100%' }}>
      {hasSignals && (
        <div>
          <Text strong style={{ marginRight: 8 }}>关键信号</Text>
          {signals!.map((s, i) => (
            <Tag color="processing" key={i}>{s}</Tag>
          ))}
        </div>
      )}
      {hasRisks && (
        <div>
          <Text strong style={{ marginRight: 8 }}>风险提示</Text>
          {risks!.map((s, i) => (
            <Tag color="warning" key={i}>{s}</Tag>
          ))}
        </div>
      )}
    </Space>
  )
}
