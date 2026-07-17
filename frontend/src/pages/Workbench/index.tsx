import { AnalysisWorkspace } from '@/features/analysis'
import { StockContextProvider } from '@/features/stock-context'
import { WatchlistSidebar } from '@/features/watchlist'

export default function Workbench() {
  return (
    <StockContextProvider>
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 左栏保持固定高度 + 内部滚动，用户能看到全部自选股 */}
        <div
          style={{
            width: 320,
            flexShrink: 0,
            position: 'sticky',
            top: 12,
            height: 'calc(100vh - 112px)',
          }}
        >
          <WatchlistSidebar />
        </div>
        {/* 右栏独立滚动容器：切换股票时内部重渲染不影响外部页面滚动位置 */}
        <div style={{ flex: 1, minWidth: 0, height: 'calc(100vh - 112px)', overflowY: 'auto' }}>
          <AnalysisWorkspace />
        </div>
      </div>
    </StockContextProvider>
  )
}
