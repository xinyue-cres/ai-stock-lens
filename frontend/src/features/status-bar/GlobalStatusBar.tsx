import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Popconfirm, Space, Tooltip, Typography, message } from 'antd'
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { getSyncStatus, refreshToday, runSync } from '@/api/sync'

const { Text } = Typography

/**
 * 顶栏全局状态：上次同步相对时间 + 一键同步 + 强制同步。
 * 数据日期归属于"当前股票"，展示在 AI 报告标题栏里，此处只放全局操作。
 */
export function GlobalStatusBar() {
  const qc = useQueryClient()

  const statusQ = useQuery({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
    refetchInterval: 60_000,
  })

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['sync-status'] })
    qc.invalidateQueries({ queryKey: ['kline'] })
    qc.invalidateQueries({ queryKey: ['diary'] })
    qc.invalidateQueries({ queryKey: ['signals'] })
    qc.invalidateQueries({ queryKey: ['analysis'] })
    qc.invalidateQueries({ queryKey: ['watchlist'] })
    qc.invalidateQueries({ queryKey: ['market-summary'] })
  }

  const toastResult = (r: any, label: string) => {
    const status = r?.status
    const rows = r?.rows_inserted ?? 0
    const done = r?.stocks_synced ?? 0
    const total = r?.stocks_total ?? done
    if (status === 'success' || status === 'partial') {
      const suffix = rows === 0 ? '（无新交易日数据 · 稍后再试）' : `· 新增 ${rows} 行`
      const level = rows === 0 ? 'warning' : 'success'
      message[level](`${label} · ${done}/${total} 只 ${suffix}`)
    } else {
      message.error(`${label} ${status}${r?.error_msg ? ' · ' + r.error_msg : ''}`)
    }
  }

  const syncMut = useMutation({
    mutationFn: runSync,
    onSuccess: (r: any) => {
      toastResult(r, '同步完成')
      invalidateAll()
    },
    onError: () => message.warning('同步超时，后台仍在运行，稍后刷新即可'),
  })

  const refreshTodayMut = useMutation({
    mutationFn: refreshToday,
    onSuccess: (r: any) => {
      const deleted = r?.rows_deleted ?? 0
      toastResult(r, `强制重拉完成 · 清除 ${deleted} 行`)
      invalidateAll()
    },
    onError: () => message.warning('同步超时，后台仍在运行，稍后刷新即可'),
  })

  const lastSyncText = useMemo(() => {
    const s = statusQ.data?.last_sync
    if (!s?.finished_at) return null
    return relativeTime(s.finished_at)
  }, [statusQ.data])

  const busy = syncMut.isPending || refreshTodayMut.isPending

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
          {syncMut.isPending ? '同步中…' : '立即同步'}
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
            {refreshTodayMut.isPending ? '同步中…' : '强制同步'}
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
