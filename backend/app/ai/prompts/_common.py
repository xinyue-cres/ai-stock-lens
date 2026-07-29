"""共用辅助函数。"""
from __future__ import annotations


def _format_recent_days(recent_days: list | None) -> str:
    """格式化近 N 日逐日明细表格，供 prompt 使用。"""
    if not recent_days:
        return ""
    lines = ["日期 | 收盘 | 涨跌幅% | 换手率%"]
    for d in recent_days:
        pct = f"{d['pct_chg']:+.2f}" if d.get("pct_chg") is not None else "-"
        tur = f"{d['turnover']:.2f}" if d.get("turnover") is not None else "-"
        lines.append(f"{d['date']} | {d['close']} | {pct} | {tur}")
    return "\n【近10个交易日逐日明细】\n" + "\n".join(lines) + "\n"


def _format_previous_block(previous: dict | None) -> str:
    if not previous:
        return ""
    review = previous.get("latest_review") or {}
    review_line = ""
    if review:
        review_line = (
            f"  · 距发布 {review.get('days_after','?')} 交易日，"
            f"累计涨跌 {review.get('price_change_pct')}%，"
            f"verdict 判定：{review.get('verdict_hit','pending')}，"
            f"scenario 命中 {review.get('triggered_count',0)}/{review.get('total_scenarios',0)}"
        )
    scenarios = previous.get("scenarios") or []
    scen_lines = []
    for i, s in enumerate(scenarios[:3]):
        if isinstance(s, dict):
            scen_lines.append(
                f"    - [{s.get('direction','?')}] {s.get('trigger','')} → {s.get('action','')}"
            )
    scen_block = "\n".join(scen_lines) if scen_lines else "    (无)"
    return f"""
【上次报告与复盘】（供你反思，不是重复播报）
  · 上次 as_of {previous.get('as_of_date')} · verdict={previous.get('verdict')} · conf={previous.get('confidence')}
  · summary：{previous.get('summary') or '(空)'}
  · 上次预案：
{scen_block}
{review_line}
"""
