import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient, useIsMutating } from '@tanstack/react-query'
import { Button, Popconfirm, Space, Tooltip, Typography, message } from 'antd'
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { getSyncStatus, refreshToday, runSync } from '@/api/sync'
import { SYNC_ALL_KEY, useInvalidation } from '@/hooks/useInvalidation'

const { Text } = Typography

/**
 * 顶栏全局状态：上次同步相对时间 + 一键同步 + 强制同步。
 * 数据日期归属于"当前股票"，展示在 AI 报告标题栏里，此处只放全局操作。
 */
export function GlobalStatusBar() {
  const qc = useQueryClient()
  const inv = useInvalidation()
  const syncingElsewhere = useIsMutating({ mutationKey: SYNC_ALL_KEY }) > 0

  const statusQ = useQuery({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
    // 同步进行中 3s 轮询看进度；空闲 60s
    refetchInterval: (q: any) => (q.state.data?.last_sync?.status === 'running' ? 3_000 : 60_000),
  })

  const syncRunning = statusQ.data?.last_sync?.status === 'running'

  const afterSync = () => {
    qc.invalidateQueries({ queryKey: ['sync-status'] })
    inv.afterSync()
  }

  const syncMut = useMutation({
    mutationKey: SYNC_ALL_KEY,
    mutationFn: runSync,
    onSuccess: (r: any) => {
      if (r?.started === false) message.warning(r?.reason || '已有同步进行中')
      else message.success('已在后台开始同步，完成后自动更新')
      afterSync()
    },
    onError: () => message.error('触发同步失败'),
  })

  const refreshTodayMut = useMutation({
    mutationKey: SYNC_ALL_KEY,
    mutationFn: refreshToday,
    onSuccess: (r: any) => {
      if (r?.started === false) message.warning(r?.reason || '已有同步进行中')
      else
        message.success(
          r?.rows_deleted ? `已在后台重拉今日 · 清除 ${r.rows_deleted} 行` : '已在后台重拉今日数据',
        )
      afterSync()
    },
    onError: () => message.error('触发同步失败'),
  })

  const lastSyncText = useMemo(() => {
    const s = statusQ.data?.last_sync
    if (!s?.finished_at) return null
    return relativeTime(s.finished_at)
  }, [statusQ.data])

  const busy = syncMut.isPending || refreshTodayMut.isPending || syncingElsewhere || syncRunning

  return (
    <Space size={12} style={{ color: '#e5e7eb', fontSize: 13 }}>
      {lastSyncText && (
        <Text style={{ color: '#94a3b8', fontSize: 12 }}>上次同步 {lastSyncText}</Text>
      )}
      <Tooltip title="同步全部自选股当日 K 线，并触发 AI 报告复盘">
        <Button
          size="small"
          type="default"
          icon={<ReloadOutlined />}
          loading={syncMut.isPending}
          disabled={busy}
          onClick={() => syncMut.mutate()}
        >
          {syncRunning || syncMut.isPending ? '同步中…' : '立即同步'}
        </Button>
      </Tooltip>
      <Popconfirm
        title="强制同步今日 K 线？"
        description="将清除所有自选股今日已入库的 K 线并重新拉取。收盘后使用可拿到最终数据。"
        okText="重拉"
        cancelText="取消"
        onConfirm={() => refreshTodayMut.mutate()}
      >
        <Tooltip title="盘中入库的可能是脏快照，收盘后用它可强制重拉当天最终 K 线">
          <Button
            size="small"
            danger
            icon={<ThunderboltOutlined />}
            loading={refreshTodayMut.isPending}
            disabled={busy}
          >
            {syncRunning || refreshTodayMut.isPending ? '同步中…' : '强制同步'}
          </Button>
        </Tooltip>
      </Popconfirm>
    </Space>
  )
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffMin = Math.round((now - then) / 60_000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  if (diffMin < 60 * 24) return `${Math.round(diffMin / 60)} 小时前`
  return `${Math.round(diffMin / 60 / 24)} 天前`
}
