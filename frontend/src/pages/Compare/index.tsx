import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Spin, Tag, Typography } from 'antd'
import Markdown from 'react-markdown'
import { getCompareHistory, getCompareDetail, CompareReport, CompareListItem } from '@/api/compare'
import { verdictPalette, Verdict } from '@/shared/theme'

const { Text, Title } = Typography

export default function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeId, setActiveId] = useState<number | null>(
    searchParams.get('id') ? Number(searchParams.get('id')) : null
  )

  const historyQ = useQuery({
    queryKey: ['compare-history'],
    queryFn: getCompareHistory,
  })

  const detailQ = useQuery({
    queryKey: ['compare-detail', activeId],
    queryFn: () => getCompareDetail(activeId!),
    enabled: !!activeId,
  })

  useEffect(() => {
    if (activeId) {
      setSearchParams({ id: String(activeId) }, { replace: true })
    }
  }, [activeId])

  // 如果没有 activeId 但有历史，自动选第一个
  useEffect(() => {
    if (!activeId && historyQ.data?.items?.length) {
      setActiveId(historyQ.data.items[0].id)
    }
  }, [historyQ.data])

  const items: CompareListItem[] = historyQ.data?.items ?? []
  const report: CompareReport | undefined = detailQ.data

  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
      {/* 左侧历史列表 */}
      <div style={{ width: 240, flexShrink: 0 }}>
        <Card size="small" title="对比历史" styles={{ body: { padding: 0, maxHeight: 'calc(100vh - 160px)', overflowY: 'auto' } }}>
          {items.length === 0 && (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无对比记录" style={{ padding: 24 }} />
          )}
          {items.map(item => (
            <div
              key={item.id}
              onClick={() => setActiveId(item.id)}
              style={{
                padding: '10px 14px',
                cursor: 'pointer',
                borderBottom: '1px solid #f5f5f5',
                background: activeId === item.id ? '#eff6ff' : 'transparent',
                borderLeft: activeId === item.id ? '3px solid #3b82f6' : '3px solid transparent',
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 500 }}>
                {item.names.join(' vs ')}
              </div>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {item.created_at} · {item.codes.length} 只
              </Text>
            </div>
          ))}
        </Card>
      </div>

      {/* 右侧报告详情 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {!activeId && (
          <Empty description="选择左侧的对比记录，或从列表页多选股票生成新的对比" style={{ padding: 60 }} />
        )}
        {activeId && detailQ.isLoading && (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
        )}
        {report && <CompareReportView report={report} />}
      </div>
    </div>
  )
}

function CompareReportView({ report }: { report: CompareReport }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 摘要 */}
      <Card size="small">
        <Text strong style={{ fontSize: 14 }}>{report.summary}</Text>
        <div style={{ marginTop: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {(report.names || report.codes).join(' · ')} · {report.as_of_date}
          </Text>
        </div>
      </Card>

      {/* 排名 */}
      {report.ranking?.length > 0 && (
        <Card size="small" title="综合排名">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {report.ranking.map((r, i) => {
              const vp = verdictPalette[(r.verdict as Verdict) || 'neutral']
              return (
                <div key={r.code} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid #f9fafb' }}>
                  <span style={{ width: 24, height: 24, borderRadius: '50%', background: i === 0 ? '#f59e0b' : i === 1 ? '#9ca3af' : '#d4d4d8', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600, flexShrink: 0 }}>
                    {i + 1}
                  </span>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontWeight: 500, fontSize: 13 }}>{r.name}</span>
                    <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>{r.code}</Text>
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                      {r.strength && <span>{r.strength} · </span>}
                      {r.rationale}
                    </div>
                  </div>
                  <Tag style={{ margin: 0, color: vp.color, borderColor: vp.border, background: vp.bg }}>{vp.label}</Tag>
                  <span style={{ fontSize: 14, fontWeight: 600, minWidth: 32, textAlign: 'right' }}>{r.score}</span>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* 资金配置 */}
      {report.allocation?.length > 0 && (
        <Card size="small" title="资金配置建议">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {report.allocation.map(a => (
              <div key={a.code} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontWeight: 500, fontSize: 13, width: 80 }}>{a.name}</span>
                <div style={{ flex: 1, height: 18, background: '#f3f4f6', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${a.pct}%`, height: '100%', background: a.code === 'cash' ? '#9ca3af' : '#3b82f6', borderRadius: 4, transition: 'width 0.3s' }} />
                </div>
                <span style={{ fontSize: 13, fontWeight: 600, minWidth: 36, textAlign: 'right' }}>{a.pct}%</span>
                <Text type="secondary" style={{ fontSize: 11, minWidth: 80 }}>{a.reason}</Text>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 相关性 + 风险 */}
      <div style={{ display: 'flex', gap: 16 }}>
        {report.correlation_note && (
          <Card size="small" title="相关性" style={{ flex: 1 }}>
            <Text style={{ fontSize: 13 }}>{report.correlation_note}</Text>
          </Card>
        )}
        {report.risk_note && (
          <Card size="small" title="风险提示" style={{ flex: 1 }}>
            <Text style={{ fontSize: 13 }}>{report.risk_note}</Text>
          </Card>
        )}
      </div>

      {/* Markdown 报告 */}
      {report.report_md && (
        <Card size="small" title="完整报告">
          <div className="compare-report-md" style={{ fontSize: 13, lineHeight: 1.7 }}>
            <Markdown>{report.report_md}</Markdown>
          </div>
          <style>{`
            .compare-report-md table {
              width: 100%;
              border-collapse: collapse;
              margin: 12px 0;
              font-size: 12px;
            }
            .compare-report-md th,
            .compare-report-md td {
              border: 1px solid #e5e7eb;
              padding: 6px 10px;
              text-align: left;
            }
            .compare-report-md th {
              background: #f9fafb;
              font-weight: 600;
            }
            .compare-report-md tr:hover td {
              background: #f9fafb;
            }
          `}</style>
        </Card>
      )}
    </div>
  )
}
