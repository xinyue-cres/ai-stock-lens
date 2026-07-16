import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Empty, Space, Spin, Tag, Timeline, Tooltip, Typography, message } from 'antd'
import { HistoryOutlined, ReloadOutlined } from '@ant-design/icons'
import { useStock, useStockName } from '@/features/stock-context'
import { getDiary, refreshDiary, type DiaryReportEntry, type DiaryReviewItem } from '@/api/diary'
import { verdictPalette, priceColor, type Verdict } from '@/shared/theme'

const { Title, Text, Paragraph } = Typography

const HIT_TAG: Record<string, { color: string; label: string }> = {
  hit: { color: 'success', label: '命中' },
  miss: { color: 'error', label: '未中' },
  pending: { color: 'default', label: '观察中' },
  'n/a': { color: 'default', label: '不适用' },
}

const HORIZON_LABEL: Record<string, string> = {
  short: '短线',
  medium: '中线',
  combined: '综合',
}

function pctText(pct: number | null | undefined): { text: string; color: string } {
  if (pct == null) return { text: '-', color: '#94a3b8' }
  const sign = pct > 0 ? '+' : ''
  return {
    text: `${sign}${pct.toFixed(2)}%`,
    color: pct > 0 ? priceColor.up : pct < 0 ? priceColor.down : '#94a3b8',
  }
}

function ReviewBlock({ review }: { review: DiaryReviewItem }) {
  const { text, color } = pctText(review.price_change_pct)
  const hit = review.verdict_hit ? HIT_TAG[review.verdict_hit] : null
  return (
    <div style={{ padding: '6px 0', borderTop: '1px dashed #e5e7eb' }}>
      <Space size={8} wrap>
        <Text style={{ fontSize: 12, color: '#64748b' }}>
          T+{review.days_after} · {review.review_date}
        </Text>
        <Text style={{ fontSize: 12, color }}>{text}</Text>
        {hit && <Tag color={hit.color as any} style={{ marginRight: 0 }}>{hit.label}</Tag>}
        {review.total_scenarios > 0 && (
          <Tag>
            命中预案 {review.triggered_count}/{review.total_scenarios}
          </Tag>
        )}
      </Space>
      {review.scenarios?.some((s) => s.triggered) && (
        <ul style={{ margin: '4px 0 0 20px', padding: 0, fontSize: 12, color: '#475569' }}>
          {review.scenarios
            .filter((s) => s.triggered)
            .map((s) => (
              <li key={s.index}>{s.trigger || `#${s.index}`} · 已触发</li>
            ))}
        </ul>
      )}
    </div>
  )
}

function DiaryEntry({ entry, sameDayIndex }: { entry: DiaryReportEntry; sameDayIndex?: number }) {
  const p = verdictPalette[entry.verdict as Verdict] || verdictPalette.neutral
  const latestHit = entry.latest_verdict_hit ? HIT_TAG[entry.latest_verdict_hit] : null
  const latestPct = pctText(entry.latest_pct)
  const totalWithCond = entry.scenarios.filter((s) => s.conditions && s.conditions.length > 0).length
  const anyTriggered = entry.reviews.some((r) => r.triggered_count > 0)
  const timeLabel = entry.created_at ? new Date(entry.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }) : null

  return (
    <div>
      <Space size={8} align="baseline" wrap>
        <Text strong>{entry.as_of_date}</Text>
        {timeLabel && sameDayIndex != null && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {timeLabel}
            {sameDayIndex === 0 ? ' · 最新' : ` · 第 ${sameDayIndex + 1} 版`}
          </Text>
        )}
        <Tag>{HORIZON_LABEL[entry.horizon] || entry.horizon}</Tag>
        <Tag
          style={{
            color: p.color,
            background: p.bg,
            border: `1px solid ${p.border}`,
          }}
        >
          {p.label}
          {entry.confidence != null && ` · ${(entry.confidence * 100).toFixed(0)}%`}
        </Tag>
        {latestHit && (
          <Tooltip title="以最新一次复盘为准">
            <Tag color={latestHit.color as any}>最新：{latestHit.label}</Tag>
          </Tooltip>
        )}
        <Text style={{ fontSize: 12, color: latestPct.color }}>累计 {latestPct.text}</Text>
      </Space>
      {entry.summary && (
        <Paragraph style={{ marginTop: 6, marginBottom: 6, fontSize: 13, color: '#334155' }}>
          {entry.summary}
        </Paragraph>
      )}
      {entry.reflection && (
        <Paragraph
          style={{
            marginTop: 4,
            marginBottom: 6,
            fontSize: 12,
            color: '#0369a1',
            background: '#f0f9ff',
            border: '1px solid #bae6fd',
            borderRadius: 4,
            padding: '4px 8px',
          }}
        >
          回顾修正 · {entry.reflection}
        </Paragraph>
      )}
      {totalWithCond === 0 && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          （旧报告无结构化条件，仅按 verdict 走势判定）
        </Text>
      )}
      {(entry.reviews.length > 0 || anyTriggered) && (
        <div style={{ marginTop: 6 }}>
          {entry.reviews.map((r) => (
            <ReviewBlock key={r.review_date} review={r} />
          ))}
        </div>
      )}
    </div>
  )
}

