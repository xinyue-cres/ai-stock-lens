import { useState } from 'react'
import { Card, Empty } from 'antd'
import { useStock } from '@/features/stock-context'
import { PositionEditModal } from './PositionEditModal'
import { WatchlistFilters } from './WatchlistFilters'
import { WatchlistItem } from './WatchlistItem'
import { WatchlistToolbar } from './WatchlistToolbar'
import { useWatchlistData } from './useWatchlistData'
import { useWatchlistFilters } from './useWatchlistFilters'

/**
 * 左栏：自选股 + 信号扫描 + 添加/同步/过滤/排序 + 单条 ⋯ 菜单。
 * 通过 StockContext 拿到 activeCode / 设置新 code。
 */
export function WatchlistSidebar() {
  const { code, setCode } = useStock()
  const { items, add, remove, pin, sync, syncLoading } = useWatchlistData()
  const { filtered, keyword, setKeyword, dir, setDir } =
    useWatchlistFilters(items)
  const [editingCode, setEditingCode] = useState<string | null>(null)
  const editingItem = editingCode ? items.find((i) => i.code === editingCode) : null

  return (
    <Card
      size="small"
      styles={{ body: { padding: 0, height: '100%', display: 'flex', flexDirection: 'column' } }}
      style={{ height: '100%', overflow: 'hidden' }}
    >
      <div style={{ padding: 10, borderBottom: '1px solid #f0f0f0' }}>
        <WatchlistToolbar
          total={items.length}
          syncLoading={syncLoading}
          onAdd={add}
          onSync={sync}
        />
        <div style={{ marginTop: 8 }}>
          <WatchlistFilters
            keyword={keyword}
            onKeyword={setKeyword}
            dir={dir}
            onDir={setDir}
          />
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {filtered.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={items.length === 0 ? '还没有自选股' : '当前筛选无结果'}
            style={{ padding: '30px 10px' }}
          />
        )}
        {filtered.map((item) => (
          <WatchlistItem
            key={item.code}
            item={item}
            active={item.code === code}
            onSelect={setCode}
            onPin={pin}
            onRemove={remove}
            onEditPosition={setEditingCode}
          />
        ))}
      </div>

      <PositionEditModal
        code={editingCode || ''}
        name={editingItem?.name}
        open={!!editingCode}
        onClose={() => setEditingCode(null)}
      />
    </Card>
  )
}
