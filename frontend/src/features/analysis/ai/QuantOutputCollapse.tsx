import { Descriptions, Space, Tag, Typography } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import { QuantOutput } from '@/api/analysis'

const { Text } = Typography

interface Props {
  data?: QuantOutput | null
}

const biasLabel: Record<string, { label: string; color: string }> = {
  long_biased: { label: '偏多', color: 'red' },
  short_biased: { label: '偏空', color: 'green' },
  neutral: { label: '中性', color: 'default' },
  long_gamma: { label: 'Long γ', color: 'purple' },
  short_gamma: { label: 'Short γ', color: 'volcano' },
}

const pressureLabel: Record<string, { label: string; color: string }> = {
  buying: { label: '买盘压力', color: 'red' },
  selling: { label: '卖盘压力', color: 'green' },
  mixed: { label: '双向对峙', color: 'gold' },
  thin: { label: '流动性稀薄', color: 'default' },
}

export function QuantOutputCollapse({ data }: Props) {
  if (!data) return null
  const bias = data.positioning_bias ? biasLabel[data.positioning_bias] : null
  const pressure = data.next_5d_pressure ? pressureLabel[data.next_5d_pressure] : null

  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <ExperimentOutlined style={{ color: '#7c3aed' }} />
        <Text strong style={{ fontSize: 13 }}>量化机构视角推理</Text>
      </Space>

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space wrap>
          {bias && <Tag color={bias.color}>整体持仓偏向：{bias.label}</Tag>}
          {pressure && <Tag color={pressure.color}>未来 5 日：{pressure.label}</Tag>}
        </Space>

        {data.reasoning && (
          <Text type="secondary" style={{ display: 'block' }}>
            {data.reasoning}
          </Text>
        )}

        {data.key_factors && data.key_factors.length > 0 && (
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              关键因子：
            </Text>
            <Space wrap size={[4, 4]} style={{ marginTop: 4 }}>
              {data.key_factors.map((f, i) => (
                <Tag key={i} style={{ fontSize: 12 }}>
                  {f}
                </Tag>
              ))}
            </Space>
          </div>
        )}

        {data.quant_flows && data.quant_flows.length > 0 && (
          <Descriptions
            bordered
            column={1}
            size="small"
            title={<Text style={{ fontSize: 13 }}>预期资金动作</Text>}
          >
            {data.quant_flows.map((flow, i) => (
              <Descriptions.Item
                key={i}
                label={
                  <Space direction="vertical" size={2}>
                    <Tag color="geekblue" style={{ margin: 0 }}>
                      {flow.type}
                    </Tag>
                    {typeof flow.probability === 'number' && (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        概率 {(flow.probability * 100).toFixed(0)}%
                      </Text>
                    )}
                  </Space>
                }
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  {flow.trigger && <Text>{flow.trigger}</Text>}
                  <Space size={12} wrap>
                    {flow.size_hint && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        规模：{flow.size_hint}
                      </Text>
                    )}
                    {typeof flow.expected_horizon_days === 'number' && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        周期：{flow.expected_horizon_days} 日
                      </Text>
                    )}
                  </Space>
                </Space>
              </Descriptions.Item>
            ))}
          </Descriptions>
        )}
      </Space>
    </div>
  )
}
