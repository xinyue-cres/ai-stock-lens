import { memo, useState } from 'react'
import { Button, Tag, Tooltip, Typography } from 'antd'
import { FolderOpenOutlined, LineChartOutlined, PlusOutlined } from '@ant-design/icons'
import type { ScoreItem } from '@/api/score'
import { priceColor } from '@/shared/theme'
import { STAGE_PALETTE } from '../constants'

const { Text } = Typography

function subScoreColor(v: number): string {
  if (v >= 70) return '#16a34a'
  if (v >= 50) return '#2563eb'
  return '#9ca3af'
}

// 过峰置信度档位标签：触发类型(bar/acc/双)×量能(缩/中/放)，误报单调递减 88→45%
function PeakConfTag({ conf }: { conf?: number | null }) {
  if (conf == null || conf <= 0) return null
  const grade =
    conf >= 66 ? { label: '极强', color: '#dc2626' } :
    conf >= 51 ? { label: '强', color: '#ea580c' } :
    conf >= 36 ? { label: '中', color: '#d97706' } :
    conf >= 21 ? { label: '弱', color: '#a16207' } :
    { label: '极弱', color: '#ca8a04' }
  return <span style={{ fontSize: 10, fontWeight: 600, marginLeft: 3, color: grade.color }}>{grade.label}</span>
}

// 当前 MACD 状态着色：按 A 股红涨绿跌——金叉(看涨)=红/橙，死叉(看跌)=蓝/绿
function stateColor(s: string): string {
  if (s.includes('金叉') && s.includes('走强')) return priceColor.up // 红：金叉·走强=看涨动能足
  if (s.includes('金叉')) return '#d97706' // 橙：金叉·走弱=金叉但动能回落，警惕
  if (s.includes('死叉') && s.includes('修复')) return '#2563eb' // 蓝：死叉·修复=回升中
  if (s.includes('死叉')) return priceColor.down // 绿：死叉·走弱=看跌
  return '#9ca3af'
}

interface ScoreRowProps {
  item: ScoreItem
  active: boolean
  onClick: (code: string) => void
  onAddWatchlist: (code: string) => void
  onOpenDetail: (code: string) => void
  onOpenWorkbench: (item: ScoreItem) => void
}

