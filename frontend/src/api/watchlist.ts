import { api } from './client'

export async function getWatchlist() {
  const { data } = await api.get('/watchlist')
  return data as { code: string; name: string; market: string; pinned: boolean }[]
}

export async function addWatchlist(code: string) {
  const { data } = await api.post('/watchlist', { code })
  return data
}

export async function removeWatchlist(code: string) {
  const { data } = await api.delete(`/watchlist/${code}`)
  return data
}

export async function setPinned(code: string, pinned: boolean) {
  const { data } = await api.patch(`/watchlist/${code}/pin`, { pinned })
  return data
}
