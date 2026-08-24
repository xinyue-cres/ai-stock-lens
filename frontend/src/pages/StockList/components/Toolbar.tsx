import { AutoComplete, Button, Dropdown, Input, Segmented, Typography } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, SortAscendingOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { searchStocks, StockInfo } from '@/api/stocks'
import { StockGroup } from '@/api/groups'
import { SortKey, SortDir, sortLabels } from '../constants'

const { Text } = Typography

interface ToolbarProps {
  search: string
  onSearchChange: (v: string) => void
  dirFilter: '' | 'bullish' | 'bearish' | 'neutral'
  onDirFilterChange: (v: '' | 'bullish' | 'bearish' | 'neutral') => void
  sortKey: SortKey
  onSortKeyChange: (k: SortKey) => void
  sortDir: SortDir
  onSortDirChange: (d: SortDir) => void
  addOpen: boolean
  onAddOpenChange: (open: boolean) => void
  addValue: string
  onAddValueChange: (v: string) => void
  onAddSelect: (code: string) => void
  addLoading: boolean
  syncLoading: boolean
  onSync: () => void
  selectMode: boolean
  onSelectModeToggle: () => void
  onSelectAll: () => void
  onSelectInvert: () => void
}

export default function Toolbar(props: ToolbarProps) {
  const {
    search, onSearchChange,
    dirFilter, onDirFilterChange,
    sortKey, onSortKeyChange,
    sortDir, onSortDirChange,
    addOpen, onAddOpenChange,
    addValue, onAddValueChange, onAddSelect, addLoading,
    syncLoading, onSync,
    selectMode, onSelectModeToggle, onSelectAll, onSelectInvert,
  } = props

  // 搜索联想防抖：拼音输入中间态（t/tia/tian'j）每键都会发请求，
  // 曾把后端连接池打爆（本地 miss 的拉丁字母每个都走 10-30s 远程兜底）。
  // 300ms 停顿才算一次输入；且 queryKey 用防抖值，未停顿的键不触发请求。
  const [debounced, setDebounced] = useState(addValue)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(addValue), 300)
    return () => clearTimeout(t)
  }, [addValue])

  const suggestQ = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => searchStocks(debounced),
    enabled: debounced.length >= 1,
  })

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
      <Input
        prefix={<SearchOutlined />}
        placeholder="搜索"
        size="small"
        style={{ width: 140 }}
        value={search}
        onChange={e => onSearchChange(e.target.value)}
        allowClear
      />
      <Segmented
        size="small"
        options={[
          { label: '全部', value: '' },
          { label: '偏多', value: 'bullish' },
          { label: '偏空', value: 'bearish' },
          { label: '中性', value: 'neutral' },
        ]}
        value={dirFilter}
        onChange={(v) => onDirFilterChange(v as any)}
      />
      <Dropdown
        menu={{
          items: (Object.keys(sortLabels) as SortKey[]).map(k => ({
            key: k,
            label: sortLabels[k],
            onClick: () => { onSortKeyChange(k) },
          })),
          selectedKeys: [sortKey],
        }}
        trigger={['click']}
      >
        <Button size="small" icon={<SortAscendingOutlined />}>
          {sortLabels[sortKey]}
        </Button>
      </Dropdown>
      {sortKey !== 'default' && (
        <Button
          size="small"
          icon={sortDir === 'desc' ? <ArrowDownOutlined /> : <ArrowUpOutlined />}
          onClick={() => onSortDirChange(sortDir === 'desc' ? 'asc' : 'desc')}
        />
      )}
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
        {addOpen ? (
          <AutoComplete
            autoFocus
            size="small"
            style={{ width: 180 }}
            placeholder="代码或名称"
            options={(suggestQ.data || []).map((s: StockInfo) => ({
              value: s.code,
              label: <span>{s.name} <Text type="secondary" style={{ fontSize: 11 }}>{s.code}</Text></span>,
            }))}
            value={addValue}
            onChange={onAddValueChange}
            onSelect={onAddSelect}
            onBlur={() => { if (!addValue) onAddOpenChange(false) }}
          />
        ) : (
          <Button size="small" icon={<PlusOutlined />} onClick={() => onAddOpenChange(true)}>添加</Button>
        )}
        <Button size="small" icon={<ReloadOutlined />} loading={syncLoading} onClick={onSync}>
          同步
        </Button>
        {selectMode && (
          <>
            <Button size="small" onClick={onSelectAll}>全选</Button>
            <Button size="small" onClick={onSelectInvert}>反选</Button>
          </>
        )}
        <Button
          size="small"
          type={selectMode ? 'primary' : 'default'}
          onClick={onSelectModeToggle}
        >
          {selectMode ? '退出多选' : '多选'}
        </Button>
      </div>
    </div>
  )
}
