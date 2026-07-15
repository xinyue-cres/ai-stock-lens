import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Space, Statistic, Table, Tag, Typography, message } from 'antd'
import { getDatasourceHealth, getSyncLogs, getSyncStatus, ProviderHealth, runSync } from '@/api/sync'

const { Text } = Typography

const statusColor: Record<string, string> = {
  success: 'green',
  partial: 'orange',
  failed: 'red',
  running: 'blue',
}

function fmtTime(v: string | null | undefined) {
  return v ? new Date(v).toLocaleString('zh-CN') : '-'
}

export default function SyncLogs() {
  const qc = useQueryClient()

  const statusQ = useQuery({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
    refetchInterval: 30_000,
  })

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['sync-logs'],
    queryFn: () => getSyncLogs(50),
    refetchInterval: 30_000,
  })

  const healthQ = useQuery({
    queryKey: ['datasource-health'],
    queryFn: getDatasourceHealth,
    refetchInterval: 30_000,
  })

  const syncMut = useMutation({
    mutationFn: runSync,
    onSuccess: (d) => {
      message.success(`同步完成 · ${d.status} · ${d.stocks_synced} 只`)
      qc.invalidateQueries({ queryKey: ['sync-status'] })
      qc.invalidateQueries({ queryKey: ['sync-logs'] })
    },
    onError: () => message.error('同步失败'),
  })

  const sched = statusQ.data?.scheduler
  const last = statusQ.data?.last_sync

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="通常你不需要主动来这里"
        description="加入自选股会自动首次同步；每交易日收盘后 16:10 系统会自动同步所有自选股。这个页面用来查看后台任务状态和排错。"
      />

      <Card
        title="任务状态"
        extra={
          <Button type="primary" loading={syncMut.isPending} onClick={() => syncMut.mutate()}>
            立即同步自选股
          </Button>
        }
      >
        <Space size={40} wrap>
          <Statistic
            title="调度器"
            value={sched?.running ? '运行中' : '未运行'}
            valueStyle={{ color: sched?.running ? '#10b981' : '#ef4444', fontSize: 22 }}
          />
          <Statistic
            title="每日同步时间"
            value={
              sched
                ? `${String(sched.cron_hour).padStart(2, '0')}:${String(sched.cron_minute).padStart(2, '0')}`
                : '-'
            }
            valueStyle={{ fontSize: 22 }}
          />
          <Statistic
            title="下次执行"
            value={fmtTime(sched?.next_run_at)}
            valueStyle={{ fontSize: 16 }}
          />
          <Statistic
            title="最近一次同步"
            value={last ? `${last.status} · ${last.stocks_synced} 只` : '尚未同步'}
            valueStyle={{
              color: last ? statusColor[last.status] : undefined,
              fontSize: 18,
            }}
          />
        </Space>
        {last?.error_msg && (
          <Alert
            style={{ marginTop: 12 }}
            type="warning"
            message="上次同步存在错误"
            description={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{last.error_msg}</pre>}
          />
        )}
      </Card>

      <Card title="数据源健康度" size="small">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {(healthQ.data?.providers || []).map((p: ProviderHealth) => {
            const ok = p.healthy && p.failures === 0
            const warn = p.healthy && p.failures > 0
            const bad = !p.healthy
            const bg = bad ? '#fef2f2' : warn ? '#fffbeb' : '#f0fdf4'
            const border = bad ? '#fecaca' : warn ? '#fde68a' : '#bbf7d0'
            const dot = bad ? '#dc2626' : warn ? '#d97706' : '#16a34a'
            return (
              <div
                key={p.name}
                style={{
                  border: `1px solid ${border}`,
                  background: bg,
                  borderRadius: 8,
                  padding: '12px 14px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: dot,
                      display: 'inline-block',
                    }}
                  />
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{p.name}</span>
                </div>
                <div style={{ fontSize: 12, color: dot }}>
                  {bad
                    ? `不可用 · ${p.cooldown_remaining}s 后重试`
                    : warn
                    ? `连续失败 ${p.failures} 次`
                    : '就绪'}
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      <Card title="历史记录" size="small">
        <Table
          loading={isLoading}
          dataSource={logs}
          rowKey="id"
          size="small"
          columns={[
            { title: 'ID', dataIndex: 'id', width: 60 },
            {
              title: '开始',
              dataIndex: 'started_at',
              width: 190,
              render: fmtTime,
            },
            {
              title: '结束',
              dataIndex: 'finished_at',
              width: 190,
              render: fmtTime,
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (v: string) => <Tag color={statusColor[v] || 'default'}>{v}</Tag>,
            },
            { title: '成功只数', dataIndex: 'stocks_synced', width: 100 },
            {
              title: '错误',
              dataIndex: 'error_msg',
              render: (v: string | null) =>
                v ? (
                  <Text type="danger" style={{ fontSize: 12 }}>
                    {v}
                  </Text>
                ) : (
                  <Tag>无</Tag>
                ),
            },
          ]}
        />
      </Card>
    </Space>
  )
}
