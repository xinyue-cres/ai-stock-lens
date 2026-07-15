import { Alert, Spin } from 'antd'
import { useEffect, useRef } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'
import { useStockAnalysis } from '@/features/stock-context'
import { priceColor } from '@/shared/theme'

const MA_COLORS: Record<string, string> = {
  ma5: '#f59e0b',
  ma10: '#3b82f6',
  ma20: '#8b5cf6',
  ma60: '#ec4899',
}

const DEFAULT_BARS = 120 // 约 6 个月交易日
const RIGHT_BLANK_RATIO = 0.3 // 右侧留白占视野比例
const RIGHT_OFFSET_BARS = Math.ceil((DEFAULT_BARS * RIGHT_BLANK_RATIO) / (1 - RIGHT_BLANK_RATIO)) // ≈51

/** K 线主图 + 成交量副图 + 4 条 MA 叠加线；默认展示最近 6 个月，右侧留 30% 空白。
 *
 * 实现说明：chart 创建 + setData 合并到同一个 effect（依赖 data）。
 * 这样 StrictMode 双 mount / 展开切换 都不会出现"chart 建好但 data 没上"的空档。
 * 代价是 data 变化时 chart 重建，但 data 变化不频繁（切股/手动同步后），可接受。
 */
export function KLineChart() {
  const containerRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, error } = useStockAnalysis()

  useEffect(() => {
    if (!containerRef.current) return
    if (!data || data.empty || !data.series) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth || 800,
      height: 520,
      layout: { background: { color: '#fff' }, textColor: '#333' },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      timeScale: {
        timeVisible: false,
        secondsVisible: false,
        borderColor: '#d1d5db',
        rightOffset: RIGHT_OFFSET_BARS,
      },
      rightPriceScale: { borderColor: '#d1d5db', scaleMargins: { top: 0.05, bottom: 0.25 } },
      crosshair: { mode: 1 },
    })

    const candle = chart.addCandlestickSeries({
      upColor: priceColor.up,
      downColor: priceColor.down,
      wickUpColor: priceColor.up,
      wickDownColor: priceColor.down,
      borderVisible: false,
    })

    const volume = chart.addHistogramSeries({
      priceFormat: {
        type: 'custom',
        formatter: (v: number) => formatVolumeHand(v),
        minMove: 1,
      },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0.02 },
    })

    const maSeries: Record<string, ReturnType<typeof chart.addLineSeries>> = {}
    for (const key of Object.keys(MA_COLORS)) {
      maSeries[key] = chart.addLineSeries({
        color: MA_COLORS[key],
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        title: key.toUpperCase(),
      })
    }

    const series = data.series
    candle.setData(series.candles || [])
    // 后端 volume 单位是股；同花顺等口径是手（1 手 = 100 股）。展示层除以 100。
    const volumesInHand = (series.volumes || []).map((v: any) => ({
      ...v,
      value: v.value / 100,
    }))
    volume.setData(volumesInHand)
    for (const key of Object.keys(MA_COLORS)) {
      maSeries[key].setData((series as any)[key] || [])
    }
    // 默认展示最近 DEFAULT_BARS 根，右侧空 RIGHT_OFFSET_BARS 供未来预测标注
    const total = (series.candles || []).length
    if (total > 0) {
      const from = Math.max(0, total - DEFAULT_BARS)
      chart.timeScale().setVisibleLogicalRange({
        from,
        to: total + RIGHT_OFFSET_BARS - 1,
      })
    }

    const ro = new ResizeObserver((entries) => {
      const w = Math.floor(entries[0]?.contentRect.width || 0)
      if (w > 0) chart.applyOptions({ width: w })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [data])

  if (isLoading) return <Spin />
  if (error) return <Alert type="error" message="加载 K 线失败" />
  if (data?.empty) return <Alert type="warning" message={data.message || '本地无数据'} />

  return <div ref={containerRef} style={{ width: '100%', height: 520 }} />
}

/** 把"手"数格式化为可读字符串：<1万→整数，<1亿→x.xx 万手，≥1亿→x.xx 亿手。 */
function formatVolumeHand(v: number): string {
  const abs = Math.abs(v)
  if (abs < 1e4) return `${Math.round(v)} 手`
  if (abs < 1e8) return `${(v / 1e4).toFixed(2)} 万手`
  return `${(v / 1e8).toFixed(2)} 亿手`
}
