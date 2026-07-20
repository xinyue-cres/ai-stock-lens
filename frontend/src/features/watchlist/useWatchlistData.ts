import { useMutation, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { addWatchlist, removeWatchlist, setPinned } from '@/api/watchlist'
import { runSync } from '@/api/sync'
import { useStock } from '@/features/stock-context'
import { useSignalsQuery } from '@/hooks/useSignalsQuery'

export function useWatchlistData() {
  const qc = useQueryClient()
  const { setCode } = useStock()

  const { items, isLoading } = useSignalsQuery()

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['watchlist'] })
    qc.invalidateQueries({ queryKey: ['signals-today'] })
  }

  const addMut = useMutation({
    mutationFn: (code: string) => addWatchlist(code),
    onSuccess: (d) => {
      message.success(`已加入 ${d.name || d.code}，同步中…`)
      invalidate()
      // 自动选中新加的票；右栏会自己 loading 到数据就绪
      if (d.code) setCode(d.code)
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '添加失败'),
  })

  const rmMut = useMutation({
    mutationFn: (code: string) => removeWatchlist(code),
    onSuccess: (_d, code) => {
      message.success(`已移除 ${code}`)
      invalidate()
    },
  })

  const pinMut = useMutation({
    mutationFn: ({ code, pinned }: { code: string; pinned: boolean }) => setPinned(code, pinned),
    onSuccess: (_d, v) => {
      message.success(v.pinned ? '已置顶' : '已取消置顶')
      invalidate()
    },
  })

  const syncMut = useMutation({
    mutationFn: runSync,
    onSuccess: (d) => {
      message.success(`同步完成 · ${d.stocks_synced} 只`)
      qc.invalidateQueries({ queryKey: ['signals-today'] })
    },
  })

  return {
    items,
    loading: isLoading,
    add: addMut.mutate,
    addLoading: addMut.isPending,
    remove: rmMut.mutate,
    pin: (code: string, pinned: boolean) => pinMut.mutate({ code, pinned }),
    sync: syncMut.mutate,
    syncLoading: syncMut.isPending,
  }
}
