import { Alert, Button, Empty, Space, Spin } from 'antd'
import { Horizon, useAiReport, useStockAnalysis } from '@/features/stock-context'
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
  anti_quant: '反量化',
  reflexivity: '反身性',
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
          {data && <VerdictBanner data={data} showCachedTag={isCachedOnly} dataAsOf={dataAsOf} />}
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
          <SignalsAndRisks signals={data.key_signals} risks={data.risks} />
        </>
      )}
    </Space>
  )
}
