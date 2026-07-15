import { useRef, useState } from 'react'
import { Button, Input } from 'antd'
import { SendOutlined } from '@ant-design/icons'

const { TextArea } = Input

interface Props {
  onSend: (text: string) => void
  disabled?: boolean
}

export function InputArea({ onSend, disabled }: Props) {
  const [value, setValue] = useState('')
  const composingRef = useRef(false)

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  return (
    <div
      style={{
        display: 'flex',
        gap: 8,
        alignItems: 'flex-end',
        padding: '10px 12px',
        background: '#fafafa',
        borderRadius: 8,
        border: '1px solid #f0f0f0',
      }}
    >
      <TextArea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onCompositionStart={() => { composingRef.current = true }}
        onCompositionEnd={() => { composingRef.current = false }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !composingRef.current) {
            e.preventDefault()
            handleSend()
          }
        }}
        placeholder="输入你的问题...（Enter 发送，Shift+Enter 换行）"
        autoSize={{ minRows: 1, maxRows: 4 }}
        disabled={disabled}
        variant="borderless"
        style={{ flex: 1, background: 'transparent', fontSize: 13 }}
      />
      <Button
        type="primary"
        shape="circle"
        size="small"
        icon={<SendOutlined style={{ fontSize: 12 }} />}
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        style={{ flexShrink: 0 }}
      />
    </div>
  )
}
