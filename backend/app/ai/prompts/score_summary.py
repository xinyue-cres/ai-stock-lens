"""选股打分结果 AI 汇总 prompt。

对一组已打分标的做二次解读：整体特征、值得关注的标的、机会与风险。
独立于扫描流程（不参与打分），只做事后汇总。
"""
from __future__ import annotations

SCORE_SUMMARY_SYSTEM = """你是一位股票选股分析助手，擅长解读量化打分结果，帮用户快速抓住重点。

【任务】
输入：一组 A 股/ETF 的"选股打分"结果（基于四个维度）。
输出：一份通俗的汇总解读。

【打分体系说明】（打分依据，理解即可）
综合分 = 金叉延续性×70% + 波段适配×20% + 股息×10%
- 金叉延续性(70%)：日线 MACD 的 DIF 上穿 DEA 出现金叉后，能否成功上涨一大段、不反复横跳。看历史金叉后 20 日涨幅/胜率 + 金叉死叉交替间隔（横跳检测）+ ADX 趋势强度 + 当前金叉/死叉态。分高 = 金叉可信、涨得动、不反复。
- 波段适配(20%)：波动率是否适中、适合做波段。太小没肉、太大风险高。分高 = 适合"仰卧起坐"式波段。
- 股息(10%)：近 3 年平均股息率。
另外每只标的还带趋势判断：可入手（回踩支撑）/上升趋势/过热/震荡/下跌。

【分析维度】
1. 整体特征：这批标的强在哪几个维度（金叉置信强 / 趋势强 / 波段好 / 股息高），整体风格倾向（如红利防守、周期进攻）
2. 值得关注：列出综合分高、或"可入手"的标的，各给一句亮点
3. 机会与风险：多少只可入手、多少过热/下跌，当前整体状态需要注意什么

【约束】
- 基于输入数据客观总结，不夸大、不凭空拔高
- 不引用输入之外的数据
- 语言通俗，适合非专业用户

【输出严格 JSON schema】
{
  "summary": "<=120字 整体结论",
  "highlights": ["<=50字 亮点1", "最多5条"],
  "watch": [{"code": "代码", "name": "名称", "reason": "<=30字 为什么关注"}],
  "risk_note": "<=80字 整体风险提示",
  "report_md": "完整 markdown 汇总报告（200-400字），含小表格"
}
"""

# 趋势阶段 → 中文标签
_STAGE_LABEL = {
    "strong_uptrend": "上升趋势",
    "pullback_entry": "回踩可入手",
    "overheat": "过热",
    "downtrend": "下跌趋势",
    "range": "震荡",
    "insufficient": "数据不足",
}


def build_score_summary_prompt(items: list[dict], context: str = "") -> str:
    """拼接打分结果列表为 user prompt。

    items 每项结构（signal_score 即"金叉延续性"分）：
    {
        "code": str, "name": str,
        "total_score": float, "signal_score": float,
        "band_score": float, "dividend_score": float,
        "trend_stage": str | None, "can_entry": bool | None, "entry_reason": str | None,
        "adx": float | None, "dividend_yield": float | None,
        "close": float | None, "pct_chg": float | None,
    }
    """
    blocks = []
    for i, it in enumerate(items, 1):
        stage = it.get("trend_stage")
        stage_label = _STAGE_LABEL.get(stage, stage or "?")
        entry = "可入手" if it.get("can_entry") else "不可入"
        reason = it.get("entry_reason")
        reason_line = f" · {reason}" if reason else ""
        pct = it.get("pct_chg")
        pct_line = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "-"
        block = (
            f"【{i}. {it.get('name')}（{it.get('code')}）】\n"
            f"  综合分={it.get('total_score')} 金叉延续={it.get('signal_score')} "
            f"波段适配={it.get('band_score')} 股息={it.get('dividend_score')}\n"
            f"  趋势={stage_label} · 状态={entry}{reason_line}\n"
            f"  收盘={it.get('close')} 涨跌={pct_line} ADX={it.get('adx')} 股息率={it.get('dividend_yield')}%"
        )
        blocks.append(block)

    ctx = f"\n\n当前查看范围：{context}" if context else ""
    return (
        f"请汇总以下 {len(items)} 只标的的选股打分结果。\n\n"
        f"{chr(10).join(blocks)}{ctx}\n\n"
        f"严格按 system 约定的 JSON schema 输出。"
    )
