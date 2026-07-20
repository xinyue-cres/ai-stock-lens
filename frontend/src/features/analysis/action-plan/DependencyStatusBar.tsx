import { Alert, Button, Space, Tag, Tooltip, Typography } from 'antd'
import {
  CheckCircleFilled,
  CloseCircleOutlined,
  ExclamationCircleFilled,
  ReloadOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getActionPlanDeps } from '@/api/actionPlan'
import { generateAiReport } from '@/api/analysis'
import { useStock } from '@/features/stock-context'

const { Text } = Typography

type Horizon = 'combined' | 'anti_quant' | 'reflexivity'

const horizonLabel: Record<Horizon, string> = {
  combined: '综合',
  anti_quant: '反量',
  reflexivity: '反身',
}

/**
 * ActionPlanPanel 顶部常驻的依赖状态栏。
 * - 数据：K 线 as_of + 是否已收盘
 * - AI 分析：每个 horizon 就绪 ✅ / 缺失 ⚠️ / 过期 🕒
 * - 缺失/过期 → 就地"生成"按钮，直接 mutate 对应 horizon
 */
export function DependencyStatusBar() {
  const qc = useQueryClient()
  const { code } = useStock()

  const depsQ = useQuery({
    queryKey: ['action-plan-deps', code],
    queryFn: () => getActionPlanDeps(code),
    enabled: !!code,
    refetchOnWindowFocus: false,
  })

  const genMut = useMutation({
    mutationFn: (h: Horizon) => generateAiReport(code, { horizon: h, force: true }),
    onSuccess: (_, h) => {
      qc.invalidateQueries({ queryKey: ['action-plan-deps', code] })
      qc.invalidateQueries({ queryKey: ['ai-report-cached', code, h] })
    },
  })

  if (!depsQ.data || depsQ.data.empty) return null

  const { kline, reports, warnings, position_dirty } = depsQ.data
  const pendingHorizon = genMut.isPending ? (genMut.variables as Horizon) : null

  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 6,
        padding: '8px 14px',
        background: '#fafafa',
      }}
    >
      <Space size={12} wrap style={{ width: '100%' }}>
        {/* 数据状态 */}
        {kline.empty ? (
          <Tag color="error" icon={<CloseCircleOutlined />}>
            无 K 线数据
          </Tag>
        ) : (
          <Tag
            icon={<CheckCircleFilled />}
            color={kline.finalized ? 'success' : 'warning'}
            style={{ margin: 0 }}
          >
            {kline.as_of} · {kline.finalized ? '已收盘' : '仅盘中'}
          </Tag>
        )}
        {position_dirty && (
          <Tooltip title="持仓修改晚于最近一次操作指示生成时间，建议点右上「强制刷新」重新合成建议">
            <Tag
              icon={<ExclamationCircleFilled />}
              color="warning"
              style={{ margin: 0 }}
            >
              持仓已变更
            </Tag>
          </Tooltip>
        )}

        {/* AI 分析状态 */}
        {(Object.keys(horizonLabel) as Horizon[]).map((h) => {
          const r = reports[h]
          const label = horizonLabel[h]
          if (!r) {
            return (
              <Space key={h} size={2}>
                <Tag icon={<CloseCircleOutlined />} color="default" style={{ margin: 0 }}>
                  {label} · 未生成
                </Tag>
                <Button
                  size="small"
                  type="link"
                  icon={<ReloadOutlined />}
                  loading={pendingHorizon === h}
                  onClick={() => genMut.mutate(h)}
                  style={{ padding: '0 4px', fontSize: 12 }}
                >
                  生成
                </Button>
              </Space>
            )
          }
          if (r.stale) {
            return (
              <Space key={h} size={2}>
                <Tooltip title={`报告 ${r.as_of} · 已落后 ${r.trading_days_behind} 交易日`}>
                  <Tag
                    icon={<ExclamationCircleFilled />}
                    color="warning"
                    style={{ margin: 0 }}
                  >
                    {label} · 过期
                  </Tag>
                </Tooltip>
                <Button
                  size="small"
                  type="link"
                  icon={<ReloadOutlined />}
                  loading={pendingHorizon === h}
                  onClick={() => genMut.mutate(h)}
                  style={{ padding: '0 4px', fontSize: 12 }}
                >
                  刷新
                </Button>
              </Space>
            )
          }
          return (
            <Tooltip key={h} title={`报告 ${r.as_of} · verdict=${r.verdict}`}>
              <Tag icon={<CheckCircleFilled />} color="success" style={{ margin: 0 }}>
                {label}
              </Tag>
            </Tooltip>
          )
        })}
      </Space>

      {warnings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 8, padding: '4px 10px', fontSize: 12 }}
          message={
            <Text style={{ fontSize: 12 }}>
              当前建议基于不完整输入：{warnings.join('、')}
            </Text>
          }
        />
      )}
    </div>
  )
}
