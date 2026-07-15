export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export const QUICK_STARTERS = [
  '为什么当前操作指示建议这样做？',
  '如果明天放量突破 MA20 该怎么办？',
  '当前最大的风险是什么？',
  '各个分析视角有冲突吗？',
]
