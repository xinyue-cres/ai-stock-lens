import { useMemo, useState } from 'react'
import { SignalItem } from '@/api/signals'

export type SortKey = 'signal' | 'pctChg' | 'name'
export type DirFilter = '' | 'bullish' | 'bearish' | 'neutral'

/**
 * 从 item 的 ai_verdict / stance 推导方向，用于过滤按钮。
 * 优先看 ai_verdict（对应右上角的主标签），其次看 stance.value 映射。
 */
function getItemDirection(item: SignalItem): string | undefined {
  // ai_verdict 直接就是 bullish/bearish/neutral/caution
  if (item.ai_verdict) {
    if (item.ai_verdict === 'caution') return 'neutral'
    return item.ai_verdict
  }
  // fallback: stance.value 映射
  if (item.stance) {
    const v = item.stance.value
    if (v === 'opportunistic_buy') return 'bullish'
    if (v === 'exit' || v === 'reduce' || v === 'trim') return 'bearish'
    if (v === 'hold' || v === 'wait') return 'neutral'
    // source=ai 时 value 就是 verdict
    if (item.stance.source === 'ai') {
      if (v === 'caution') return 'bearish'
      return v
    }
  }
  // 最后 fallback top_signal
  return item.top_signal?.direction
}

/**
 * 自选股列表的过滤/排序状态与结果。
 * - keyword: 名称/代码模糊过滤
 * - dir: 按 ai_verdict 方向过滤
 * - sortKey: 排序键（信号权重 / 涨幅 / 名称）
 * - 置顶项永远优先排在最前
 */
export function useWatchlistFilters(items: SignalItem[]) {
  const [keyword, setKeyword] = useState('')
  const [dir, setDir] = useState<DirFilter>('')
  const [sortKey, setSortKey] = useState<SortKey>('signal')

  const filtered = useMemo(() => {
    let arr = items
    if (keyword) {
      const k = keyword.toLowerCase()
      arr = arr.filter((i) => i.code.includes(k) || (i.name || '').toLowerCase().includes(k))
    }
    if (dir) arr = arr.filter((i) => getItemDirection(i) === dir)

    const sorted = [...arr]
    if (sortKey === 'pctChg') {
      sorted.sort((a, b) => (b.pct_chg ?? -Infinity) - (a.pct_chg ?? -Infinity))
    } else if (sortKey === 'name') {
      sorted.sort((a, b) => (a.name || a.code).localeCompare(b.name || b.code, 'zh'))
    } else {
      sorted.sort((a, b) => {
        const wa = a.top_signal?.weight ?? 0
        const wb = b.top_signal?.weight ?? 0
        if (wb !== wa) return wb - wa
        return (b.signals?.length ?? 0) - (a.signals?.length ?? 0)
      })
    }
    // 置顶稳定排到最前
    return sorted.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
  }, [items, keyword, dir, sortKey])

  return { filtered, keyword, setKeyword, dir, setDir, sortKey, setSortKey }
}
