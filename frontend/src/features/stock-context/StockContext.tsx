import { createContext, ReactNode, useContext, useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

interface StockContextValue {
  code: string
  setCode: (code: string) => void
}

const StockContext = createContext<StockContextValue | null>(null)

export function StockContextProvider({ children }: { children: ReactNode }) {
  const params = useParams<{ code?: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [code, setCodeState] = useState<string>(params.code || '')

  useEffect(() => {
    if (params.code && params.code !== code) setCodeState(params.code)
  }, [params.code])

  const setCode = (c: string) => {
    const trimmed = c.trim()
    setCodeState(trimmed)
    const group = searchParams.get('group')
    const suffix = group ? `?group=${group}` : ''
    if (trimmed) navigate(`/stock/${trimmed}${suffix}`)
    else navigate(`/${suffix}`)
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
