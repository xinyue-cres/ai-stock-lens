import { api } from './client'

export interface ProviderPreset {
  id: string
  name: string
  base_url: string
  default_model: string
  docs_url: string
}

export interface AiConfigPublic {
  provider: string | null
  base_url: string | null
  model: string | null
  api_key_masked: string
  has_api_key: boolean
}

export interface AiConfigPayload {
  provider?: string
  base_url?: string
  model?: string
  api_key?: string
}

export interface AiTestResult {
  ok: boolean
  model?: string
  reply?: string
  error?: string
}

export async function getPresets(): Promise<ProviderPreset[]> {
  const { data } = await api.get<ProviderPreset[]>('/settings/presets')
  return data
}

export async function getAiConfig(): Promise<AiConfigPublic> {
  const { data } = await api.get<AiConfigPublic>('/settings/ai')
  return data
}

export async function saveAiConfig(payload: AiConfigPayload): Promise<AiConfigPublic> {
  const { data } = await api.put<AiConfigPublic>('/settings/ai', payload)
  return data
}

export async function testAiConfig(payload: {
  provider?: string
  base_url: string
  model: string
  api_key: string
}): Promise<AiTestResult> {
  const { data } = await api.post<AiTestResult>('/settings/ai/test', payload)
  return data
}

// ---- 总资金 ----

export async function getCapital(): Promise<{ total_capital: number | null }> {
  const { data } = await api.get('/settings/capital')
  return data
}

export async function saveCapital(amount: number): Promise<{ total_capital: number }> {
  const { data } = await api.put('/settings/capital', { amount })
  return data
}
