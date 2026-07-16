"""共用辅助函数。"""
from __future__ import annotations


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
