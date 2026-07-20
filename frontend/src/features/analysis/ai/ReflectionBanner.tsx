import { Typography } from 'antd'
import { InfoCircleOutlined } from '@ant-design/icons'

const { Text } = Typography

interface Props {
  reflection?: string | null
}

export function ReflectionBanner({ reflection }: Props) {
  if (!reflection) return null
  return (
    <div style={{ display: 'flex', gap: 6, padding: '6px 10px', background: '#f0f9ff', borderRadius: 4, border: '1px solid #bae6fd', alignItems: 'baseline' }}>
      <InfoCircleOutlined style={{ color: '#0ea5e9', fontSize: 12, flexShrink: 0, marginTop: 2 }} />
      <div>
        <Text strong style={{ fontSize: 11, color: '#0369a1' }}>回顾修正</Text>
        <Text style={{ fontSize: 12, color: '#475569', marginLeft: 6 }}>{reflection}</Text>
      </div>
    </div>
  )
}
