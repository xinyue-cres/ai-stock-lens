import { Fragment, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Popover, Segmented, Spin, Tag, Typography, message } from 'antd'
import { PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import { getCombinedList, type CombinedItem, type CombinedStage } from '@/api/score'
import { BUY_SIDE_STAGES, COMBINED_PALETTE, SELL_SIDE_STAGES, STAGE_PALETTE } from '../constants'

const { Text } = Typography

interface CombinedRowProps {
  item: CombinedItem
  active: boolean
  onClick: (code: string) => void
  onAddWatchlist: (code: string) => void
}

/** 单行综合 item（ScoreRow 风格，宽度自适应），显示代码 + 综合分 + combined_stage 标签 */
function CombinedRow({ item, active, onClick, onAddWatchlist }: CombinedRowProps) {
  const palette = COMBINED_PALETTE[item.combined_stage] ?? COMBINED_PALETTE.hold
  const wStage = item.weekly.trend_stage ? STAGE_PALETTE[item.weekly.trend_stage] : null
  const dStage = item.daily.trend_stage ? STAGE_PALETTE[item.daily.trend_stage] : null

  return (
    <div
      onClick={() => onClick(item.code)}
      style={{
        padding: '10px 14px',
        borderBottom: '1px solid #f0f0f0',
        cursor: 'pointer',
        background: active ? '#e6f4ff' : 'transparent',
        borderLeft: active ? '3px solid #1677ff' : '3px solid transparent',
        transition: 'background 0.15s ease',
      }}
      onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = '#fafafa' }}
      onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent' }}
    >
      {/* 第一行：名称 + 综合分 + combined_stage tag */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{item.name || item.code}</span>
          <Text type="secondary" style={{ fontSize: 11 }}>{item.code}</Text>
          {item.is_fund && <Tag style={{ fontSize: 10, lineHeight: '14px', padding: '0 4px', marginInlineEnd: 0 }}>ETF</Tag>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Tag
            style={{
              color: palette.color, background: palette.bg, borderColor: palette.border,
              fontSize: 11, lineHeight: '16px', padding: '0 6px', marginInlineEnd: 0,
            }}
          >
            {palette.label}
          </Tag>
          <span style={{ fontWeight: 700, fontSize: 15, color: palette.color, minWidth: 36, textAlign: 'right' }}>
            {item.combined_score.toFixed(1)}
          </span>
        </div>
      </div>

      {/* 第二行：weekly / daily 两条腿的简版状态 */}
      <div style={{ display: 'flex', gap: 10, fontSize: 11, color: 'rgba(0,0,0,0.65)', marginBottom: 4, flexWrap: 'wrap', rowGap: 2 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span style={{ color: 'rgba(0,0,0,0.45)' }}>周</span>
          <span style={{ fontWeight: 600 }}>{item.weekly.total_score?.toFixed(0) ?? '-'}</span>
          {wStage && <span style={{ color: wStage.color }}>{wStage.label}</span>}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span style={{ color: 'rgba(0,0,0,0.45)' }}>日</span>
          <span style={{ fontWeight: 600 }}>{item.daily.total_score?.toFixed(0) ?? '-'}</span>
          {dStage && <span style={{ color: dStage.color }}>{dStage.label}</span>}
        </span>
        {/* signal_score 双腿 + 剩余中位预期 */}
        <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span style={{ color: 'rgba(0,0,0,0.45)' }}>信</span>
          <span style={{ fontWeight: 500 }}>
            {item.weekly.signal_score?.toFixed(0) ?? '-'}/{item.daily.signal_score?.toFixed(0) ?? '-'}
          </span>
        </span>
        {/* 历史可预期： 剩余中位（hist_med - signal_gain）*/}
        {item.hist_golden_peak_median != null && item.weekly_signal_gain_pct != null && (() => {
          const remain = item.hist_golden_peak_median - item.weekly_signal_gain_pct
          return (
            <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <span style={{ color: 'rgba(0,0,0,0.45)' }}>余中</span>
              <span style={{ fontWeight: 600, color: remain >= 10 ? '#16a34a' : remain > 0 ? '#0891b2' : '#d97706' }}>
                {remain > 0 ? `+${remain.toFixed(0)}%` : `${remain.toFixed(0)}%`}
              </span>
            </span>
          )
        })()}
        {!item.in_watchlist && (
          <Button
            size="small"
            type="text"
            icon={<PlusOutlined />}
            style={{ padding: 0, height: '16px', lineHeight: '16px', fontSize: 11, marginLeft: 'auto' }}
            onClick={(e) => { e.stopPropagation(); onAddWatchlist(item.code) }}
          >
            加自选
          </Button>
        )}
      </div>

      {/* 第三行：操作建议（一行截断） */}
      <Text
        type="secondary"
        style={{
          fontSize: 11, display: 'block',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}
      >
        {item.entry_reason}
      </Text>
    </div>
  )
}

interface CombinedViewProps {
  scope: string
  groupIds: number[]
  selected: string | null
  onSelect: (code: string) => void
  onAddWatchlist: (code: string) => void
  renderDetail?: (code: string) => React.ReactNode  // 右侧详情渲染（可选）
}

/** 左侧列表（ScoreRow 风格，含 stage 过滤 Segmented + 自选分组过滤） */
export function CombinedList({
  scope, groupIds, selected, onSelect, onAddWatchlist,
}: CombinedViewProps) {
  const [coarse, setCoarse] = useState<'all' | 'buy_side' | 'sell_side' | 'hold' | 'avoid'>('buy_side')
  const [fine, setFine] = useState<CombinedStage | null>(null)
  const groupIdsKey = groupIds.length ? groupIds.join(',') : undefined

  // 基准拉全量，前端按粗过滤 + 细分档位两级过滤
  const listQ = useQuery({
    queryKey: ['combined-list', scope, groupIdsKey],
    queryFn: () => getCombinedList({ scope, limit: 500, group_ids: groupIdsKey }),
  })
  const items = useMemo(() => {
    const all = listQ.data ?? []
    let arr = all
    if (coarse === 'buy_side') arr = arr.filter((i) => BUY_SIDE_STAGES.includes(i.combined_stage))
    else if (coarse === 'sell_side') arr = arr.filter((i) => SELL_SIDE_STAGES.includes(i.combined_stage))
    else if (coarse === 'hold') arr = arr.filter((i) => i.combined_stage === 'hold')
    else if (coarse === 'avoid') arr = arr.filter((i) => i.combined_stage === 'avoid')
    if (fine) arr = arr.filter((i) => i.combined_stage === fine)
    return arr
  }, [listQ.data, coarse, fine])

  // 细分档位点击 → 联动粗排跳到对应侧
  const pickFine = (stage: CombinedStage, checked: boolean) => {
    if (!checked) { setFine(null); return }
    if (BUY_SIDE_STAGES.includes(stage)) setCoarse('buy_side')
    else if (SELL_SIDE_STAGES.includes(stage)) setCoarse('sell_side')
    else if (stage === 'hold') setCoarse('hold')
    else setCoarse('avoid')
    setFine(stage)
  }

  // 细分 tag：只保留 10 个买卖档，买侧/卖侧对称两行（持有/回避由粗排承担）
  // 卖侧显式镜像顺序，与买侧逐档对应（强卖↔强买、卖出↔买入、观察卖↔观察买…）
  const SELL_MIRROR_ORDER: CombinedStage[] = [
    'strong_sell', 'sell', 'watch_sell', 'deep_rally_exit', 'light_sell',
  ]
  // 各档信号含义（问号提示用）
  const STAGE_MEANING: Record<CombinedStage, string> = {
    strong_buy: '日周线同向看多共振，重仓买入',
    buy: '周线看好 + 日线已反弹，可买入',
    watch_buy: '周看多但日线整理，等升级',
    deep_pullback_entry: '周趋势内日超跌，轻仓分批',
    light_buy: '周中性 + 日线有起涨信号，轻仓试',
    hold: '可交易但无明确方向，不动',
    watch_sell: '周定调偏坏，日线未确认走坏，先盯',
    light_sell: '周走弱但日线未确认，先减仓',
    deep_rally_exit: '周已走坏，日线反弹是离场窗口',
    sell: '日周均走坏，尽快出清',
    strong_sell: '双周共振走弱，清仓',
    avoid: '系统不评估（数据不足/双周假弱），不介入',
  }
  const stageHelp = (
    <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '5px 12px', maxWidth: 360 }}>
      {[...BUY_SIDE_STAGES, ...SELL_MIRROR_ORDER].map((stage) => {
        const p = COMBINED_PALETTE[stage]
        return (
          <Fragment key={stage}>
            <span style={{ color: p.color, fontWeight: 600, fontSize: 12, whiteSpace: 'nowrap' }}>{p.label}</span>
            <span style={{ color: 'rgba(0,0,0,0.65)', fontSize: 12 }}>{STAGE_MEANING[stage]}</span>
          </Fragment>
        )
      })}
    </div>
  )

  return (
    <Card
      size="small"
      title={`日周合并 (${items.length})`}
      extra={
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Popover
            title="信号含义"
            content={stageHelp}
            trigger="click"
            placement="bottomRight"
          >
            <QuestionCircleOutlined style={{ fontSize: 14, color: '#999', cursor: 'pointer' }} />
          </Popover>
          <Segmented
            size="small"
            value={coarse}
            onChange={(v) => { setCoarse(v as typeof coarse); setFine(null) }}
            options={[
              { value: 'all', label: '全部' },
              { value: 'buy_side', label: '买侧' },
              { value: 'sell_side', label: '卖侧' },
              { value: 'hold', label: '中性' },
              { value: 'avoid', label: '回避' },
            ]}
          />
        </div>
      }
      style={{ width: 540, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
      styles={{
        header: { flexShrink: 0, padding: '6px 12px', alignItems: 'center' },
        body: { padding: 0, flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' },
      }}
    >
      {/* 第二、三排：细分档位 tag，买侧/卖侧对称两行 */}
      <div style={{ padding: '4px 12px 8px', borderBottom: '1px solid #f0f0f0', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {[
          { key: '买', stages: BUY_SIDE_STAGES },
          { key: '卖', stages: SELL_MIRROR_ORDER },
        ].map(({ key, stages }) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, color: '#9ca3af', flexShrink: 0, width: 12 }}>{key}</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {stages.map((stage) => {
                const p = COMBINED_PALETTE[stage]
                const active = fine === stage
                return (
                  <Tag.CheckableTag
                    key={stage}
                    checked={active}
                    onChange={(c: boolean) => pickFine(stage, c)}
                    style={{
                      fontSize: 11,
                      color: p.color,
                      backgroundColor: active ? '#e0e0e0' : 'transparent',
                    }}
                  >
                    {p.label}
                  </Tag.CheckableTag>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {listQ.isLoading && (
          <div style={{ padding: 32, textAlign: 'center' }}><Spin /></div>
        )}
        {!listQ.isLoading && items.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无综合评判记录"
            style={{ padding: 24 }}
          />
        )}
        {items.map((item) => (
          <CombinedRow
            key={item.code}
            item={item}
            active={selected === item.code}
            onClick={onSelect}
            onAddWatchlist={onAddWatchlist}
          />
        ))}
      </div>
    </Card>
  )
}

/** 兼容老 API：不再使用卡片网格。导出别名保留向后兼容。 */
export default CombinedList
