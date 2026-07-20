import { Alert, Button, Empty, Space, Spin, Tag } from 'antd'
import { WarningOutlined } from '@ant-design/icons'
import { Horizon, useAiReport, useStockAnalysis } from '@/features/stock-context'
import { TrapRisk } from '@/api/analysis'
import { DebateSection } from './DebateSection'
import { QuantOutputCollapse } from './QuantOutputCollapse'
import { ReflectionBanner } from './ReflectionBanner'
import { ReflexivityCollapse } from './ReflexivityCollapse'
import { SignalsAndRisks } from './SignalsAndRisks'
import { VerdictBanner } from './VerdictBanner'

interface Props {
  horizon: Horizon
}

const horizonEmpty: Record<Horizon, string> = {
  combined: '综合',
  anti_quant: '反量',
  reflexivity: '反身',
}

const antiQuantHint: Record<string, string> = {
  neutral: '未发现拥挤风险，可顺势跟随',
  caution: '存在拥挤迹象，注意风控',
  bearish: '多头拥挤严重，警惕反转',
  bullish: '空头拥挤，反弹概率较高',
}

/** 单一视角报告：拿 hook 拿状态，组合展示子块。 */
export function HorizonReport({ horizon }: Props) {
  const { data, loading, isPending, isError, error, generate, forceRegenerate, isCachedOnly, horizonMismatch } =
    useAiReport(horizon)
  const kline = useStockAnalysis()
  const dataAsOf = (kline.data as any)?.indicators?.as_of_date || null

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* 操作栏 + verdict 同行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {data && (
            <VerdictBanner
              data={data}
              showCachedTag={isCachedOnly}
              dataAsOf={dataAsOf}
              hint={horizon === 'anti_quant' ? antiQuantHint[data.verdict] : undefined}
            />
          )}
        </div>
        <Space size={8} style={{ flexShrink: 0 }}>
          <Button type="primary" loading={isPending} onClick={generate}>
            {data ? '刷新分析' : '生成分析'}
          </Button>
          {data && (
            <Button loading={isPending} onClick={forceRegenerate}>
              强制刷新
            </Button>
          )}
        </Space>
      </div>

      {horizonMismatch && !data && (
        <Alert
          type="warning"
          showIcon
          message={`后端返回的报告类型与当前 Tab（${horizonEmpty[horizon]}）不一致，可能后端服务未重启加载新代码，请重启后端后再试。`}
        />
      )}

      {!data && !loading && (
        <Empty
          description={`当天暂无${horizonEmpty[horizon]}报告，点击「生成分析」`}
          style={{ padding: '32px 0' }}
        />
      )}

      {loading && !data && (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin size="large" tip={isPending ? 'AI 正在分析…' : '加载缓存…'} />
        </div>
      )}

      {isError && <Alert type="error" showIcon message={(error as any)?.message || '生成失败'} />}

      {data && (
        <>
          {data.trap_risk && data.trap_risk.type !== 'none' && (
            <TrapRiskBanner trap={data.trap_risk} />
          )}
          <ReflectionBanner reflection={data.reflection} />
          {data.quant_output && <QuantOutputCollapse data={data.quant_output} />}
          {(data.reflexivity_stage || data.narrative || data.feedback_loop) && (
            <ReflexivityCollapse
              stage={data.reflexivity_stage}
              narrative={data.narrative}
              feedbackLoop={data.feedback_loop}
            />
          )}
          <DebateSection bull={data.bull} bear={data.bear} judge={data.judge} />
          {data.evidence_review && data.evidence_review.length > 0 && (
            <EvidenceReviewTable reviews={data.evidence_review} />
          )}
          <SignalsAndRisks signals={data.key_signals} risks={data.risks} />
        </>
      )}
    </Space>
  )
}

const ratingColor: Record<string, string> = { strong: 'green', medium: 'gold', weak: 'default' }
const ratingLabel: Record<string, string> = { strong: '强', medium: '中', weak: '弱' }

function EvidenceReviewTable({ reviews }: { reviews: Array<{ side: string; claim: string; rating: string; reason: string }> }) {
  return (
    <div style={{ fontSize: 13 }}>
      {reviews.map((r, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 4 }}>
          <Tag color={r.side === 'bull' ? 'red' : 'green'} style={{ margin: 0, flexShrink: 0 }}>
            {r.side === 'bull' ? '牛' : '熊'}
          </Tag>
          <Tag color={ratingColor[r.rating]} style={{ margin: 0, flexShrink: 0 }}>
            {ratingLabel[r.rating] || r.rating}
          </Tag>
          <span>{r.claim}</span>
          {r.reason && <span style={{ color: '#9ca3af', fontSize: 12 }}>— {r.reason}</span>}
        </div>
      ))}
    </div>
  )
}

const trapTypeLabel: Record<string, string> = {
  false_breakout: '假突破风险',
  crowded_chase: '诱多拥挤',
  stop_loss_cascade: '止损踩踏',
}

const trapLevelColor: Record<string, string> = {
  low: 'default',
  medium: 'orange',
  high: 'red',
}

function TrapRiskBanner({ trap }: { trap: TrapRisk }) {
  const label = trapTypeLabel[trap.type] || trap.type
  const color = trapLevelColor[trap.level] || 'default'

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: '#fff7ed', borderRadius: 6, border: '1px solid #fed7aa' }}>
      <WarningOutlined style={{ color: '#ea580c', fontSize: 14 }} />
      <Tag color={color} style={{ margin: 0 }}>{label} · {trap.level}</Tag>
      {trap.evidence.length > 0 && (
        <span style={{ fontSize: 12, color: '#78716c' }}>
          {trap.evidence.join('；')}
        </span>
      )}
    </div>
  )
}
