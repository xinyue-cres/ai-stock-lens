import { Space, Tag, Typography } from 'antd'
import { RadarChartOutlined } from '@ant-design/icons'
import { FeedbackLoop, ReflexivityStage } from '@/api/analysis'

const { Text, Paragraph } = Typography

interface Props {
  stage?: ReflexivityStage | null
  narrative?: string | null
  feedbackLoop?: FeedbackLoop | null
}

const stageLabel: Record<ReflexivityStage, { label: string; color: string; desc: string }> = {
  self_reinforcing_up: {
    label: '上行自我强化中',
    color: 'red',
    desc: '预期 → 追买 → 涨 → 更多预期，正反馈仍在加速',
  },
  peak_exhaustion: {
    label: '顶部动能衰竭',
    color: 'orange',
    desc: '价还在但量已跟不上，叙事进入疲态',
  },
  reversal_top: {
    label: '顶部反转确立',
    color: 'volcano',
    desc: '拐点信号已出现，反馈方向即将/正在切换',
  },
  self_reinforcing_down: {
    label: '下行自我强化中',
    color: 'green',
    desc: '止损 → 抛售 → 跌 → 更多止损，负反馈加速',
  },
  capitulation: {
    label: '恐慌抛售末段',
    color: 'cyan',
    desc: '巨量、长下影、情绪极端，恐慌接近尾声',
  },
  reversal_bottom: {
    label: '底部反转确立',
    color: 'blue',
    desc: '拐点信号已出现，反馈方向即将/正在切换',
  },
  range_bound: {
    label: '无主线震荡',
    color: 'default',
    desc: '当前无明显反身性主线，多空拉锯',
  },
}

const directionTag: Record<NonNullable<FeedbackLoop['direction']>, { label: string; color: string }> = {
  positive: { label: '正反馈', color: 'red' },
  negative: { label: '负反馈', color: 'green' },
}

const strengthTag: Record<NonNullable<FeedbackLoop['strength']>, { label: string; color: string }> = {
  accelerating: { label: '加速中', color: 'red' },
  stable: { label: '稳态', color: 'blue' },
  weakening: { label: '衰竭中', color: 'orange' },
  reversing: { label: '反转中', color: 'volcano' },
}

export function ReflexivityCollapse({ stage, narrative, feedbackLoop }: Props) {
  if (!stage && !narrative && (!feedbackLoop || Object.keys(feedbackLoop).length === 0)) {
    return null
  }
  const s = stage ? stageLabel[stage] : null
  const dir = feedbackLoop?.direction ? directionTag[feedbackLoop.direction] : null
  const str = feedbackLoop?.strength ? strengthTag[feedbackLoop.strength] : null
  const evidence = feedbackLoop?.key_evidence || []

  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <RadarChartOutlined style={{ color: '#7c3aed' }} />
        <Text strong style={{ fontSize: 13 }}>反身性阶段与叙事循环</Text>
      </Space>

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {s && (
          <Space direction="vertical" size={4}>
            <Space>
              <Tag color={s.color} style={{ fontSize: 13, padding: '2px 10px' }}>
                {s.label}
              </Tag>
              {dir && <Tag color={dir.color}>{dir.label}</Tag>}
              {str && <Tag color={str.color}>{str.label}</Tag>}
            </Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {s.desc}
            </Text>
          </Space>
        )}

        {narrative && (
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              主流叙事与资金行为：
            </Text>
            <Paragraph style={{ marginTop: 4, marginBottom: 0 }}>{narrative}</Paragraph>
          </div>
        )}

        {evidence.length > 0 && (
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              反馈循环关键证据：
            </Text>
            <ul style={{ margin: '4px 0 0 0', paddingLeft: 20 }}>
              {evidence.map((e, i) => (
                <li key={i}>
                  <Text>{e}</Text>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Space>
    </div>
  )
}
