import type { ComponentType } from 'react'

export interface PanelDef {
  id: string
  /** Tab 标签文本 */
  label: string
  /** 显示顺序，越小越靠前 */
  order: number
  /** Panel 组件，从 useStock() 拿 code，无 props */
  Component: ComponentType
}

/**
 * 全局面板注册表。加新面板 = 新增文件 + registerPanel(...)。
 * AnalysisWorkspace 按 order 排序，以 Tabs 形式渲染。
 */
const registry: PanelDef[] = []

export function registerPanel(def: PanelDef): void {
  const idx = registry.findIndex((p) => p.id === def.id)
  if (idx >= 0) registry[idx] = def
  else registry.push(def)
}

export function getPanels(): PanelDef[] {
  return [...registry].sort((a, b) => a.order - b.order)
}
