import { Card, Space, Tag, Typography } from 'antd'
import { BulbOutlined } from '@ant-design/icons'
import { BiasCheck, BiasType } from '@/api/actionPlan'

const { Text, Title } = Typography

const biasColor: Record<BiasType, string> = {
  anchoring: 'gold',
  endowment: 'purple',
  disposition: 'volcano',
  confirmation: 'geekblue',
  recency: 'cyan',
  availability: 'blue',
  loss_aversion: 'red',
  overconfidence: 'magenta',
  herding: 'green',
  sunk_cost: 'orange',
}

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
 * 展示 Trader 输出的散户易错点自查清单。piggyback 在 Trader Agent 单次调用之上，
 * 与 actions 平级但侧重心理面。放在 ActionPlanPanel 动作清单之后、免责声明之前。
 */
export function BiasCheckSection({ checks }: Props) {
  if (!checks || checks.length === 0) return null

  return (
    <div>
      <Title level={5} style={{ marginBottom: 8, fontSize: 14 }}>
        <BulbOutlined style={{ color: '#f59e0b', marginRight: 6 }} />
        散户易错点自查（{checks.length} 条）
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
  const color = biasColor[check.bias] || 'default'
  const label = check.label || biasFallbackLabel[check.bias] || check.bias
  // 兼容旧格式（trigger/counter_action）和新格式（do_not/do_instead）
  const doNot = check.do_not || (check as any).trigger || ''
  const doInstead = check.do_instead || (check as any).counter_action || ''

  return (
    <Card
      size="small"
      styles={{ body: { padding: 12 } }}
      style={{
        borderLeft: '3px solid #f59e0b',
        background: '#fffbeb',
      }}
    >
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <Space align="baseline" size={8} wrap>
          <Tag color={color} style={{ margin: 0, fontWeight: 600 }}>
            {label}
          </Tag>
        </Space>

        {doNot && (
          <div>
            <Text style={{ fontSize: 13, color: '#dc2626', fontWeight: 500 }}>
              🚫 {doNot}
            </Text>
          </div>
        )}

        {doInstead && (
          <div>
            <Text style={{ fontSize: 13, color: '#059669', fontWeight: 500 }}>
              ✅ {doInstead}
            </Text>
          </div>
        )}
      </Space>
    </Card>
  )
}