export function DiaryPanel() {
  const { code } = useStock()
  const name = useStockName()
  const qc = useQueryClient()

  const q = useQuery({
    queryKey: ['diary', code],
    queryFn: () => getDiary(code),
    enabled: !!code,
  })

  const refreshMut = useMutation({
    mutationFn: () => refreshDiary(code),
    onSuccess: (r) => {
      message.success(`已补齐复盘：${r.new_reviews} 条新纪录`)
      qc.invalidateQueries({ queryKey: ['diary', code] })
    },
    onError: (e: any) => message.error(e?.message || '复盘失败'),
  })

  if (!code) return null

  const entries = q.data || []

  // 命中率统计：每 (as_of_date, horizon) 只取最新那一版参与，避免同日多次重生成把分母灌大
  const seen = new Set<string>()
  const dedup: DiaryReportEntry[] = []
  for (const e of entries) {
    const k = `${e.as_of_date}__${e.horizon}`
    if (seen.has(k)) continue
    seen.add(k)
    dedup.push(e)
  }
  const decided = dedup.filter((e) => e.latest_verdict_hit === 'hit' || e.latest_verdict_hit === 'miss')
  const hits = decided.filter((e) => e.latest_verdict_hit === 'hit').length
  const accuracy = decided.length > 0 ? (hits / decided.length) * 100 : null

  return (
    <Card styles={{ body: { padding: 20 } }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space align="baseline" size={8} style={{ justifyContent: 'space-between', width: '100%' }}>
          <Space align="baseline" size={8}>
            <Title level={5} style={{ margin: 0 }}>
              <HistoryOutlined style={{ color: '#7c3aed', marginRight: 8 }} />
              分析日志
            </Title>
            {name && (
              <Text type="secondary" style={{ fontSize: 15 }}>
                {name}（{code}）
              </Text>
            )}
          </Space>
          <Space>
            {accuracy != null && (
              <Tag color={accuracy >= 60 ? 'success' : accuracy >= 40 ? 'default' : 'error'}>
                命中率 {accuracy.toFixed(0)}% ({hits}/{decided.length})
              </Tag>
            )}
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={refreshMut.isPending}
              onClick={() => refreshMut.mutate()}
            >
              刷新复盘
            </Button>
          </Space>
        </Space>

        {q.isLoading && <Spin />}
        {q.isError && <Alert type="error" showIcon message="日记加载失败" />}
        {!q.isLoading && entries.length === 0 && (
          <Empty description="暂无历史 AI 报告 — 先生成一份分析" />
        )}

        {entries.length > 0 && (
          <Timeline
            items={entries.map((e, i) => {
              // 同一天已经处理过多少条（entries 已按 as_of desc + created desc）
              const sameDayBefore = entries.slice(0, i).filter((x) => x.as_of_date === e.as_of_date).length
              return {
                color:
                  e.latest_verdict_hit === 'hit'
                    ? 'green'
                    : e.latest_verdict_hit === 'miss'
                      ? 'red'
                      : 'blue',
                children: <DiaryEntry entry={e} sameDayIndex={sameDayBefore} />,
              }
            })}
          />
        )}

        <Text type="secondary" style={{ fontSize: 12 }}>
          T+N 相对报告发布日的交易日数；verdict 判定阈值 ±2%，短线看 T+3，中线/综合看 T+10。
        </Text>
      </Space>
    </Card>
  )
}
