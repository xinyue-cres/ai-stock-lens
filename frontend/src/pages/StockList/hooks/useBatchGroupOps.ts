/** 批量分组操作：加入/移出/清除三组 Promise.all 编排收敛为一个 applyGroupOp。
 *
 * 从 BatchActionBar 抽出（原 3 个 Dropdown 各自内嵌 ~40 行重复业务）。
 * 乐观更新：patchStock 成功后先改 signals-today 缓存里的 group_ids，
 * 让列表和 toast 同时翻新；invalidate 正常后台走。
 */
import { useCallback } from 'react'
import { message } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { patchStock } from '@/api/groups'
import type { SignalItem } from '@/api/signals'

type Op = 'add' | 'remove' | 'clear'

export function useBatchGroupOps(
  selected: Set<string>,
  allItems: SignalItem[],
  onDone: () => void,
) {
  const qc = useQueryClient()

  const invalidateBoth = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['signals-today'] })
    qc.invalidateQueries({ queryKey: ['groups'] })
  }, [qc])

  /** 乐观更新 signals-today 缓存里的 group_ids（等 /api/signals/today 慢拉 ~2.15s 期间
   * 用户会看到"toast 已消失，数据刚变"的滞后感，先改缓存消除）。 */
  const applyOptimisticGroupIds = useCallback((codes: string[], computeIds: (cur: number[]) => number[]) => {
    const set = new Set(codes)
    qc.setQueryData(['signals-today'], (old: any) => {
      if (!old?.items) return old
      return {
        ...old,
        items: old.items.map((it: any) => {
          if (!set.has(it.code)) return it
          return { ...it, group_ids: computeIds(it.group_ids || []) }
        }),
      }
    })
    invalidateBoth()
  }, [qc, invalidateBoth])

  /** 统一编排：对 selected 逐只 patch group_ids，按操作类型跳过已满足/不满足的票，
   * 汇总"生效数/跳过数"给 toast。 */
  const applyGroupOp = useCallback((op: Op, groupId?: number, groupName = '') => {
    Promise.all([...selected].map(code => {
      const cur = allItems.find(i => i.code === code)
      const curIds = cur?.group_ids || []
      if (op === 'add') {
        if (curIds.includes(groupId!)) return 'skip'
        return patchStock(code, { group_ids: [...curIds, groupId!] }).then(() => 'ok')
      }
      if (op === 'remove') {
        if (!curIds.includes(groupId!)) return 'skip'
        return patchStock(code, { group_ids: curIds.filter(id => id !== groupId) }).then(() => 'ok')
      }
      return patchStock(code, { group_ids: [] }).then(() => 'ok')  // clear
    })).then((rs) => {
      const ok = rs.filter(r => r === 'ok').length
      const skip = rs.filter(r => r === 'skip').length
      const verb = op === 'add' ? '已加入' : op === 'remove' ? '已移出' : ''
      if (op === 'clear') {
        message.success('已清除所有分组')
      } else if (ok > 0 && skip > 0) {
        message.success(`${ok} 只${verb}「${groupName}」，${skip} 只${op === 'add' ? '已在组内' : '不在组内'}跳过`)
      } else if (ok > 0) {
        message.success(`${ok} 只${verb}「${groupName}」`)
      } else {
        message.info(`所选均${op === 'add' ? '已在该组内' : '不在该组内'}，无变更`)
      }
      onDone()
      if (ok > 0) {
        if (op === 'add') applyOptimisticGroupIds([...selected], (ids) => [...new Set([...ids, groupId!])])
        else if (op === 'remove') applyOptimisticGroupIds([...selected], (ids) => ids.filter(id => id !== groupId))
        else applyOptimisticGroupIds([...selected], () => [])
      } else {
        invalidateBoth()
      }
    }).catch(() => message.error('批量分组操作失败'))
  }, [selected, allItems, onDone, applyOptimisticGroupIds, invalidateBoth])

  return { addToGroup: applyGroupOp, removeFromGroup: applyGroupOp, clearAllGroups: applyGroupOp, invalidateBoth }
}
