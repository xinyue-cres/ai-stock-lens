import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getKline } from '@/api/stocks'
import { useStock } from './StockContext'

/**
 * 拉取当前股票的日线 + 指标 + 图表序列 + 信号。
 * placeholderData 保持高度防止页面上滚。
 */
export function useStockAnalysis() {
  const { code } = useStock()
  return useQuery({
    queryKey: ['kline', code],
    queryFn: () => getKline(code),
    enabled: !!code,
    staleTime: 10 * 60_000,
    gcTime: 30 * 60_000,
    placeholderData: keepPreviousData,
  })
}

/** 派生：当前股票名称。空则 null。 */
export function useStockName(): string | null {
  const { data } = useStockAnalysis()
  return data && !data.empty ? data.name || null : null
}
