import { Alert } from 'antd'

interface Props {
  reflection?: string | null
}

/** 反思高亮：AI 基于上次报告 + 复盘给出的修正要点。 */
export function ReflectionBanner({ reflection }: Props) {
  if (!reflection) return null
  return (
    <Alert
      type="info"
      showIcon
      message="AI 回顾修正"
      description={reflection}
      style={{ background: '#f0f9ff', border: '1px solid #bae6fd' }}
    />
  )
}
