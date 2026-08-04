import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Checkbox, Empty, Segmented, Select, Space, Spin, Switch, Tag, Typography, message } from 'antd'
import { PlayCircleOutlined, QuestionCircleOutlined, RobotOutlined, StopOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  analyzeBatchScore,
  cancelScan,
  getScanStatus,
  getScoreDetail,
  getScoreList,
  runScan,
  ScoreDetail as ScoreDetailType,
  StockComment as StockCommentType,
  ScoreSummary as ScoreSummaryType,
  summarizeScore,
} from '@/api/score'
import { getGroups } from '@/api/groups'
import { addWatchlist } from '@/api/watchlist'
import { useInvalidation } from '@/hooks/useInvalidation'
import ScoreRow from './components/ScoreRow'
import ScoreDetailView from './components/ScoreDetail'
import ScoreCriteriaModal from './components/ScoreCriteriaModal'
import ScoreSummaryModal from './components/ScoreSummaryModal'
import ScoreCommentsModal from './components/ScoreCommentsModal'

const { Text } = Typography

export default function ScoreboardPage() {
  const qc = useQueryClient()
  const globalInv = useInvalidation()
  const navigate = useNavigate()
  // 跳转到个股完整详情页
  const openDetail = (code: string) => navigate(`/stock/${code}`)
  // 列表固定按综合分排序，只保留升降序切换
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')
  const [onlyEntry, setOnlyEntry] = useState(false)
  // 范围 + 自选分组选择持久化（localStorage），切页面回来不丢
  const [scope, setScope] = useState<string>(() => localStorage.getItem('scoreboard-scope') || 'all')
  const [groupIds, setGroupIds] = useState<number[]>(() => {
    try {
      const arr = JSON.parse(localStorage.getItem('scoreboard-group-ids') ?? '[]')
      return Array.isArray(arr) ? arr.filter((x: unknown) => typeof x === 'number') : []
    } catch {
      return []
    }
  })
  const [force, setForce] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [criteriaOpen, setCriteriaOpen] = useState(false)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [commentsOpen, setCommentsOpen] = useState(false)

  // 自选分组列表（选"自选分组"范围时用）
  const groupsQ = useQuery({
    queryKey: ['groups'],
    queryFn: getGroups,
    enabled: scope === 'group',
  })
  const groups = groupsQ.data ?? []

  // 打分排行（选了自选分组范围时，按所选分组过滤显示）
  const activeGroupIds = scope === 'group' && groupIds.length ? groupIds.join(',') : undefined
  const listQ = useQuery({
    queryKey: ['score-list', sortDir, onlyEntry, activeGroupIds],
    queryFn: () =>
      getScoreList({
        sort_by: 'total',
        dir: sortDir,
        limit: 200,
        can_entry: onlyEntry ? true : undefined,
        group_ids: activeGroupIds,
      }),
  })
  const items = listQ.data ?? []

  // 扫描状态轮询（扫描中 2s，空闲 30s）
  const statusQ = useQuery({
    queryKey: ['score-scan-status'],
    queryFn: getScanStatus,
    refetchInterval: (q: any) => (q.state.data?.running ? 2000 : 30_000),
  })
  const scan = statusQ.data

  // 扫描结束 → 刷新列表与详情
  // 两个完成信号：running true→false（正常慢扫描）；finished_at null→有值（兜底，
  // 防止扫描太快、空闲 30s 轮询没 poll 到 running=true 时漏掉完成事件）
  const prevRunning = useRef<boolean>(false)
  const prevFinishedNull = useRef<boolean>(false)
  useEffect(() => {
    const running = !!scan?.running
    const finishedAtIsNull = scan?.finished_at == null
    const justFinished = prevRunning.current && !running
    const finishedAppeared = prevFinishedNull.current && !finishedAtIsNull && !running
    if (justFinished || finishedAppeared) {
      qc.invalidateQueries({ queryKey: ['score-list'] })
      if (selected) qc.invalidateQueries({ queryKey: ['score-detail', selected] })
    }
    prevRunning.current = running
    prevFinishedNull.current = finishedAtIsNull
  }, [scan?.running, scan?.finished_at, qc, selected])

  // 详情
  const detailQ = useQuery({
    queryKey: ['score-detail', selected],
    queryFn: () => getScoreDetail(selected!),
    enabled: !!selected,
  })
  const detail: ScoreDetailType | undefined = detailQ.data

  const scanMut = useMutation({
    mutationFn: () =>
      runScan({
        scope,
        force,
        group_ids: scope === 'group' && groupIds.length ? groupIds : undefined,
      }),
    onSuccess: (d) => {
      if (d.started === false) message.warning(d.reason || '已有扫描进行中')
      else message.success(`开始扫描，共 ${d.total} 只`)
      // 立即刷新扫描状态：让轮询尽快切到 running(2s)，避免最长 30s 的空闲轮询延迟
      qc.invalidateQueries({ queryKey: ['score-scan-status'] })
    },
    onError: () => message.error('触发扫描失败'),
  })

  const cancelMut = useMutation({
    mutationFn: cancelScan,
    onSuccess: () => message.info('已请求取消'),
  })

  // AI 逐股点评（独立按钮：对当前列表每只各自生成总结，不做组对比）
  const commentMut = useMutation({
    mutationFn: () =>
      analyzeBatchScore({
        scope,
        group_ids: scope === 'group' && groupIds.length ? groupIds.join(',') : undefined,
        sort_by: 'total',
        dir: sortDir,
        limit: 10,
      }),
    onSuccess: () => setCommentsOpen(true),
    onError: () => message.error('AI 逐股点评失败，请稍后重试'),
  })
  const commentData: StockCommentType[] | null = commentMut.data?.items ?? null

  // AI 整组汇总（独立按钮，复用当前列表的过滤/排序参数，不参与扫描）
  const summaryMut = useMutation({
    mutationFn: () =>
      summarizeScore({
        scope,
        group_ids: scope === 'group' && groupIds.length ? groupIds.join(',') : undefined,
        sort_by: 'total',
        dir: sortDir,
        limit: 15,
      }),
    onSuccess: () => setSummaryOpen(true),
    onError: () => message.error('AI 汇总失败，请稍后重试'),
  })
  const summaryData: ScoreSummaryType | null = summaryMut.data ?? null

  const addMut = useMutation({
    // 处于"自选分组"范围且选中了分组时，加入自选直接放进当前分组
    mutationFn: (code: string) =>
      addWatchlist(code, scope === 'group' && groupIds.length ? groupIds : undefined),
    onSuccess: () => {
      message.success('已加入自选股')
      globalInv.afterSync()
    },
    onError: () => message.error('加入自选失败'),
  })

  const running = !!scan?.running
  const progress = scan && scan.total > 0 ? Math.round((scan.done / scan.total) * 100) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: 'calc(100vh - 96px)' }}>
      {/* 顶部工具栏：扫描操作 | AI 分析 | 排序过滤 三组 */}
      <Card size="small" styles={{ body: { padding: '10px 16px' } }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Space size={8} align="center" wrap>
            <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>选股扫描</span>
            <Button
              type="link"
              size="small"
              icon={<QuestionCircleOutlined />}
              onClick={() => setCriteriaOpen(true)}
              style={{ padding: 0 }}
            >
              选股标准
            </Button>
            <Select
              size="small"
              value={scope}
              onChange={(v) => {
                setScope(v)
                localStorage.setItem('scoreboard-scope', v)
                if (v !== 'group') {
                  setGroupIds([])
                  localStorage.setItem('scoreboard-group-ids', '[]')
                }
              }}
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
                onChange={(v) => {
                  const ids = v as number[]
                  setGroupIds(ids)
                  localStorage.setItem('scoreboard-group-ids', JSON.stringify(ids))
                }}
                placeholder="多选分组，列表只显示这些组"
                style={{ minWidth: 220, maxWidth: 440 }}
                options={groups.map((g) => ({ value: g.id, label: `${g.name} (${g.stock_count})` }))}
              />
            )}
            <Checkbox checked={force} onChange={(e) => setForce(e.target.checked)}>
              强制重扫
            </Checkbox>
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={scanMut.isPending}
              disabled={running}
              onClick={() => scanMut.mutate()}
            >
              {running ? '扫描中' : '开始扫描'}
            </Button>
            {running && (
              <Button size="small" icon={<StopOutlined />} onClick={() => cancelMut.mutate()}>
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

          <Space size={8} align="center" wrap>
            <Button
              size="small"
              type="primary"
              ghost
              icon={<RobotOutlined />}
              loading={commentMut.isPending}
              onClick={() => commentMut.mutate()}
            >
              AI 点评
            </Button>
            <Button
              size="small"
              icon={<RobotOutlined />}
              loading={summaryMut.isPending}
              onClick={() => summaryMut.mutate()}
            >
              AI 汇总
            </Button>
          </Space>

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

      {/* 内容区：master-detail，左右栏等高各自滚动 */}
      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
        <Card
          size="small"
          title={`打分排行 (${items.length})`}
          style={{ width: 540, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
          styles={{
            header: { flexShrink: 0, minHeight: 45, padding: '8px 16px' },
            body: { padding: 0, flex: 1, overflowY: 'auto' },
          }}
        >
          {items.length === 0 && !running && (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无打分记录，先点开始扫描" style={{ padding: 24 }} />
          )}
          {items.length === 0 && running && (
            <div style={{ padding: 32, textAlign: 'center' }}>
              <Spin /> 正在扫描...
            </div>
          )}
          {items.map((item) => (
            <ScoreRow
              key={item.code}
              item={item}
              active={selected === item.code}
              onClick={() => setSelected(item.code)}
              onAddWatchlist={(code) => addMut.mutate(code)}
              onOpenDetail={openDetail}
            />
          ))}
        </Card>

        <div style={{ flex: 1, minWidth: 0, overflowY: 'auto', height: '100%' }}>
          {!selected && (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Empty description="点击左侧股票查看打分详情" />
            </div>
          )}
          {selected && detailQ.isLoading && (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Spin size="large" />
            </div>
          )}
          {detail && <ScoreDetailView detail={detail} onAddWatchlist={(code) => addMut.mutate(code)} onOpenDetail={openDetail} />}
        </div>
      </div>

      <ScoreCriteriaModal open={criteriaOpen} onClose={() => setCriteriaOpen(false)} />
      <ScoreSummaryModal
        open={summaryOpen}
        onClose={() => setSummaryOpen(false)}
        loading={summaryMut.isPending}
        data={summaryData}
        count={summaryData?.count}
      />
      <ScoreCommentsModal
        open={commentsOpen}
        onClose={() => setCommentsOpen(false)}
        loading={commentMut.isPending}
        items={commentData}
        count={commentData?.length}
      />
    </div>
  )
}
