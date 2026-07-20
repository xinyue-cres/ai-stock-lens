import { useState } from 'react'
import { Button, Layout, Menu, Tooltip } from 'antd'
import { SettingOutlined } from '@ant-design/icons'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import Positions from './pages/Positions'
import StockDetail from './pages/StockDetail'
import StockList from './pages/StockList'
import SyncLogs from './pages/SyncLogs'
import { SettingsDrawer } from './features/settings'
import { GlobalStatusBar } from './features/status-bar'

const { Header, Content } = Layout

function selectedKey(pathname: string): string {
  if (pathname.startsWith('/positions')) return 'positions'
  if (pathname.startsWith('/sync')) return 'sync'
  return 'workbench'
}

export default function App() {
  const location = useLocation()
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{ color: '#fff', fontWeight: 700, marginRight: 32, fontSize: 16 }}>
          个股分析
        </div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey(location.pathname)]}
          items={[
            { key: 'workbench', label: <Link to="/">工作台</Link> },
            { key: 'positions', label: <Link to="/positions">持仓</Link> },
            { key: 'sync', label: <Link to="/sync">任务状态</Link> },
          ]}
          style={{ flex: 1, minWidth: 0 }}
        />
        <GlobalStatusBar />
        <Tooltip title="设置">
          <Button
            type="text"
            icon={<SettingOutlined style={{ color: '#fff', fontSize: 18 }} />}
            onClick={() => setSettingsOpen(true)}
            style={{ marginLeft: 8 }}
          />
        </Tooltip>
      </Header>
      <Content style={{ padding: 16 }}>
        <Routes>
          <Route path="/" element={<StockList />} />
          <Route path="/stock/:code" element={<StockDetail />} />
          <Route path="/positions" element={<Positions />} />
          <Route path="/sync" element={<SyncLogs />} />
        </Routes>
      </Content>
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </Layout>
  )
}
