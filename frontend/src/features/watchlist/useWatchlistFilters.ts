import { useMemo, useState } from 'react'
import { SignalItem } from '@/api/signals'

export type DirFilter = '' | 'bullish' | 'bearish' | 'neutral'

function getItemDirection(item: SignalItem): string | undefined {
  if (item.ai_verdict) {
    if (item.ai_verdict === 'caution') return 'neutral'
    return item.ai_verdict
  }
  if (item.stance) {
    const v = item.stance.value
    if (v === 'opportunistic_buy') return 'bullish'
    if (v === 'exit' || v === 'reduce' || v === 'trim') return 'bearish'
    if (v === 'hold' || v === 'wait') return 'neutral'
    if (item.stance.source === 'ai') {
      if (v === 'caution') return 'neutral'
      return v
    }
  }
  return item.top_signal?.direction
}

export function useWatchlistFilters(items: SignalItem[]) {
  const [keyword, setKeyword] = useState('')
  const [dir, setDir] = useState<DirFilter>('')

  const filtered = useMemo(() => {
    let arr = items
    if (keyword) {
      const k = keyword.toLowerCase()
      arr = arr.filter((i) => i.code.includes(k) || (i.name || '').toLowerCase().includes(k))
    }
    if (dir) arr = arr.filter((i) => getItemDirection(i) === dir)

    const sorted = [...arr]
    sorted.sort((a, b) => {
      const wa = a.top_signal?.weight ?? 0
      const wb = b.top_signal?.weight ?? 0
      if (wb !== wa) return wb - wa
      return (b.signals?.length ?? 0) - (a.signals?.length ?? 0)
    })
    return sorted.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
  }, [items, keyword, dir])

  return { filtered, keyword, setKeyword, dir, setDir }
}
