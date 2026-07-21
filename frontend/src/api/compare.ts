import { api } from './client'

export interface CompareRanking {
  code: string
  name: string
  score: number
  verdict: string
  strength?: string
  rationale: string
}

export interface CompareAllocation {
  code: string
  name: string
  pct: number
  reason: string
}

export interface CompareReport {
  id: number
  codes: string[]
  names?: string[]
  as_of_date: string
  summary: string
  report_md: string
  ranking: CompareRanking[]
  allocation: CompareAllocation[]
  correlation_note: string
  risk_note: string
  created_at?: string
  cached?: boolean
}

export interface CompareListItem {
  id: number
  codes: string[]
  names: string[]
  as_of_date: string
  summary: string
  created_at: string
}

export async function generateCompare(codes: string[], force = false): Promise<CompareReport> {
  const { data } = await api.post('/compare', { codes, force })
  return data
}

export async function getCompareHistory(): Promise<{ items: CompareListItem[] }> {
  const { data } = await api.get('/compare/history')
  return data
}

export async function getCompareDetail(id: number): Promise<CompareReport> {
  const { data } = await api.get(`/compare/${id}`)
  return data
}

export async function deleteCompare(id: number): Promise<void> {
  await api.delete(`/compare/${id}`)
}
