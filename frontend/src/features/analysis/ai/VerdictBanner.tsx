import { Space, Tag, Tooltip, Typography } from 'antd'
import { CloseCircleOutlined } from '@ant-design/icons'
import { AiReport } from '@/api/analysis'
import { verdictPalette } from '@/shared/theme'
import { timeAgo } from '@/shared/timeAgo'

const { Text, Paragraph } = Typography

interface Props {
  data: AiReport
  showCachedTag?: boolean
  /** 当前 K 线数据的最新交易日；若比报告的 as_of 更新则报告陈旧 */
  dataAsOf?: string | null
}

/** 顶部彩色条带：verdict + confidence + summary + 报告日期 + 陈旧提醒。 */
export function VerdictBanner({ data, showCachedTag, dataAsOf }: Props) {
  const p = verdictPalette[data.verdict] || verdictPalette.neutral
  const reportAsOf = data.as_of_date
  const stale = !!(reportAsOf && dataAsOf && reportAsOf < dataAsOf)
  const ago = timeAgo(data.created_at)

  return (
    <div
      style={{
        background: p.bg,
        border: `1px solid ${p.border}`,
        borderRadius: 8,
        padding: '16px 20px',
      }}
    >
      <Space align="baseline" size={12} wrap>
        <Tag
          style={{
            background: p.color,
            color: '#fff',
            fontSize: 16,
            padding: '4px 14px',
            border: 'none',
            margin: 0,
          }}
        >
          {p.label}
        </Tag>
        {typeof data.confidence === 'number' && (
          <Text type="secondary">置信度 {(data.confidence * 100).toFixed(0)}%</Text>
        )}
        {reportAsOf && (
          <Tooltip
            title={
              stale
                ? `AI 报告基于 ${reportAsOf} 数据，当前数据已更新到 ${dataAsOf} — 建议重新生成`
                : `AI 报告基于 ${reportAsOf} 数据${ago ? ` · 生成于${ago}` : ''}`
            }
          >
            <Tag
              icon={stale ? <CloseCircleOutlined /> : undefined}
              color={stale ? 'error' : undefined}
              style={{ margin: 0 }}
            >
              {stale ? `报告 ${reportAsOf} · 已过期` : ago || `报告 ${reportAsOf}`}
            </Tag>
          </Tooltip>
        )}
        {showCachedTag && <Tag color="cyan">缓存</Tag>}
      </Space>
      {data.summary && (
        <Paragraph style={{ margin: '10px 0 0', fontSize: 16, color: '#1f2937', lineHeight: 1.6 }}>
          {data.summary}
        </Paragraph>
      )}
    </div>
  )
}
