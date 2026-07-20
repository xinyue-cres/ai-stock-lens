import { Button } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AnalysisWorkspace } from '@/features/analysis'
import { StockContextProvider } from '@/features/stock-context'
import { WatchlistSidebar } from '@/features/watchlist'

export default function StockDetail() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const groupId = searchParams.get('group') ? Number(searchParams.get('group')) : null

  return (
    <StockContextProvider>
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <div
          style={{
            width: 320,
            flexShrink: 0,
            position: 'sticky',
            top: 12,
            height: 'calc(100vh - 112px)',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(groupId ? `/?group=${groupId}` : '/')}
            style={{ alignSelf: 'flex-start', marginBottom: 8 }}
          >
            返回列表
          </Button>
          <div style={{ flex: 1, minHeight: 0 }}>
            <WatchlistSidebar groupId={groupId} />
          </div>
        </div>
        <div style={{ flex: 1, minWidth: 0, minHeight: 'calc(100vh - 112px)' }}>
          <AnalysisWorkspace />
        </div>
      </div>
    </StockContextProvider>
  )
}
