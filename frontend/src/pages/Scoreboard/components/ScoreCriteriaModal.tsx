import { Modal, Progress, Tag, Typography } from 'antd'
import { SCORE_CRITERIA, STAGE_PALETTE } from '../constants'

const { Text, Paragraph } = Typography

const WEIGHT_COLOR: Record<string, string> = {
  '70%': '#3b82f6',
  '20%': '#16a34a',
  '10%': '#d97706',
}

// 复用趋势徽章配色（A 股红涨绿跌）
const stageTag = (k: keyof typeof STAGE_PALETTE) => ({
  color: STAGE_PALETTE[k].color,
  borderColor: STAGE_PALETTE[k].border,
  background: STAGE_PALETTE[k].bg,
  margin: 0,
  fontSize: 11,
})

export default function ScoreCriteriaModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  return (
    <Modal title="选股标准说明" open={open} onCancel={onClose} footer={null} width={640}>
      <Paragraph style={{ marginTop: 4 }}>
        这套打分用于筛选适合「<Text strong>稳定上升电梯 + 中途波段仰卧起坐</Text>」这类策略的标的。
        综合分由四个维度按权重加权，分越高越符合标准：
      </Paragraph>

      <div style={{ display: 'flex', alignItems: 'center', gap: 18, margin: '14px 0' }}>
        <div style={{ fontSize: 28, fontWeight: 700, color: '#1f2937' }}>综合分</div>
        <Text type="secondary" style={{ fontSize: 13 }}>
          = 0.70×金叉延续性 + 0.20×波段适配 + 0.10×股息
        </Text>
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        {SCORE_CRITERIA.map((c) => (
          <div key={c.key} style={{ flex: 1, textAlign: 'center' }}>
            <Progress
              type="circle"
              percent={parseInt(c.weight)}
              size={64}
              strokeColor={WEIGHT_COLOR[c.weight]}
              format={() => <b style={{ fontSize: 15 }}>{c.weight}</b>}
            />
            <div style={{ fontSize: 12, marginTop: 6 }}>{c.label}</div>
          </div>
        ))}
      </div>

      {SCORE_CRITERIA.map((c) => (
        <div key={c.key} style={{ padding: '10px 12px', background: '#f9fafb', borderRadius: 8, marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Tag style={{ margin: 0, background: WEIGHT_COLOR[c.weight], color: '#fff', border: 'none' }}>
              {c.weight}
            </Tag>
            <b>{c.label}</b>
          </div>
          <Text type="secondary" style={{ fontSize: 13, display: 'block', marginTop: 4 }}>
            {c.desc}
          </Text>
        </div>
      ))}

      <div style={{ padding: '12px', background: '#f0f5ff', borderRadius: 8 }}>
        <b>趋势 / 可入手判断（排行 item 最右的徽章）</b>
        <Text type="secondary" style={{ fontSize: 13, display: 'block', marginTop: 4 }}>
          金叉驱动 + 空间衡量：综合「当前 MACD 金叉状态 × 布林带空间(%B) × 历史金叉延续分」。
        </Text>

        <div style={{ marginTop: 10, fontSize: 13 }}>
          <b style={{ color: STAGE_PALETTE.pullback_entry.color }}>金叉态（DIF &gt; DEA）→ 上升候选</b>
          <ul style={{ margin: '6px 0 0', paddingLeft: 20, color: '#666', fontSize: 12, lineHeight: 2 }}>
            <li>
              贴上布林上轨（%B&gt;0.85，短期涨过头）→ <Tag style={stageTag('overheat')}>过热</Tag> 等回踩
            </li>
            <li>
              距 60 日高点回撤 &gt;40% 且历史金叉分&lt;65 → <Tag style={stageTag('downtrend')}>下跌趋势</Tag> 回避
            </li>
            <li>
              历史金叉延续分 ≥65（可靠）→ <Tag style={stageTag('pullback_entry')}>可入手</Tag>
            </li>
            <li>
              未过热、有上方空间（%B≥0.2）→ <Tag style={stageTag('pullback_entry')}>可入手</Tag>
            </li>
            <li>
              贴下轨（%B&lt;0.2，弱势金叉）→ <Tag style={stageTag('range')}>震荡</Tag> 观望
            </li>
          </ul>
        </div>

        <div style={{ marginTop: 8, fontSize: 13 }}>
          <b style={{ color: STAGE_PALETTE.downtrend.color }}>死叉态（DIF &lt; DEA）</b>
          <ul style={{ margin: '6px 0 0', paddingLeft: 20, color: '#666', fontSize: 12, lineHeight: 2 }}>
            <li>
              历史金叉延续分 ≥65（可靠，金叉总会再来）→ <Tag style={stageTag('range')}>震荡</Tag> 等下次金叉
            </li>
            <li>
              历史金叉延续分 &lt;65 → <Tag style={stageTag('downtrend')}>下跌趋势</Tag> 回避
            </li>
          </ul>
        </div>

        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 10 }}>
          徽章颜色按 A 股红涨绿跌：可入手/上升=红、过热=橙、震荡=蓝、下跌=绿、数据不足=灰。
          打分看「长期是否适合做」，趋势徽章看「现在能否买」。
        </Text>
      </div>

      <div style={{ padding: '12px', background: '#f0f5ff', borderRadius: 8, marginTop: 8 }}>
        <b>右侧详情卡「趋势判断 · 信号汇总」怎么看</b>
        <Text type="secondary" style={{ fontSize: 13, display: 'block', marginTop: 4 }}>
          点击排行里的股票，右侧卡片展示这只票的 MACD 信号历史汇总：
        </Text>
        <ul style={{ margin: '6px 0 0', paddingLeft: 20, color: '#666', fontSize: 12, lineHeight: 2 }}>
          <li><b>当前信号 / 信号持续</b>：现在是金叉还是死叉，已持续几个交易日</li>
          <li><b>历史金叉平均持续</b>：历史上每次金叉平均延续几天（对照当前，超出=强势延续）</li>
          <li><b>历史金叉周期峰值涨幅</b>：每次金叉冲到的最高涨幅，展示<Text type="secondary">均值 · 中位 · 胜率（冲过 +5% 的占比）</Text></li>
          <li><b>历史死叉周期谷值跌幅</b>：每次死叉砸到的最深跌幅（负值=真跌），展示<Text type="secondary">均值 · 中位 · 胜率（跌破 -5% 的占比）</Text></li>
          <li><b>过峰信号</b>：MACD 柱（DIF−DEA）当日 vs 昨前均值——上涨中柱体缩小=<Text type="secondary">上涨见顶</Text>，下跌中柱体回升=<Text type="secondary">下跌见底</Text>（比 DIF 斜率更早预警）</li>
          <li><b>DIF 斜率 / ADX / 均线结构</b>：动能方向、趋势强度、均线排列（多头/空头/纠缠）</li>
        </ul>
      </div>
    </Modal>
  )
}
