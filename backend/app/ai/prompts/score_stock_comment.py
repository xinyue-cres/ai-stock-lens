"""单只股票的选股打分点评 prompt。

针对一只标的的打分 + 趋势判断做独立解读（不对比其他股票）。
用于"AI 点评"按钮：对当前列表逐只生成各自总结。
"""
from __future__ import annotations

SCORE_STOCK_SYSTEM = """你是一位 A 股个股分析助手，只针对单只股票的打分数据做通俗解读。

【输入】一只标的的"选股打分"结果：综合分 + 四个维度分 + 趋势判断 + 关键指标。

【打分体系】（理解即可）
综合分 = 金叉延续性×70% + 波段适配×20% + 股息×10%
- 金叉延续性(70%)：日线 MACD 的 DIF 上穿 DEA 出现金叉后，能否成功上涨一大段、不反复横跳。看历史金叉后 20 日涨幅/胜率 + 金叉死叉交替间隔（横跳检测）+ ADX 趋势强度 + 当前金叉/死叉态。分高 = 金叉可信、涨得动、不反复。
- 波段适配(20%)：波动率适中适合做波段。太小没肉、太大风险高。
- 股息(10%)：近 3 年平均股息率。
趋势阶段：可入手（上升趋势回踩支撑）/ 上升趋势 / 过热 / 震荡 / 下跌 / 数据不足。

【任务】给这只股票写一段独立点评：
1. 打分结构解读：这只票强在哪、弱在哪（结合各维度分高低说，别只说数字）
2. 当前趋势与能否入手：结合趋势阶段和关键指标
3. 一句话结论：值得关注 / 等回踩再考虑 / 回避

【约束】
- 只分析这一只，不与其他股票比较，不引用输入之外的数据
- 客观，不夸大，不凭空拔高
- 语言通俗，像朋友给建议

【输出严格 JSON schema】
{
  "verdict": "关注 | 观望 | 回避",
  "score_comment": "<=40字，打分结构一句话",
  "summary": "<=150字，完整解读（强在哪/弱在哪/能否入手）",
  "key_point": "<=30字，最值得注意的一点"
}
"""

_STAGE_LABEL = {
    "strong_uptrend": "上升趋势",
    "pullback_entry": "回踩可入手",
    "overheat": "过热",
    "downtrend": "下跌趋势",
    "range": "震荡",
    "insufficient": "数据不足",
}


def build_score_stock_prompt(item: dict) -> str:
    """拼接单只打分数据为 user prompt。

    item 结构（与 /score/list 的 ScoreItem 一致，signal_score 即"金叉延续性"分）：
    {code, name, total_score, signal_score, band_score, dividend_score,
     trend_stage, can_entry, entry_reason, close, pct_chg, turnover, hist_vol, adx, dividend_yield}
    """
    stage = item.get("trend_stage")
    stage_label = _STAGE_LABEL.get(stage, stage or "?")
    entry = "可入手" if item.get("can_entry") else "不可入"
    reason = item.get("entry_reason")
    reason_line = f"（{reason}）" if reason else ""
    pct = item.get("pct_chg")
    pct_line = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "-"

    return f"""请分析以下单只股票的选股打分结果：

【{item.get('name')}（{item.get('code')}）】
综合分={item.get('total_score')}
  金叉延续={item.get('signal_score')} 波段适配={item.get('band_score')} 股息={item.get('dividend_score')}
趋势阶段={stage_label} · 状态={entry}{reason_line}
关键指标：收盘={item.get('close')} 涨跌={pct_line} ADX={item.get('adx')}
  年化波动率={item.get('hist_vol')}% 股息率={item.get('dividend_yield')}% 换手率={item.get('turnover')}%

严格按 system 约定的 JSON schema 输出。"""
