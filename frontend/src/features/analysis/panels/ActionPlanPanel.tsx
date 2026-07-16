import { Alert, Button, Card, Empty, Space, Spin, Typography } from 'antd'
import { AimOutlined, ReloadOutlined } from '@ant-design/icons'
import { useStock, useStockName } from '@/features/stock-context'
import { timeAgo } from '@/shared/timeAgo'
import { ActionCard, ConflictsSection, stanceLabel } from '../action-plan/ActionCard'
import { BiasCheckSection } from '../action-plan/BiasCheckCard'
import { DependencyStatusBar } from '../action-plan/DependencyStatusBar'
import { useActionPlan } from '../action-plan/useActionPlan'

const { Title, Text } = Typography

/**
 * 操作指示（Trader）面板：把 4 份分析 + 当前指标 + 用户持仓 压成一份可执行清单。
 */
export function ActionPlanPanel() {
  const { code } = useStock()
  const name = useStockName()
  const { data, loading, isPending, isError, error, generate, forceRegenerate, isCachedOnly } =
    useActionPlan()

  const stance = data?.overall_stance ? stanceLabel[data.overall_stance] : null

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
              <AimOutlined style={{ color: '#7c3aed', marginRight: 8 }} />
              操作指示 · Trader
            </Title>
            {name && (
              <Text type="secondary" style={{ fontSize: 15 }}>
                {name}（{code}）
              </Text>
            )}
            {data?.as_of_date && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {timeAgo(data.created_at) || `截至 ${data.as_of_date}`}
              </Text>
            )}
            {isCachedOnly && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                · 缓存
              </Text>
            )}
          </Space>
          <Space>
            <Button type="primary" loading={isPending} onClick={generate}>
              {data && !data.empty ? '刷新' : '生成清单'}
            </Button>
            {data && !data.empty && (
              <Button icon={<ReloadOutlined />} loading={isPending} onClick={forceRegenerate}>
                强制刷新
              </Button>
            )}
          </Space>
        </Space>

        <DependencyStatusBar />

        {!data && loading && (
          <div style={{ textAlign: 'center', padding: '32px 0' }}>
            <Spin size="large" tip={isPending ? 'Trader 正在整合各视角…' : '加载缓存…'} />
          </div>
        )}

        {!data && !loading && (
          <Empty
            description="尚未生成操作清单，点击右上「生成清单」（需先至少生成一份分析）"
            style={{ padding: '32px 0' }}
          />
        )}

        {isError && (
          <Alert
            type="error"
            showIcon
            message={(error as any)?.response?.data?.detail || '生成失败'}
          />
        )}

        {data && !data.empty && (
          <>
            {stance && (
              <div
                style={{
                  padding: '10px 14px',
                  background: stance.bg,
                  border: `1px solid ${stance.color}`,
                  borderRadius: 6,
                }}
              >
                <Space align="baseline" size={12} wrap>
                  <span
                    style={{
                      background: stance.color,
                      color: '#fff',
                      padding: '2px 10px',
                      borderRadius: 4,
                      fontSize: 13,
                      fontWeight: 600,
                    }}
                  >
                    {stance.label}
                  </span>
                  {data.summary && <Text style={{ fontSize: 14 }}>{data.summary}</Text>}
                </Space>
              </div>
            )}

            {data.position_advice && (
              <Alert
                type="info"
                message="持仓建议"
                description={data.position_advice}
                showIcon
                style={{ background: '#f5f3ff', borderColor: '#c4b5fd' }}
              />
            )}

            <ConflictsSection conflicts={data.conflicts || []} />

            {data.actions && data.actions.length > 0 && (
              <div>
                <Title level={5} style={{ marginBottom: 8, fontSize: 14 }}>
                  动作清单（按优先级）
                </Title>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  {data.actions.map((a, i) => (
                    <ActionCard key={i} action={a} />
                  ))}
                </Space>
              </div>
            )}

            <BiasCheckSection checks={data.bias_checks} />

            <Text type="secondary" style={{ fontSize: 12 }}>
              以上仅为技术面数据合成的建议，非投资意见，据此操作风险自负。
            </Text>
          </>
        )}
      </Space>
    </Card>
  )
}
