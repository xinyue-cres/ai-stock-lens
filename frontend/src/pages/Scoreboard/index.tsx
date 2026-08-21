import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Card, Empty, Spin } from 'antd'
import { ScoreItem as ScoreItemType } from '@/api/score'

import { useScoreboardData } from './hooks/useScoreboardData'
import { useScoreboardActions } from './hooks/useScoreboardActions'
import { useScoreboardState } from './useScoreboardState'

import ScoreboardToolbar from './components/ScoreboardToolbar'
import ScoreRow from './components/ScoreRow'
import ScoreDetailView from './components/ScoreDetail'
import CombinedView from './components/CombinedView'
import CombinedDetailView from './components/CombinedDetailView'
import ScoreCriteriaModal from './components/ScoreCriteriaModal'
import ScoreSummaryModal from './components/ScoreSummaryModal'
import ScoreCommentsModal from './components/ScoreCommentsModal'

export default function ScoreboardPage() {
  const navigate = useNavigate()
  // 跳转到个股完整详情页（useCallback 稳定引用，避免 ScoreRow memo 被 props 变化命中变失效）
  const openDetail = useCallback((code: string) => navigate(`/stock/${code}`), [navigate])
  // 跳转到工作台分组视图：已加自选且分到组 → 进该分组；未加自选 → 工作台全部
  const openWorkbench = useCallback((item: ScoreItemType) => {
    if (item.in_watchlist && item.group_ids && item.group_ids.length > 0) {
      navigate(`/?group=${item.group_ids[0]}`)
    } else {
      navigate('/')
    }
  }, [navigate])

  // URL 定位：?code=X 直接选中该票（工作台「看打分」跳过来）；selected 变化写回 URL
  const [searchParams, setSearchParams] = useSearchParams()
  const [selected, setSelected] = useState<string | null>(() => searchParams.get('code'))

  // URL → selected 双向同步：浏览器后退/前进/外部分享链接也能正确选中
  useEffect(() => {
    const urlCode = searchParams.get('code')
    if (urlCode !== selected) setSelected(urlCode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const selectStock = useCallback((code: string | null) => {
    setSelected(code)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (code) next.set('code', code)
      else next.delete('code')
      return next
    }, { replace: true })
  }, [setSearchParams])

  // 工具栏/过滤状态
  const {
    onlyEntry, setOnlyEntry,
    scope, setScope, groupIds, setGroupIds, force, setForce,
    peakFilter, setPeakFilter, timeframe, setTimeframe, aiParams,
  } = useScoreboardState()

  // 数据获取（列表/详情/分组/扫描进度）
  const {
    groups, items, scan, running,
    detailQ, detail,
    combinedDetailQ, combinedDetail,
  } = useScoreboardData({
    onlyEntry, scope, groupIds, peakFilter, timeframe, aiParams, selected,
  })

  // 异步操作（扫描/取消/AI/加自选）
  const {
    criteriaOpen, setCriteriaOpen,
    summaryOpen, setSummaryOpen,
    commentsOpen, setCommentsOpen,
    scanMut, cancelMut, commentMut, summaryMut, addMut,
    summaryData, commentData,
  } = useScoreboardActions({ scope, force, groupIds, timeframe, aiParams })

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
        onlyEntry={onlyEntry}
        setOnlyEntry={setOnlyEntry}
        peakFilter={peakFilter}
        setPeakFilter={setPeakFilter}
        timeframe={timeframe}
        setTimeframe={setTimeframe}
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

      {/* 内容区：左侧列表（综合=CombinedView / 日周=ScoreRow）+ 右侧详情 */}
      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
        {timeframe === 'combined' ? (
          <CombinedView
            scope={scope}
            groupIds={groupIds}
            selected={selected}
            onSelect={selectStock}
            onAddWatchlist={addMut.mutate}
          />
        ) : (
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
                onClick={selectStock}
                onAddWatchlist={addMut.mutate}
                onOpenDetail={openDetail}
                onOpenWorkbench={openWorkbench}
              />
            ))}
          </Card>
        )}

        <div style={{ flex: 1, minWidth: 0, overflowY: 'auto', height: '100%' }}>
          {!selected && (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Empty description="点击左侧股票查看打分详情" />
            </div>
          )}
          {selected && (detailQ.isLoading || combinedDetailQ.isLoading) && (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Spin size="large" />
            </div>
          )}
          {detail && (
            <ScoreDetailView
              detail={detail}
              onAddWatchlist={(code) => addMut.mutate(code)}
              onOpenDetail={openDetail}
            />
          )}
          {combinedDetail && (
            <CombinedDetailView
              detail={combinedDetail}
              onAddWatchlist={(code) => addMut.mutate(code)}
            />
          )}
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
