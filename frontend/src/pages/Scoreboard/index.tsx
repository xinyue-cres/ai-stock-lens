import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Empty, Spin, message } from 'antd'
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
import ScoreboardToolbar from './components/ScoreboardToolbar'
import ScoreRow from './components/ScoreRow'
import ScoreDetailView from './components/ScoreDetail'
import ScoreCriteriaModal from './components/ScoreCriteriaModal'
import ScoreSummaryModal from './components/ScoreSummaryModal'
import ScoreCommentsModal from './components/ScoreCommentsModal'
import { useScoreboardState } from './useScoreboardState'

export default function ScoreboardPage() {
  const qc = useQueryClient()
  const globalInv = useInvalidation()
  const navigate = useNavigate()
  // 跳转到个股完整详情页
  const openDetail = (code: string) => navigate(`/stock/${code}`)

  // 工具栏/过滤状态（scope/groupIds 持久化到 localStorage）
  const {
    sortDir, setSortDir, onlyEntry, setOnlyEntry,
    scope, setScope, groupIds, setGroupIds, force, setForce, aiParams,
  } = useScoreboardState()

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
  const running = !!scan?.running

  // 扫描结束 → 刷新列表与详情
  // 两个完成信号：running true→false（正常慢扫描）；finished_at null→有值（兜底，
  // 防止扫描太快、空闲 30s 轮询没 poll 到 running=true 时漏掉完成事件）
  const prevRunning = useRef<boolean>(false)
  const prevFinishedNull = useRef<boolean>(false)
  useEffect(() => {
    const runningNow = !!scan?.running
    const finishedAtIsNull = scan?.finished_at == null
    const justFinished = prevRunning.current && !runningNow
    const finishedAppeared = prevFinishedNull.current && !finishedAtIsNull && !runningNow
    if (justFinished || finishedAppeared) {
      qc.invalidateQueries({ queryKey: ['score-list'] })
      if (selected) qc.invalidateQueries({ queryKey: ['score-detail', selected] })
    }
    prevRunning.current = runningNow
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
    mutationFn: () => analyzeBatchScore({ ...aiParams, limit: 10 }),
    onSuccess: () => setCommentsOpen(true),
    onError: () => message.error('AI 逐股点评失败，请稍后重试'),
  })
  const commentData: StockCommentType[] | null = commentMut.data?.items ?? null

  // AI 整组汇总（独立按钮，复用当前列表的过滤/排序参数，不参与扫描）
  const summaryMut = useMutation({
    mutationFn: () => summarizeScore({ ...aiParams, limit: 15 }),
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: 'calc(100vh - 96px)' }}>
      <ScoreboardToolbar
        scope={scope}
        setScope={setScope}
        groupIds={groupIds}
        setGroupIds={setGroupIds}
        groups={groups}
        force={force}
        setForce={setForce}
        sortDir={sortDir}
        setSortDir={setSortDir}
        onlyEntry={onlyEntry}
        setOnlyEntry={setOnlyEntry}
        scan={scan}
        running={running}
        scanPending={scanMut.isPending}
        commentPending={commentMut.isPending}
        summaryPending={summaryMut.isPending}
        onStartScan={() => scanMut.mutate()}
        onCancelScan={() => cancelMut.mutate()}
        onAIComment={() => commentMut.mutate()}
        onAISummary={() => summaryMut.mutate()}
        onOpenCriteria={() => setCriteriaOpen(true)}
      />

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
