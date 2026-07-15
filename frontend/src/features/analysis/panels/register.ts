/**
 * 面板自动注册。App 启动时 import 一次即可。
 * 加新面板：在此 push 一行 + 新增文件。AnalysisWorkspace 会渲染为 Tabs。
 */
import { ActionPlanPanel } from './ActionPlanPanel'
import { AiReportPanel } from './AiReportPanel'
import { ChatPanel } from './ChatPanel'
import { DiaryPanel } from './DiaryPanel'
import { IndicatorsPanel } from './IndicatorsPanel'
import { KLinePanel } from './KLinePanel'
import { registerPanel } from './registry'

registerPanel({ id: 'ai-report',   label: 'AI 分析',   order: 10, Component: AiReportPanel })
registerPanel({ id: 'action-plan', label: '操作指示', order: 15, Component: ActionPlanPanel })
registerPanel({ id: 'kline',       label: 'K 线',      order: 20, Component: KLinePanel })
registerPanel({ id: 'diary',       label: '分析日志', order: 25, Component: DiaryPanel })
registerPanel({ id: 'indicators',  label: '指标详情', order: 30, Component: IndicatorsPanel })
registerPanel({ id: 'chat',        label: '对话',     order: 35, Component: ChatPanel })
