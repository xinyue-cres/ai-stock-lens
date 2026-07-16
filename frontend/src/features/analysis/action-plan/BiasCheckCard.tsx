import { Space, Tag, Typography } from 'antd'
import { StopOutlined } from '@ant-design/icons'
import { BiasCheck, BiasType } from '@/api/actionPlan'

const { Text, Title } = Typography

const biasFallbackLabel: Record<BiasType, string> = {
  anchoring: '锚定效应',
  endowment: '禀赋效应',
  disposition: '处置效应',
  confirmation: '确认偏误',
  recency: '近因效应',
  availability: '可得性偏误',
  loss_aversion: '损失厌恶',
  overconfidence: '过度自信',
  herding: '从众效应',
  sunk_cost: '沉没成本',
}

interface Props {
  checks?: BiasCheck[]
}

/**
 * 展示 Trader 输出的"当前禁止事项"——基于当前走势和持仓，
 * 纪律性约束，放在动作清单之前，防止冲动操作。
 */
export function BiasCheckSection({ checks }: Props) {
  if (!checks || checks.length === 0) return null

  return (
    <div>
      <Title level={5} style={{ marginBottom: 8, fontSize: 14 }}>
        <StopOutlined style={{ color: '#dc2626', marginRight: 6 }} />
        当前禁止事项（{checks.length} 条）
      </Title>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        {checks.map((b, i) => (
          <BiasCheckCard key={i} check={b} />
        ))}
      </Space>
    </div>
  )
}

function BiasCheckCard({ check }: { check: BiasCheck }) {
  const label = check.label || biasFallbackLabel[check.bias] || check.bias
  const command = check.command || check.do_not || ''
  const invalidation = check.invalidation || ''
  const isProhibit = command.startsWith('禁止')

  return (
    <Space align="baseline" size={8} style={{ width: '100%' }}>
      <Tag
        color={isProhibit ? 'red' : 'blue'}
        style={{ margin: 0, fontWeight: 600, flexShrink: 0 }}
      >
        {label}
      </Tag>
      <Text style={{ fontSize: 13, fontWeight: 500 }}>
        {command}
        {invalidation && (
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
            （{invalidation}）
          </Text>
        )}
      </Text>
    </Space>
  )
}
