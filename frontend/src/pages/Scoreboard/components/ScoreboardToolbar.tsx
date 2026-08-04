import { Button, Card, Checkbox, Segmented, Select, Space, Switch, Tag, Typography } from 'antd'
import { PlayCircleOutlined, QuestionCircleOutlined, RobotOutlined, StopOutlined } from '@ant-design/icons'
import type { ScanStatus } from '@/api/score'

const { Text } = Typography

export interface GroupOption {
  id: number
  name: string
  stock_count: number
}

interface ScoreboardToolbarProps {
  scope: string
  setScope: (v: string) => void
  groupIds: number[]
  setGroupIds: (v: number[]) => void
  groups: GroupOption[]
  force: boolean
  setForce: (v: boolean) => void
  sortDir: 'desc' | 'asc'
  setSortDir: (v: 'desc' | 'asc') => void
  onlyEntry: boolean
  setOnlyEntry: (v: boolean) => void
  scan: ScanStatus | undefined
  running: boolean
  scanPending: boolean
  commentPending: boolean
  summaryPending: boolean
  onStartScan: () => void
  onCancelScan: () => void
  onAIComment: () => void
  onAISummary: () => void
  onOpenCriteria: () => void
}

export default function ScoreboardToolbar(props: ScoreboardToolbarProps) {
  const {
    scope, setScope, groupIds, setGroupIds, groups, force, setForce,
    sortDir, setSortDir, onlyEntry, setOnlyEntry,
    scan, running, scanPending, commentPending, summaryPending,
    onStartScan, onCancelScan, onAIComment, onAISummary, onOpenCriteria,
  } = props

  const progress = scan && scan.total > 0 ? Math.round((scan.done / scan.total) * 100) : 0

  return (
    <Card size="small" styles={{ body: { padding: '10px 16px' } }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {/* 扫描操作 */}
        <Space size={8} align="center" wrap>
          <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>选股扫描</span>
          <Button type="link" size="small" icon={<QuestionCircleOutlined />} onClick={onOpenCriteria} style={{ padding: 0 }}>
            选股标准
          </Button>
          <Select
            size="small"
            value={scope}
            onChange={setScope}
            style={{ width: 130 }}
            options={[
              { value: 'all', label: '全 A 股 + ETF' },
              { value: 'watchlist', label: '全部自选' },
              { value: 'group', label: '自选分组' },
            ]}
          />
          {scope === 'group' && (
            <Select
              size="small"
              mode="multiple"
              value={groupIds}
              onChange={setGroupIds}
              placeholder="多选分组，列表只显示这些组"
              style={{ minWidth: 220, maxWidth: 440 }}
              options={groups.map((g) => ({ value: g.id, label: `${g.name} (${g.stock_count})` }))}
            />
          )}
          <Checkbox checked={force} onChange={(e) => setForce(e.target.checked)}>
            强制重扫
          </Checkbox>
          <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={scanPending} disabled={running} onClick={onStartScan}>
            {running ? '扫描中' : '开始扫描'}
          </Button>
          {running && (
            <Button size="small" icon={<StopOutlined />} onClick={onCancelScan}>
              取消
            </Button>
          )}
          {running && (
            <Tag color="blue" style={{ marginInlineEnd: 0 }}>
              {scan?.done ?? 0}/{scan?.total ?? 0} · {progress}%
              {scan?.failed ? ` · 失败 ${scan.failed}` : ''}
            </Tag>
          )}
        </Space>

        <div style={{ flex: 1 }} />

        {/* AI 分析 */}
        <Space size={8} align="center" wrap>
          <Button size="small" type="primary" ghost icon={<RobotOutlined />} loading={commentPending} onClick={onAIComment}>
            AI 点评
          </Button>
          <Button size="small" icon={<RobotOutlined />} loading={summaryPending} onClick={onAISummary}>
            AI 汇总
          </Button>
        </Space>

        {/* 排序过滤 */}
        <Space size={8} align="center" wrap>
          <Segmented
            size="small"
            value={sortDir}
            onChange={(v) => setSortDir(v as 'desc' | 'asc')}
            options={[
              { value: 'desc', label: '综合降' },
              { value: 'asc', label: '综合升' },
            ]}
          />
          <Switch size="small" checked={onlyEntry} onChange={setOnlyEntry} />
          <Text type="secondary" style={{ fontSize: 12 }}>
            只看可入手
          </Text>
        </Space>
      </div>
    </Card>
  )
}
