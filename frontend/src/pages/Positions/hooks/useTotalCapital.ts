/** 当前总资金（CapitalCard 与汇总卡共用，react-query 同 key 自动去重）。 */
import { useQuery } from '@tanstack/react-query'
import { getCapital } from '@/api/settings'

export function useTotalCapital() {
  const capitalQ = useQuery({
    queryKey: ['total-capital'],
    queryFn: getCapital,
  })
  return capitalQ.data?.total_capital ?? null
}
