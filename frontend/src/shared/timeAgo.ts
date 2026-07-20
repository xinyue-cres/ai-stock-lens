/**
 * 把 ISO 时间字符串转为"X天Y时Z分前"的相对时间。
 * 用于 AI 报告和操作指示的生成时间展示。
 */
export function timeAgo(isoOrDate: string | Date | null | undefined): string | null {
  if (!isoOrDate) return null
  const target = typeof isoOrDate === 'string' ? new Date(isoOrDate) : isoOrDate
  if (isNaN(target.getTime())) return null
  const diff = Date.now() - target.getTime()
  if (diff < 0) return '刚刚'

  const minutes = Math.floor(diff / 60_000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) {
    const remHours = hours - days * 24
    return remHours > 0 ? `${days}天${remHours}时前` : `${days}天前`
  }
  if (hours > 0) {
    const remMin = minutes - hours * 60
    return remMin > 0 ? `${hours}时${remMin}分前` : `${hours}时前`
  }
  if (minutes > 0) return `${minutes}分前`
  return '刚刚'
}

export function timeAgoShort(isoOrDate: string | Date | null | undefined): string {
  if (!isoOrDate) return '--'
  const target = typeof isoOrDate === 'string' ? new Date(isoOrDate.replace(' ', 'T')) : isoOrDate
  if (isNaN(target.getTime())) return '--'
  const diff = Date.now() - target.getTime()
  if (diff < 60_000) return '刚刚'
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}

export function timeDiffHours(isoOrDate: string | Date | null | undefined): number {
  if (!isoOrDate) return Infinity
  const target = typeof isoOrDate === 'string' ? new Date(isoOrDate.replace(' ', 'T')) : isoOrDate
  if (isNaN(target.getTime())) return Infinity
  return (Date.now() - target.getTime()) / 3_600_000
}
