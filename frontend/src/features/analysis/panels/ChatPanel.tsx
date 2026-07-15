import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from 'antd'
import { ClearOutlined, MessageOutlined } from '@ant-design/icons'
import { useStock } from '@/features/stock-context'
import { InputArea } from '../chat/InputArea'
import { MessageList } from '../chat/MessageList'
import { ChatMessage, QUICK_STARTERS } from '../chat/types'

const STORAGE_KEY_PREFIX = 'chat_messages_'

function loadMessages(code: string): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY_PREFIX + code)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveMessages(code: string, messages: ChatMessage[]) {
  try {
    if (messages.length === 0) {
      sessionStorage.removeItem(STORAGE_KEY_PREFIX + code)
    } else {
      sessionStorage.setItem(STORAGE_KEY_PREFIX + code, JSON.stringify(messages))
    }
  } catch { /* quota exceeded — ignore */ }
}

export function ChatPanel() {
  const { code } = useStock()
  const [messages, setMessages] = useState<ChatMessage[]>(() => code ? loadMessages(code) : [])
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const prevCodeRef = useRef(code)

  // 切换股票时加载对应历史
  if (code !== prevCodeRef.current) {
    prevCodeRef.current = code
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setStreaming(false)
    setMessages(code ? loadMessages(code) : [])
  }

  // messages 变化时持久化
  useEffect(() => {
    if (code) saveMessages(code, messages)
  }, [code, messages])

  const sendMessage = useCallback(
    async (userMsg: string) => {
      if (!code || streaming) return

      const userMessage: ChatMessage = { role: 'user', content: userMsg }
      const newMessages = [...messages, userMessage]
      const assistantMessage: ChatMessage = { role: 'assistant', content: '' }
      setMessages([...newMessages, assistantMessage])
      setStreaming(true)

      // 只有第一轮（之前无历史）才注入完整上下文
      const injectContext = messages.length === 0

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const resp = await fetch(`/api/stocks/${code}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: newMessages, inject_context: injectContext }),
          signal: controller.signal,
        })

        if (!resp.ok || !resp.body) {
          setMessages((prev) => {
            const copy = [...prev]
            copy[copy.length - 1] = { role: 'assistant', content: '请求失败，请重试' }
            return copy
          })
          setStreaming(false)
          return
        }

        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let accumulated = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const text = decoder.decode(value, { stream: true })
          const lines = text.split('\n')

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const payload = line.slice(6)
            if (payload === '[DONE]') continue

            try {
              const parsed = JSON.parse(payload)
              if (parsed.content) {
                accumulated += parsed.content
                setMessages((prev) => {
                  const copy = [...prev]
                  copy[copy.length - 1] = { role: 'assistant', content: accumulated }
                  return copy
                })
              }
              if (parsed.error) {
                accumulated += `\n[错误: ${parsed.error}]`
                setMessages((prev) => {
                  const copy = [...prev]
                  copy[copy.length - 1] = { role: 'assistant', content: accumulated }
                  return copy
                })
              }
            } catch {
              // ignore malformed chunks
            }
          }
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          setMessages((prev) => {
            const copy = [...prev]
            copy[copy.length - 1] = { role: 'assistant', content: '连接中断，请重试' }
            return copy
          })
        }
      } finally {
        setStreaming(false)
        abortRef.current = null
      }
    },
    [code, messages, streaming],
  )

  const handleClear = () => {
    setMessages([])
    if (code) sessionStorage.removeItem(STORAGE_KEY_PREFIX + code)
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setStreaming(false)
  }

  return (
    <div
      style={{
        position: 'relative',
        height: 'calc(100vh - 280px)',
        minHeight: 300,
        display: 'flex',
        flexDirection: 'column',
        background: '#fff',
        borderRadius: 8,
        border: '1px solid #f0f0f0',
        overflow: 'hidden',
      }}
    >
      {/* 消息区：内部滚动 */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {messages.length === 0 ? (
          <div
            style={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
              padding: 24,
              gap: 20,
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                background: '#f0f5ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 22,
                color: '#1677ff',
              }}
            >
              <MessageOutlined />
            </div>
            <div style={{ color: '#666', fontSize: 13, textAlign: 'center' }}>
              基于已有分析报告，自由提问
            </div>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 8,
                justifyContent: 'center',
                maxWidth: 380,
              }}
            >
              {QUICK_STARTERS.map((q) => (
                <div
                  key={q}
                  onClick={() => sendMessage(q)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 16,
                    border: '1px solid #e8e8e8',
                    background: '#fff',
                    fontSize: 12,
                    color: '#555',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#1677ff'
                    e.currentTarget.style.color = '#1677ff'
                    e.currentTarget.style.background = '#f0f5ff'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = '#e8e8e8'
                    e.currentTarget.style.color = '#555'
                    e.currentTarget.style.background = '#fff'
                  }}
                >
                  {q}
                </div>
              ))}
            </div>
            <div style={{ color: '#bbb', fontSize: 11 }}>仅供讨论，不触发任何操作</div>
          </div>
        ) : (
          <MessageList messages={messages} streaming={streaming} />
        )}
      </div>

      {/* 输入区：固定在卡片底部 */}
      <div
        style={{
          flexShrink: 0,
          padding: '10px 12px 12px',
          background: '#fff',
          borderTop: '1px solid #f0f0f0',
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
        }}
      >
        <div style={{ flex: 1 }}>
          <InputArea onSend={sendMessage} disabled={streaming} />
        </div>
        {messages.length > 0 && (
          <Button
            size="small"
            type="text"
            icon={<ClearOutlined />}
            onClick={handleClear}
            style={{ color: '#999', flexShrink: 0 }}
          />
        )}
      </div>
    </div>
  )
}
