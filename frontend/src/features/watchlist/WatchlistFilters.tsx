import { Input, Radio, Space } from 'antd'
import { DirFilter, SortKey } from './useWatchlistFilters'

interface Props {
  keyword: string
  onKeyword: (v: string) => void
  dir: DirFilter
  onDir: (v: DirFilter) => void
  sortKey: SortKey
  onSort: (v: SortKey) => void
}

export function WatchlistFilters({
  keyword,
  onKeyword,
  dir,
  onDir,
  sortKey,
  onSort,
}: Props) {
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Input.Search
        size="small"
        placeholder="过滤已添加"
        value={keyword}
        onChange={(e) => onKeyword(e.target.value)}
        allowClear
      />

      <Radio.Group
        size="small"
        value={dir}
        onChange={(e) => onDir(e.target.value)}
        style={{ display: 'flex' }}
      >
        <Radio.Button value="" style={{ flex: 1, textAlign: 'center' }}>全部</Radio.Button>
        <Radio.Button value="bullish" style={{ flex: 1, textAlign: 'center' }}>偏多</Radio.Button>
        <Radio.Button value="bearish" style={{ flex: 1, textAlign: 'center' }}>偏空</Radio.Button>
        <Radio.Button value="neutral" style={{ flex: 1, textAlign: 'center' }}>中性</Radio.Button>
      </Radio.Group>

      <Radio.Group
        size="small"
        value={sortKey}
        onChange={(e) => onSort(e.target.value)}
        style={{ display: 'flex' }}
      >
        <Radio.Button value="signal" style={{ flex: 1, textAlign: 'center' }}>信号</Radio.Button>
        <Radio.Button value="pctChg" style={{ flex: 1, textAlign: 'center' }}>涨幅</Radio.Button>
        <Radio.Button value="name" style={{ flex: 1, textAlign: 'center' }}>名称</Radio.Button>
      </Radio.Group>
    </Space>
  )
}
