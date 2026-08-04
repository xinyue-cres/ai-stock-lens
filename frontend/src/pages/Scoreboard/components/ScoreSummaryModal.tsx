import { Empty, Modal, Spin, Tag, Typography } from 'antd'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ScoreSummary } from '@/api/score'

const { Text } = Typography

export default function ScoreSummaryModal({
  open,
  onClose,
  loading,
  data,
  count,
}: {
  open: boolean
  onClose: () => void
  loading: boolean
  data: ScoreSummary | null
  count?: number
}) {
  return (
    <Modal title="选股打分 AI 汇总" open={open} onCancel={onClose} footer={null} width={780}>
      {loading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
          <div style={{ marginTop: 14, color: '#6b7280' }}>
            AI 正在汇总 {count ?? '当前'} 只标的的打分结果，约 10-30 秒...
          </div>
        </div>
      )}
      {!loading && !data && <Empty description="暂无汇总结果" />}
      {!loading && data && (
        <div>
          <div style={{ background: '#f0f5ff', borderRadius: 8, padding: '10px 14px', marginBottom: 14 }}>
            <Text strong style={{ fontSize: 14 }}>{data.summary}</Text>
          </div>

          {data.highlights?.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <Text strong style={{ fontSize: 13 }}>亮点</Text>
              <ul style={{ margin: '6px 0 0', paddingLeft: 20 }}>
                {data.highlights.map((h, i) => (
                  <li key={i} style={{ fontSize: 13, color: '#4b5563', marginBottom: 2 }}>{h}</li>
                ))}
              </ul>
            </div>
          )}

          {data.watch?.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <Text strong style={{ fontSize: 13 }}>值得关注</Text>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                {data.watch.map((w) => (
                  <Tag key={w.code} color="blue" style={{ fontSize: 12 }}>
                    {w.name}（{w.code}）
                  </Tag>
                ))}
              </div>
            </div>
          )}

          {data.risk_note && (
            <div style={{ background: '#fffbeb', borderRadius: 8, padding: '10px 14px', marginBottom: 14 }}>
              <Text strong style={{ color: '#d97706', fontSize: 13 }}>风险提示</Text>
              <div style={{ fontSize: 13, color: '#4b5563', marginTop: 4 }}>{data.risk_note}</div>
            </div>
          )}

          {data.report_md && (
            <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: '8px 16px', background: '#fafafa' }}>
              <Markdown remarkPlugins={[remarkGfm]}>{data.report_md}</Markdown>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
