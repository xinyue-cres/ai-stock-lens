import { Card, Space, Typography } from 'antd'
import { LineChartOutlined } from '@ant-design/icons'
import { useStock, useStockName } from '@/features/stock-context'
import { KLineChart } from '../kline/KLineChart'

const { Title, Text } = Typography

export function KLinePanel() {
  const { code } = useStock()
  const name = useStockName()

  return (
    <Card styles={{ body: { padding: 20 } }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space align="baseline" size={12} wrap>
          <Title level={5} style={{ margin: 0 }}>
            <LineChartOutlined style={{ color: '#7c3aed', marginRight: 8 }} />
            K 线
          </Title>
          {name && (
            <Text type="secondary" style={{ fontSize: 15 }}>
              {name}（{code}）
            </Text>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>
            前复权 · 量单位「手」
          </Text>
        </Space>

        <KLineChart />
      </Space>
    </Card>
  )
}
