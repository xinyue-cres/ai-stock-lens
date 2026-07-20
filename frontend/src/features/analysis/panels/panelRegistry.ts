import type { ComponentType } from 'react'
import { ActionPlanPanel } from './ActionPlanPanel'
import { AiReportPanel } from './AiReportPanel'
import { ChatPanel } from './ChatPanel'
import { DiaryPanel } from './DiaryPanel'
import { IndicatorsPanel } from './IndicatorsPanel'
import { KLinePanel } from './KLinePanel'

export interface PanelDef {
  id: string
  label: string
  order: number
  Component: ComponentType
}

const registry: PanelDef[] = [
  { id: 'ai-report',   label: 'AI 分析',   order: 10, Component: AiReportPanel },
  { id: 'action-plan', label: '操作指示', order: 15, Component: ActionPlanPanel },
  { id: 'kline',       label: 'K 线',      order: 20, Component: KLinePanel },
  { id: 'diary',       label: '分析日志', order: 25, Component: DiaryPanel },
  { id: 'indicators',  label: '指标详情', order: 30, Component: IndicatorsPanel },
  { id: 'chat',        label: '对话',     order: 35, Component: ChatPanel },
]

export function registerPanel(def: PanelDef): void {
  const idx = registry.findIndex((p) => p.id === def.id)
  if (idx >= 0) registry[idx] = def
  else registry.push(def)
}

export function getPanels(): PanelDef[] {
  return [...registry].sort((a, b) => a.order - b.order)
}