// React.memo：200 行 Rank 列表选中/30s 轮询时，只 active 变化的行重渲染；
// 父组件必须保证回调（onClick/onAddWatchlist/onOpenDetail/onOpenWorkbench）引用稳定才能命中 memo。
function ScoreRow({ item, active, onClick, onAddWatchlist, onOpenDetail, onOpenWorkbench }: ScoreRowProps) {
  const [hovered, setHovered] = useState(false)
  const pct = item.pct_chg
  const stage = item.trend_stage ? STAGE_PALETTE[item.trend_stage] : null

  return (
    <div
      onClick={() => onClick(item.code)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '10px 14px',
        borderBottom: '1px solid #f5f5f5',
        cursor: 'pointer',
        background: active ? '#eff6ff' : hovered ? '#f9fafb' : '#fff',
        borderLeft: `3px solid ${active ? '#3b82f6' : 'transparent'}`,
        transition: 'background 0.1s',
      }}
    >
      {/* 综合分 */}
      <div style={{ width: 46, flexShrink: 0, textAlign: 'center' }}>
        <div style={{ fontSize: 20, fontWeight: 700, color: item.total_score >= 70 ? '#16a34a' : item.total_score >= 50 ? '#2563eb' : '#9ca3af' }}>
          {item.total_score.toFixed(0)}
        </div>
        <Text type="secondary" style={{ fontSize: 10 }}>综合</Text>
      </div>

      {/* 名称代码 */}
      <div style={{ width: 118, flexShrink: 0 }}>
        <div style={{ fontWeight: 500, fontSize: 13, lineHeight: 1.3 }}>{item.name || item.code}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>{item.code}</Text>
          {typeof pct === 'number' && (
            <span style={{ fontSize: 12, fontWeight: 600, color: pct >= 0 ? priceColor.up : priceColor.down }}>
              {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
            </span>
          )}
        </div>
      </div>

      {/* 子维度 mini 分（固定靠左，标签在上数字在下，统一对齐） */}
      <div style={{ width: 80, flexShrink: 0, display: 'flex', gap: 6, fontSize: 11 }}>
        {[
          { label: '金', v: item.signal_score, c: subScoreColor(item.signal_score) },
          { label: '波', v: item.band_score, c: subScoreColor(item.band_score) },
          { label: '息', v: item.dividend_score, c: subScoreColor(item.dividend_score) },
        ].map(({ label, v, c }) => (
          <span key={label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', lineHeight: 1.2, width: 20 }}>
            <span>{label}</span>
            <b style={{ color: c }}>{v.toFixed(0)}</b>
          </span>
        ))}
      </div>

      {/* 当前 MACD 状态（新增显示，详情页仍保留） */}
      {item.current_state && (
        <span
          style={{
            fontSize: 11,
            fontWeight: 500,
            flexShrink: 0,
            marginLeft: 6,
            color: stateColor(item.current_state),
            whiteSpace: 'nowrap',
          }}
        >
          {item.current_state}
        </span>
      )}

      {/* 过峰信号标记：bar|acc_z 触发 + 置信度档位（放量/双触发=强，缩量=弱） */}
      {item.peak_signal === '上涨过峰' && (
        <Tooltip title={`动能急刹（上涨见顶预警）·置信度${item.peak_conf ?? 0}分，注意回调`}>
          <span style={{ fontSize: 11, fontWeight: 700, marginLeft: 6, flexShrink: 0, color: '#d97706' }}>
            ▲过峰<PeakConfTag conf={item.peak_conf} />
          </span>
        </Tooltip>
      )}
      {item.peak_signal === '下跌过峰' && (
        <Tooltip title={`动能急转（下跌见底信号）·置信度${item.peak_conf ?? 0}分，关注反抽`}>
          <span style={{ fontSize: 11, fontWeight: 700, marginLeft: 6, flexShrink: 0, color: '#16a34a' }}>
            ▼过峰<PeakConfTag conf={item.peak_conf} />
          </span>
        </Tooltip>
      )}

      {/* DIF 斜率 */}
      {item.dif_slope != null && item.dif_slope_dir && (
        <Tooltip title={`MACD ${item.current_state ?? ''} · DIF 当日−昨前均值 ${item.dif_slope > 0 ? '+' : ''}${item.dif_slope}`}>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              marginLeft: 6,
              flexShrink: 0,
              color: item.dif_slope_dir === 'up' ? priceColor.up : item.dif_slope_dir === 'down' ? priceColor.down : '#9ca3af',
            }}
          >
            {item.dif_slope_dir === 'up' ? '↗' : item.dif_slope_dir === 'down' ? '↘' : '→'} {item.dif_slope > 0 ? '+' : ''}
            {item.dif_slope.toFixed(3)}
          </span>
        </Tooltip>
      )}

      {/* 趋势徽章（可入手 / 左侧机会 / 震荡 / 下跌等） */}
      {stage && (
        <Tag style={{ margin: 0, marginLeft: 6, color: stage.color, borderColor: stage.border, background: stage.bg, fontSize: 11, flexShrink: 0 }}>
          {stage.label}
        </Tag>
      )}
      {item.trend_stage === 'left_entry' && (
        <Tooltip title="死叉下跌动能衰竭的左侧机会，逆势·高风险，建议轻仓">
          <span style={{ fontSize: 10, marginLeft: 6, color: '#7c3aed', flexShrink: 0 }}>⚠逆势</span>
        </Tooltip>
      )}
      {/* 下跌趋势但文案含"深跌中刚金叉"= 反弹未确认：金叉存在但历史延续差不可信，
          决策仍取回避。与真下跌区分（文案树已对齐，见 trend_judge）。 */}
      {item.trend_stage === 'downtrend' && item.entry_reason?.includes('深跌中刚金叉') && (
        <Tooltip title={item.entry_reason}>
          <span style={{ fontSize: 10, marginLeft: 6, color: '#d97706', flexShrink: 0 }}>⚠反弹不可信</span>
        </Tooltip>
      )}

      {/* 弹性空隙：把 hover 操作推到最右，状态/斜率/徽章保持靠左 */}
      <div style={{ flex: 1, minWidth: 8 }} />

      {/* hover 操作：去工作台 + 查看详情 + 加自选 */}
      <div style={{ width: 96, flexShrink: 0, display: 'flex', justifyContent: 'flex-end', visibility: hovered ? 'visible' : 'hidden' }}>
        <Tooltip title={item.in_watchlist && item.group_ids?.length ? '在工作台对应分组查看' : '去工作台查看'}>
          <Button
            type="text"
            size="small"
            icon={<FolderOpenOutlined style={{ fontSize: 12 }} />}
            onClick={(e) => {
              e.stopPropagation()
              onOpenWorkbench(item)
            }}
          />
        </Tooltip>
        <Tooltip title="查看个股详情">
          <Button
            type="text"
            size="small"
            icon={<LineChartOutlined style={{ fontSize: 12 }} />}
            onClick={(e) => {
              e.stopPropagation()
              onOpenDetail(item.code)
            }}
          />
        </Tooltip>
        <Tooltip title="加入自选股">
          <Button
            type="text"
            size="small"
            icon={<PlusOutlined style={{ fontSize: 12 }} />}
            onClick={(e) => {
              e.stopPropagation()
              onAddWatchlist(item.code)
            }}
          />
        </Tooltip>
      </div>
    </div>
  )
}

export default memo(ScoreRow)
