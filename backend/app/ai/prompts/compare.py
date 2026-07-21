"""多股横向对比 AI 分析 prompt。"""
from __future__ import annotations

COMPARE_SYSTEM = """你是一位投资组合分析师，擅长横向对比多只 A 股并给出资金配置建议。

【任务】
输入：2-6 只 A 股的技术指标快照 + 已有 AI 分析摘要。
输出：一份结构化的横向对比报告，帮助用户决定"资金应该优先进入哪只"。

【分析维度】
1. **多空方向对比**：各票当前 AI verdict 和 confidence，谁更明确看多/看空
2. **技术面强弱**：价格趋势（MA 排列）、动量（涨跌幅）、波动率（ATR）、盈亏比潜力
3. **资金配置建议**：综合打分后排序 + 建议资金占比。考虑：
   - 确定性高的多配
   - 波动大的少配
   - 同方向相关性高的要分散
4. **相关性/分散度**：判断选中的票之间走势是否同质化

【约束】
- A 股无做空机制，所有建议围绕"买入/持有/观望"
- 不引用输入之外的数据
- 不做新的技术分析，只基于输入中的已有分析结果做横向比较
- 评分基于输入数据的客观指标，不凭空拔高
- 资金配置合计 100%，若全部不适合买入，允许配比中加入"现金等待"项

【输出严格 JSON schema】
{
  "ranking": [
    {
      "code": "股票代码",
      "name": "股票名称",
      "score": 0-100 综合评分,
      "verdict": "bullish|neutral|bearish|caution",
      "strength": "技术面强弱 1-2 句",
      "rationale": "<=40字，为什么排这个位"
    }
  ],
  "allocation": [
    {
      "code": "股票代码 或 'cash'",
      "name": "名称 或 '现金等待'",
      "pct": 百分比整数,
      "reason": "<=30字"
    }
  ],
  "correlation_note": "<=80字，这几只票之间的关联性和分散度评估",
  "risk_note": "<=80字，当前组合主要风险提示",
  "summary": "<=100字，一句话结论：资金应该怎么分配",
  "report_md": "完整 markdown 格式对比报告（200-400字），包含表格对比"
}

ranking 按 score 降序排列。allocation 按 pct 降序排列。
"""


def build_compare_prompt(stocks_data: list[dict]) -> str:
    """拼接多票数据为 user prompt。

    stocks_data 每项结构：
    {
        "code": str,
        "name": str,
        "close": float,
        "pct_chg": float,
        "ma5/10/20/60": float,
        "atr": float,
        "turnover": float,
        "verdict": str | None,
        "confidence": float | None,
        "summary": str | None,
        "key_signals": list,
        "scenarios": list,
    }
    """
    blocks = []
    for i, s in enumerate(stocks_data, 1):
        ma_line = f"MA5={s.get('ma5')} MA10={s.get('ma10')} MA20={s.get('ma20')} MA60={s.get('ma60')}"
        verdict_line = f"verdict={s.get('verdict', '未分析')} confidence={s.get('confidence', 'N/A')}"
        block = (
            f"【{i}. {s.get('name')}（{s.get('code')}）】\n"
            f"  close={s.get('close')} pct_chg={s.get('pct_chg')}% turnover={s.get('turnover')}%\n"
            f"  {ma_line}\n"
            f"  ATR={s.get('atr')} BOLL上/下={s.get('boll_upper')}/{s.get('boll_lower')}\n"
            f"  AI: {verdict_line}\n"
            f"  摘要: {s.get('summary') or '无'}\n"
            f"  关键信号: {s.get('key_signals') or '无'}\n"
            f"  scenarios: {s.get('scenarios') or '无'}"
        )
        blocks.append(block)

    return f"""请对以下 {len(stocks_data)} 只 A 股进行横向对比分析。

{chr(10).join(blocks)}

请严格按 system 约定的 JSON schema 输出。"""
