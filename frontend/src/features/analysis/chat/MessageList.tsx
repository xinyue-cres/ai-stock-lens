import { useEffect, useRef } from 'react'
import Markdown from 'react-markdown'
import { LoadingOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons'
import type { ChatMessage } from './types'

export function MessageList({ messages, streaming }: { messages: ChatMessage[]; streaming?: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) return null

  return (
    <div style={{ padding: '16px 12px 8px' }}>
      {messages.map((msg, i) => {
        const isUser = msg.role === 'user'
        const isLast = i === messages.length - 1
        const isThinking = !isUser && isLast && streaming && !msg.content

        return (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: 10,
              marginBottom: 16,
              flexDirection: isUser ? 'row-reverse' : 'row',
              alignItems: 'flex-start',
            }}
          >
            <div
              style={{
                width: 26,
                height: 26,
                borderRadius: '50%',
                background: isUser ? '#1677ff' : '#f0f5ff',
                border: isUser ? 'none' : '1px solid #d6e4ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                fontSize: 12,
                color: isUser ? '#fff' : '#1677ff',
              }}
            >
              {isUser ? <UserOutlined /> : <RobotOutlined />}
            </div>

            <div
              style={{
                maxWidth: '80%',
                padding: isUser ? '8px 12px' : '10px 14px',
                borderRadius: isUser ? '12px 2px 12px 12px' : '2px 12px 12px 12px',
                background: isUser ? '#1677ff' : '#ffffff',
                color: isUser ? '#fff' : '#1f1f1f',
                boxShadow: isUser ? 'none' : '0 1px 3px rgba(0,0,0,0.05)',
                border: isUser ? 'none' : '1px solid #f0f0f0',
                fontSize: 13,
                lineHeight: 1.7,
                wordBreak: 'break-word',
              }}
            >
              {isThinking ? (
                <span style={{ color: '#999', fontStyle: 'italic', fontSize: 12 }}>
                  <LoadingOutlined style={{ marginRight: 6 }} />
                  思考中...
                </span>
              ) : isUser ? (
                <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
              ) : (
                <div className="chat-md">
                  <Markdown>{msg.content}</Markdown>
                </div>
              )}
            </div>
          </div>
        )
      })}
      <div ref={bottomRef} />

      <style>{`
        .chat-md p { margin: 0 0 8px; }
        .chat-md p:last-child { margin-bottom: 0; }
        .chat-md ul, .chat-md ol { margin: 4px 0; padding-left: 18px; }
        .chat-md li { margin: 2px 0; }
        .chat-md code {
          background: #f5f5f5;
          padding: 1px 4px;
          border-radius: 3px;
          font-size: 12px;
        }
        .chat-md pre {
          background: #f8f8f8;
          padding: 8px 10px;
          border-radius: 6px;
          overflow-x: auto;
          font-size: 12px;
          margin: 6px 0;
        }
        .chat-md pre code { background: none; padding: 0; }
        .chat-md strong { font-weight: 600; }
        .chat-md h1, .chat-md h2, .chat-md h3 {
          font-size: 13px;
          font-weight: 600;
          margin: 8px 0 4px;
        }
        .chat-md blockquote {
          margin: 4px 0;
          padding-left: 10px;
          border-left: 3px solid #d9d9d9;
          color: #666;
        }
      `}</style>
    </div>
  )
}
