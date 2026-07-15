import { createContext, ReactNode, useContext, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

interface StockContextValue {
  code: string
  setCode: (code: string) => void
}

const StockContext = createContext<StockContextValue | null>(null)

/**
 * 提供当前股票 code 的全局上下文。
 * - 与 URL /stock/:code 双向绑定
 * - 所有面板通过 useStock() 拿到当前 code，不用逐层传 prop
 */
export function StockContextProvider({ children }: { children: ReactNode }) {
  const params = useParams<{ code?: string }>()
  const navigate = useNavigate()
  const [code, setCodeState] = useState<string>(params.code || '')

  useEffect(() => {
    if (params.code && params.code !== code) setCodeState(params.code)
  }, [params.code])

  const setCode = (c: string) => {
    const trimmed = c.trim()
    setCodeState(trimmed)
    if (trimmed) navigate(`/stock/${trimmed}`)
    else navigate('/')
  }

  return (
    <StockContext.Provider value={{ code, setCode }}>{children}</StockContext.Provider>
  )
}

export function useStock(): StockContextValue {
  const ctx = useContext(StockContext)
  if (!ctx) throw new Error('useStock 必须在 <StockContextProvider> 内使用')
  return ctx
}
