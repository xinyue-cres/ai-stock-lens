import { Button, Card, Space, Tabs, Typography, message } from 'antd'
import { RobotOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useMutation, useIsMutating } from '@tanstack/react-query'
import { generateAiReport } from '@/api/analysis'
import { useStock, useStockAnalysis, useStockName } from '@/features/stock-context'
import { Horizon, aiReportMutationKey } from '@/features/analysis/hooks/useAiReport'
import { useInvalidation } from '@/hooks/useInvalidation'
import { StaleDateBadge } from '@/features/status-bar'
import { HorizonReport } from '../ai/HorizonReport'

const { Title, Text } = Typography

const ALL_HORIZONS: Horizon[] = ['combined', 'anti_quant', 'reflexivity', 'mean_reversion']

export function AiReportPanel() {
  const { code } = useStock()
  const name = useStockName()
  const kline = useStockAnalysis()
  const asOf = (kline.data as any)?.indicators?.as_of_date || null
  const globalInv = useInvalidation()

  const genCombined = useMutation({
    mutationKey: aiReportMutationKey(code, 'combined'),
    mutationFn: () => generateAiReport(code, { horizon: 'combined', force: true }),
    onSuccess: () => globalInv.afterAiReport(code, 'combined'),
  })
  const genAntiQuant = useMutation({
    mutationKey: aiReportMutationKey(code, 'anti_quant'),
    mutationFn: () => generateAiReport(code, { horizon: 'anti_quant', force: true }),
    onSuccess: () => globalInv.afterAiReport(code, 'anti_quant'),
  })
  const genReflexivity = useMutation({
    mutationKey: aiReportMutationKey(code, 'reflexivity'),
    mutationFn: () => generateAiReport(code, { horizon: 'reflexivity', force: true }),
    onSuccess: () => globalInv.afterAiReport(code, 'reflexivity'),
  })
  const genMeanReversion = useMutation({
    mutationKey: aiReportMutationKey(code, 'mean_reversion'),
    mutationFn: () => generateAiReport(code, { horizon: 'mean_reversion', force: true }),
    onSuccess: () => globalInv.afterAiReport(code, 'mean_reversion'),
  })

  const anyPending = useIsMutating({
    predicate: (m) => {
      const key = m.options.mutationKey as readonly unknown[] | undefined
      return !!key && key[0] === 'gen-ai-report' && key[1] === code
    },
  })

  const handleGenAll = () => {
    genCombined.mutate()
    genAntiQuant.mutate()
    genReflexivity.mutate()
    genMeanReversion.mutate()
  }

  return (
    <Card styles={{ body: { padding: 20 } }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space
          align="baseline"
          size={12}
          wrap
          style={{ justifyContent: 'space-between', width: '100%' }}
        >
          <Space align="baseline" size={12} wrap>
            <Title level={5} style={{ margin: 0 }}>
              <RobotOutlined style={{ color: '#7c3aed', marginRight: 8 }} />
              AI 技术分析
            </Title>
            {name && (
              <Text type="secondary" style={{ fontSize: 15 }}>
                {name}（{code}）
              </Text>
            )}
            <StaleDateBadge asOf={asOf} />
          </Space>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={anyPending > 0}
            onClick={handleGenAll}
          >
            {anyPending > 0 ? '生成中…' : '一键全生成'}
          </Button>
        </Space>

        <Tabs
          defaultActiveKey="combined"
          size="middle"
          items={[
            {
              key: 'combined',
              label: '综合分析',
              children: <HorizonReport horizon="combined" />,
            },
            {
              key: 'anti_quant',
              label: '量化视角',
              children: <HorizonReport horizon="anti_quant" />,
            },
            {
              key: 'reflexivity',
              label: '反身视角',
              children: <HorizonReport horizon="reflexivity" />,
            },
            {
              key: 'mean_reversion',
              label: '左侧机会',
              children: <HorizonReport horizon="mean_reversion" />,
            },
          ]}
        />

        <Text type="secondary" style={{ fontSize: 12 }}>
          以上为 AI 基于技术数据的分析，非投资建议，据此操作风险自负。
        </Text>
      </Space>
    </Card>
  )
}
