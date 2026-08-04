import { useState } from 'react'
import { Alert } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { getAiConfig } from '@/api/settings'

/** 无 AI Key 引导条：首次启动提示去右上角设置，点击打开设置抽屉。
 *
 * 与 SettingsDrawer 共享 ['ai-config'] 查询缓存——保存 key 后自动消失。
 */
export function AiKeyBanner({ onOpenSettings }: { onOpenSettings: () => void }) {
  const configQ = useQuery({ queryKey: ['ai-config'], queryFn: getAiConfig })
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || configQ.isLoading || configQ.data?.has_api_key) return null

  return (
    <Alert
      type="warning"
      showIcon
      banner
      closable
      onClose={() => setDismissed(true)}
      message={
        <span>
          尚未配置 AI Key，AI 分析 / 点评等功能暂不可用。{' '}
          <a onClick={onOpenSettings} style={{ fontWeight: 600, color: '#b45309' }}>
            去设置 →
          </a>
        </span>
      }
      style={{ marginBottom: 12 }}
    />
  )
}
