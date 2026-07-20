import { generateAiReport, AiReportOptions } from './analysis'

export interface BatchProgress {
  total: number
  completed: number
  current: string | null
  errors: { code: string; error: string }[]
}

export type ProgressCallback = (progress: BatchProgress) => void

/**
 * 批量生成 AI 分析，带并发控制。
 * concurrency: 同时最多发几个请求（默认 2，避免触发 API 限流）
 */
export async function batchGenerateAiReports(
  codes: string[],
  opts: AiReportOptions = {},
  concurrency = 2,
  onProgress?: ProgressCallback,
): Promise<BatchProgress> {
  const progress: BatchProgress = {
    total: codes.length,
    completed: 0,
    current: null,
    errors: [],
  }

  const queue = [...codes]
  const running: Promise<void>[] = []

  const runOne = async () => {
    while (queue.length > 0) {
      const code = queue.shift()!
      progress.current = code
      onProgress?.(structuredClone(progress))
      try {
        await generateAiReport(code, opts)
      } catch (e: any) {
        progress.errors.push({ code, error: e?.message || '生成失败' })
      }
      progress.completed++
      onProgress?.(structuredClone(progress))
    }
  }

  for (let i = 0; i < Math.min(concurrency, codes.length); i++) {
    running.push(runOne())
  }
  await Promise.all(running)

  progress.current = null
  onProgress?.(structuredClone(progress))
  return progress
}
