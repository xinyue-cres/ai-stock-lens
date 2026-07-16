import { api } from './client'

export async function runSync() {
  const { data } = await api.post('/sync/run', {}, { timeout: 60_000 })
  return data
}

export async function syncSingleStock(code: string) {
  const { data } = await api.post(`/sync/stock/${code}`, {}, { timeout: 30_000 })
  return data as { code: string; rows_inserted: number }
}

export async function refreshToday() {
  const { data } = await api.post('/sync/refresh-today', {}, { timeout: 60_000 })
  return data
}

export async function getSyncLogs(limit = 20) {
  const { data } = await api.get('/sync/logs', { params: { limit } })
  return data
}

export interface SyncStatus {
  scheduler: {
    running: boolean
    enabled: boolean
    cron_hour: number
    cron_minute: number
    next_run_at: string | null
  }
  last_sync: {
    id: number
    started_at: string
    finished_at: string | null
    status: string
    stocks_synced: number
    error_msg: string | null
  } | null
}

export async function getSyncStatus(): Promise<SyncStatus> {
  const { data } = await api.get<SyncStatus>('/sync/status')
  return data
}

// ---- 数据源健康度 ----

export interface ProviderHealth {
  name: string
  healthy: boolean
  failures: number
  cooldown_remaining: number
}

export async function getDatasourceHealth(): Promise<{ providers: ProviderHealth[] }> {
  const { data } = await api.get('/sync/datasource-health')
  return data
}
