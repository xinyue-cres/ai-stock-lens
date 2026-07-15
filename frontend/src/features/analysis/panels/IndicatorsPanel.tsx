import { Card, Collapse, Descriptions, Space, Tag, Typography } from 'antd'
import { FundOutlined } from '@ant-design/icons'
import { useStockAnalysis, useStock, useStockName } from '@/features/stock-context'

const { Title, Text } = Typography

const crossLabel: Record<string, { label: string; color: string }> = {
  golden: { label: '金叉', color: 'red' },
  death: { label: '死叉', color: 'green' },
}

const fmt = (v: unknown, d = 2) =>
  typeof v === 'number' && !Number.isNaN(v) ? v.toFixed(d) : '-'

function TagFor({
  dict,
  value,
}: {
  dict: Record<string, { label: string; color: string }>
  value?: string
}) {
  if (!value) return <Tag>-</Tag>
  const t = dict[value]
  return <Tag color={t?.color || 'default'}>{t?.label || value}</Tag>
}

export function IndicatorsPanel() {
  const { data } = useStockAnalysis()
  const { code } = useStock()
  const name = useStockName()

  if (!data || data.empty) return null
  const ind = data.indicators || {}
  const ma = ind.ma || {}
  const osc = ind.oscillators || {}
  const vol = ind.volume || {}
  const price = ind.latest_price || {}

  return (
    <Card styles={{ body: { padding: 20 } }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space align="baseline" size={12} wrap>
          <Title level={3} style={{ margin: 0 }}>
            <FundOutlined style={{ color: '#7c3aed', marginRight: 8 }} />
            技术指标详情
          </Title>
          {name && (
            <Text type="secondary" style={{ fontSize: 15 }}>
              {name}（{code}）
            </Text>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>
            截止 {ind.as_of_date}
          </Text>
        </Space>

        <Collapse
          ghost
          defaultActiveKey={['detail']}
          items={[
            {
              key: 'detail',
              label: <Text type="secondary">展开详细数值</Text>,
              children: (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Descriptions bordered column={4} size="small" title="价格与成交">
                  <Descriptions.Item label="开盘">{fmt(price.open)}</Descriptions.Item>
                  <Descriptions.Item label="最高">{fmt(price.high)}</Descriptions.Item>
                  <Descriptions.Item label="最低">{fmt(price.low)}</Descriptions.Item>
                  <Descriptions.Item label="换手率">{fmt(price.turnover)}%</Descriptions.Item>
                  <Descriptions.Item label="成交额（亿）">
                    {fmt((price.amount || 0) / 1e8)}
                  </Descriptions.Item>
                  <Descriptions.Item label="量比">{fmt(vol.vol_ratio)}</Descriptions.Item>
                </Descriptions>

                <Descriptions bordered column={4} size="small" title="均线">
                  <Descriptions.Item label="MA5">{fmt(ma.ma5)}</Descriptions.Item>
                  <Descriptions.Item label="MA10">{fmt(ma.ma10)}</Descriptions.Item>
                  <Descriptions.Item label="MA20">{fmt(ma.ma20)}</Descriptions.Item>
                  <Descriptions.Item label="MA60">{fmt(ma.ma60)}</Descriptions.Item>
                  <Descriptions.Item label="MA120">{fmt(ma.ma120)}</Descriptions.Item>
                  <Descriptions.Item label="MA250">{fmt(ma.ma250)}</Descriptions.Item>
                  <Descriptions.Item label="MA5/10">
                    {ma.ma5_ma10_cross ? (
                      <TagFor dict={crossLabel} value={ma.ma5_ma10_cross} />
                    ) : (
                      <Tag>-</Tag>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="MA5/20">
                    {ma.ma5_ma20_cross ? (
                      <TagFor dict={crossLabel} value={ma.ma5_ma20_cross} />
                    ) : (
                      <Tag>-</Tag>
                    )}
                  </Descriptions.Item>
                </Descriptions>

                <Descriptions bordered column={4} size="small" title="振荡">
                  <Descriptions.Item label="DIF">{fmt(osc.macd?.dif, 4)}</Descriptions.Item>
                  <Descriptions.Item label="DEA">{fmt(osc.macd?.dea, 4)}</Descriptions.Item>
                  <Descriptions.Item label="HIST">{fmt(osc.macd?.hist, 4)}</Descriptions.Item>
                  <Descriptions.Item label="BOLL 上/中/下">
                    {fmt(osc.boll?.upper)} / {fmt(osc.boll?.middle)} / {fmt(osc.boll?.lower)}
                  </Descriptions.Item>
                  <Descriptions.Item label="K">{fmt(osc.kdj?.k)}</Descriptions.Item>
                  <Descriptions.Item label="D">{fmt(osc.kdj?.d)}</Descriptions.Item>
                  <Descriptions.Item label="J">{fmt(osc.kdj?.j)}</Descriptions.Item>
                  <Descriptions.Item label="RSI6/12/24">
                    {fmt(osc.rsi?.rsi6)} / {fmt(osc.rsi?.rsi12)} / {fmt(osc.rsi?.rsi24)}
                  </Descriptions.Item>
                </Descriptions>
              </Space>
              ),
            },
          ]}
        />
      </Space>
    </Card>
  )
}
