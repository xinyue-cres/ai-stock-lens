import { api } from './client'

export interface StockGroup {
  id: number
  name: string
  sort_order: number
  stock_count: number
}

export async function getGroups(): Promise<StockGroup[]> {
  const { data } = await api.get('/groups')
  return data
}

export async function createGroup(name: string, sort_order = 0): Promise<StockGroup> {
  const { data } = await api.post('/groups', { name, sort_order })
  return data
}

export async function updateGroup(id: number, payload: { name?: string; sort_order?: number }) {
  const { data } = await api.patch(`/groups/${id}`, payload)
  return data
}

export async function deleteGroup(id: number) {
  const { data } = await api.delete(`/groups/${id}`)
  return data
}

export async function patchStock(code: string, payload: { group_ids?: number[]; note?: string | null }) {
  const { data } = await api.patch(`/watchlist/${code}`, payload)
  return data
}
