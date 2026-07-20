import { useQuery } from '@tanstack/react-query'
import { getTodaySignals, SignalItem } from '@/api/signals'

export function useSignalsQuery() {
  const query = useQuery({
    queryKey: ['signals-today'],
    queryFn: () => getTodaySignals(),
    refetchInterval: (q) => {
      const items = (q.state.data as any)?.items ?? []
      return items.some((i: any) => i.empty) ? 3_000 : 5 * 60_000
    },
  })

  const items: SignalItem[] = query.data?.items ?? []

  return { ...query, items }
}
