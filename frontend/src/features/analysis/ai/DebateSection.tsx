import { Space, Tag, Typography } from 'antd'
import { DebaterView, JudgeView } from '@/api/analysis'
import { verdictPalette } from '@/shared/theme'

const { Title, Text } = Typography

function DebaterCard({ view, side }: { view: DebaterView | null | undefined; side: 'bull' | 'bear' }) {
  if (!view) return null
  const p = side === 'bull' ? verdictPalette.bullish : verdictPalette.bearish
  const label = side === 'bull' ? '牛派' : '熊派'
  const emoji = side === 'bull' ? '🐂' : '🐻'
  return (
    <div
      style={{
        border: `1px solid ${p.border}`,
        background: p.bg,
        borderRadius: 8,
        padding: '12px 14px',
      }}
    >
      <Space align="baseline" style={{ marginBottom: 8 }}>
        <Text strong style={{ fontSize: 15, color: p.color }}>
          {emoji} {label}观点
        </Text>
        {typeof view.confidence === 'number' && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            置信度 {(view.confidence * 100).toFixed(0)}%
          </Text>
        )}
      </Space>
      {view.thesis && (
        <div style={{ fontSize: 14, color: '#1f2937', marginBottom: 8, fontWeight: 500 }}>
          {view.thesis}
        </div>
      )}
      {view.arguments && view.arguments.length > 0 && (
        <ul style={{ margin: '4px 0 8px 20px', padding: 0, color: '#374151', fontSize: 13 }}>
          {view.arguments.map((a, i) => {
            // 兼容新格式 {claim, failure_mode} 和旧格式 string
            const claim = typeof a === 'string' ? a : a?.claim || ''
            const failureMode = typeof a === 'object' && a?.failure_mode ? a.failure_mode : null
            return (
              <li key={i} style={{ marginBottom: 4 }}>
                {claim}
                {failureMode && (
                  <span style={{ color: '#9ca3af', fontSize: 11, marginLeft: 6 }}>
                    ⚡失效条件：{failureMode}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {view.concessions && view.concessions.length > 0 && (
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
          <Text type="secondary">让步：</Text>
          {view.concessions.join('；')}
        </div>
      )}
      {view.invalidation && (
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
          <Text type="secondary">推翻条件：</Text>
          {view.invalidation}
        </div>
      )}
    </div>
  )
}

function JudgeCard({ judge }: { judge: JudgeView | null | undefined }) {
  if (!judge) return null
  const winsLabel: Record<string, string> = {
    bull: '牛派更有理',
    bear: '熊派更有理',
    draw: '势均力敌',
  }
  return (
    <div
      style={{
        border: '1px solid #d1d5db',
        background: '#f9fafb',
        borderRadius: 8,
        padding: '12px 14px',
      }}
    >
      <Space align="baseline" style={{ marginBottom: 8 }}>
        <Text strong style={{ fontSize: 15 }}>⚖️ 裁判</Text>
        {judge.who_wins && <Tag>{winsLabel[judge.who_wins] || judge.who_wins}</Tag>}
      </Space>
      {judge.verdict_reasoning && (
        <div style={{ fontSize: 13, color: '#374151', marginBottom: 10, lineHeight: 1.6 }}>
          {judge.verdict_reasoning}
        </div>
      )}
      {judge.consensus && judge.consensus.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          <Text strong style={{ fontSize: 12 }}>共识：</Text>
          {judge.consensus.map((s, i) => (
            <Tag key={i} color="default" style={{ marginBottom: 2 }}>
              {s}
            </Tag>
          ))}
        </div>
      )}
      {judge.disputes && judge.disputes.length > 0 && (
        <div>
          <Text strong style={{ fontSize: 12 }}>分歧：</Text>
          {judge.disputes.map((s, i) => (
            <Tag key={i} color="warning" style={{ marginBottom: 2 }}>
              {s}
            </Tag>
          ))}
        </div>
      )}
    </div>
  )
}

interface Props {
  bull?: DebaterView | null
  bear?: DebaterView | null
  judge?: JudgeView | null
}

export function DebateSection({ bull, bear, judge }: Props) {
  if (!bull && !bear) return null
  return (
    <div>
      <Title level={5} style={{ margin: '0 0 10px' }}>
        牛熊辩论
      </Title>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <DebaterCard view={bull} side="bull" />
          <DebaterCard view={bear} side="bear" />
        </div>
        <JudgeCard judge={judge} />
      </Space>
    </div>
  )
}
