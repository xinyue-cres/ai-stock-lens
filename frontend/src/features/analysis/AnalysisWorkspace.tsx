import { Card, Empty, Tabs } from 'antd'
import { useStock } from '@/features/stock-context'
import { KeyMetricsStrip } from './indicators/KeyMetricsStrip'
import './panels/register' // 触发面板注册
import { getPanels } from './panels/registry'

/**
 * 右栏容器：所有已注册面板作为 Tabs 展示。
 * - 只挂载当前激活的 Tab（destroyInactiveTabPane），避免全部并渲染的性能浪费
 * - 面板扩展 = 在 features/analysis/panels/ 下新增文件 + register.ts push 一行
 */
export function AnalysisWorkspace() {
  const { code } = useStock()
  const panels = getPanels()

  if (!code) {
    return (
      <Card>
        <Empty description="从左侧选择自选股，或在上方搜索任意 A 股" />
      </Card>
    )
  }

  return (
    <>
      <KeyMetricsStrip />
      <Tabs
        size="large"
        type="line"
        defaultActiveKey={panels[0]?.id}
        destroyInactiveTabPane
        tabBarStyle={{ marginBottom: 12, paddingLeft: 12 }}
        items={panels.map((p) => ({
          key: p.id,
          label: p.label,
          children: <p.Component />,
        }))}
      />
    </>
  )
}
