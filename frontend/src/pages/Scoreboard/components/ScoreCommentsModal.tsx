import { Empty, Modal, Spin, Tag, Typography } from 'antd'
import type { StockComment } from '@/api/score'

const { Text } = Typography

const VERDICT_COLOR: Record<string, string> = {
  关注: '#16a34a',
  观望: '#d97706',
  回避: '#dc2626',
  分析失败: '#6b7280',
}

export default function ScoreCommentsModal({
  open,
  onClose,
  loading,
  items,
  count,
}: {
  open: boolean
  onClose: () => void
  loading: boolean
  items: StockComment[] | null
  count?: number
}) {
  return (
    <Modal
      title={`AI 逐股点评${count ? `（${count} 只）` : ''}`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={780}
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
          <div style={{ marginTop: 14, color: '#6b7280' }}>
            AI 正在逐只点评 {count ?? ''} 只标的，每只独立分析，约 20-60 秒...
          </div>
        </div>
      )}
      {!loading && !items && <Empty description="暂无点评结果" />}
      {!loading && items && (
        <div style={{ maxHeight: '62vh', overflowY: 'auto', paddingRight: 4 }}>
          {items.map((it) => {
            const color = VERDICT_COLOR[it.verdict] ?? '#6b7280'
            return (
              <div
                key={it.code}
                style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 14px', marginBottom: 10 }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <b>{it.name || it.code}</b>
                  <Text type="secondary" style={{ fontSize: 12 }}>{it.code}</Text>
                  <Tag style={{ margin: 0, color, borderColor: color, background: `${color}14` }}>{it.verdict}</Tag>
                  {it.score_comment && (
                    <Text type="secondary" style={{ fontSize: 12, flex: 1, textAlign: 'right' }}>
                      {it.score_comment}
                    </Text>
                  )}
                </div>
                <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.6 }}>{it.summary}</div>
                {it.key_point && (
                  <div
                    style={{
                      marginTop: 6,
                      fontSize: 12,
                      color: '#b45309',
                      background: '#fffbeb',
                      borderRadius: 6,
                      padding: '4px 8px',
                      display: 'inline-block',
                    }}
                  >
                    ★ {it.key_point}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
