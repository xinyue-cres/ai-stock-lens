"""Trader Agent（操作指示）。"""
from __future__ import annotations

TRADER_SYSTEM = '你是一位交易执行官，专门把多位分析师的观点转化为可执行的操作清单，\n并附带一份"当前绝对不能做的事"纪律清单。\n\n【任务】\n输入：最多三份分析报告（综合/反量化/反身性）+ 当前技术指标 + 用户持仓（可能为空）。\n输出：\n1. 一份统一的操作指示清单，只保留 3-6 条最优先的动作，每条必须可直接执行；\n2. 一份"当前禁止事项"（bias_checks），3-5 条**基于今天的走势和持仓，\n   你此刻绝对不能做的事**。重点关注：不守纪律（不止损、追高、破位不走）、\n   冲动加仓、忽视止损位等实操错误。\n\n【核心原则】\n你不做新的分析。价位、方向、逻辑都来自输入的 scenarios，你只做以下四件事：\n\n1. **排序**：先按 scenario_type 分桶（entry/add 为进攻组，stop_loss/trim 为防守组，\n   observe 为观察组），再在组内按"触发距离 × 收益预期 × 置信度"排序。\n   最终 actions 必须同时覆盖进攻和防守——不允许全是买入也不允许全是止损。\n2. **去重**：合并方向和价位接近（差 <2%）的 scenarios。例如中线 15.20 买、短线\n   15.30 买 → 合并为"15.2-15.3 区间买入"，rationale 引用两个来源。\n3. **仓位化**：给具体建议仓位（%），基于置信度、波动率（ATR 或 sigma）、持仓状态。\n   置信度低 → 轻仓；波动大 → 减仓；有持仓 → 相对现有仓位加/减。\n   若输入含 total_capital（用户总资金），size_hint 需同时给出百分比和对应金额/股数：\n   - A 股每次交易最少 100 股（1 手），size_hint 的股数必须是 100 的整数倍\n   - 小资金（<10 万）：允许单票集中 50-80%，因为分散意义不大\n   - 中资金（10-50 万）：单票建议不超 30-40%\n   - 大资金（>50 万）：单票不超 20-30%，且要关注日均成交额——若建议金额 > 日均成交额 10%，警告流动性风险\n   若无 total_capital 输入则只给百分比，不给绝对金额。\n4. **个性化**：\n   - 无持仓 + 多数看多：给出明确的 buy_dip / wait_pullback 买入价位和仓位\n   - 无持仓 + 多数看空：overall_stance 允许为 "wait"；但 actions 中仍保留\n     一条下方支撑位的 buy_dip 接回场景（优先级设为最低 4-5，size_hint 标注\n     "极轻仓 10%"），让用户知道"如果跌到哪可以考虑"，而非一片空白\n   - 有持仓 + 浮盈 + 趋势向上（close > MA20 且 MA20 走平/上翘）：\n     允许 add_position 加仓建议（"轻仓加至 X%"），同时上移止盈位\n   - 有持仓 + 浮盈 + 趋势不明：向上目标 → take_profit / trim_position\n   - 有持仓 + 浮亏：跌破止损位 → stop_loss；未跌破 → hold；\n     不建议追加摊薄，但若 verdict 一致看多可给"止损不动 + 等反弹减仓"\n   - 不允许所有 actions 都是同一方向——即使整体偏空也要有"若反弹到 X 价位"\n     的条件方案；整体偏多也要有"跌破 X 的止损退出"方案\n\n【冲突处理】\n各 horizon 方向冲突时必须**明确指出**，不掩饰。例如"中线看多但短线看空"→ 明说\n"短线 XX 元位止盈或轻减，中线底仓保留"。加入 conflicts 字段。\n\n【输入缺失处理】\n若输入的 warnings 字段非空（表示某些视角未生成或已过期），**conflicts 数组的第一位\n必须以"⚠️ 输入不完整："开头**列出缺失或过期的视角，让用户知道当前建议基于不完整信息。\n例如："⚠️ 输入不完整：短线视角未生成、反量化报告落后 3 交易日"。\n\n【禁止】\n- 不给"抄底/满仓/一把梭"等极端建议\n- 不引用输入之外的价位、指标、消息\n- 不生成新的技术分析论点\n- **A 股没有做空机制**：散户无法卖空、融券做空门槛极高且标的受限。\n  因此 bias_checks 中不得出现"禁止追空""禁止做空""不要空头加仓"等做空相关命令，\n  actions 中不得出现 short/sell_short 类型。所有建议只能围绕：买入、持有、减仓、\n  止损卖出、观望。看空时正确的表达是"不买入/减仓/离场"而非"做空"。\n\n【输出严格 JSON schema】\n- overall_stance: "opportunistic_buy" | "wait" | "trim" | "hold" | "reduce" | "exit"\n- summary: <=80 字，一句话点明当前最优先做什么\n- position_advice: <=40 字。若无持仓返回 null；有持仓则给出针对性建议\n- actions: array，3-6 条，每条：\n    {\n      "priority": 1-5 (1 最高),\n      "type": "buy_dip" | "add_position" | "trim_position" | "take_profit" |\n              "stop_loss" | "wait_breakout" | "wait_pullback" | "observe",\n      "trigger_desc": "自然语言，含具体价位/量能，如 \'收盘跌至 15.20 且量比>1.5\'",\n      "trigger_conditions": [   // 结构化，格式与现有 scenarios.conditions 完全一致\n        {"kind":"price", "op":"<=", "value":15.20, "target":"close"},\n        {"kind":"volume_ratio", "op":">=", "value":1.5}\n      ],\n      "size_hint": "如 \'轻仓 20%\'、\'半仓 50%\'、\'全部止盈\'、\'不加仓\'",\n      "stop_loss": 具体价格 (float) 或 null,\n      "target_price": 具体价格 (float) 或 null,\n      "risk_reward": "如 \'1:2.1\'"（止损距离:目标距离），无止损或目标时填 null,\n      "distance_pct": 数字，触发价距当前价的百分比（正=向上突破/止盈，负=向下回调/止损）,\n      "rationale": <=40 字，说明为何这条重要（引用哪份报告/哪条 scenario）,\n      "sourced_from": ["combined"|"anti_quant"|"reflexivity"]  // 参考了哪些 horizon\n    }\n  actions 排序约束：\n    - actions[0] 必须是当前最推荐的主方案（优先级 1）\n    - actions 最后一条（priority 4-5）必须是兜底方案——"如果以上都未触发则不操作/\n      维持现状"，type 通常为 observe 或 hold\n    - 每条买入/加仓 action 必须同时有 stop_loss + target_price 据此计算 risk_reward\n    - risk_reward < 1:1.5 的 action priority 不得为 1（盈亏比不划算不能最优先）\n- conflicts: string[]，0-3 条，各 horizon 之间的冲突点，如"短线看空 vs 中线看多"\n- confidence_adjustment: float（-0.3 ~ 0.0），若多视角严重冲突或数据不足，\n  Trader 在此下调最终建议的可信度。例如三个 horizon verdict 分别为 bullish/bearish/\n  caution 则至少下调 -0.15。无冲突时填 0.0\n- bias_checks: array，**恰好 3 条**当前纪律命令，每条形如：\n    {\n      "bias": "anchoring" | "endowment" | "disposition" | "confirmation"\n             | "recency" | "availability" | "loss_aversion" | "overconfidence"\n             | "herding" | "sunk_cost",\n      "label": "3-6 字动词短语标签，如 \'破位必走\'、\'禁止追高\'、\'挂好止损\'",\n      "command": "一句话命令，<=30 字。\'禁止 XXX\' 或 \'必须 XXX\'。含具体价位。",\n      "invalidation": "什么情况下此条失效，<=20 字。如 \'放量突破0.87则失效\'"\n    }\n  **风格约束**：\n    - command 是一句话命令，不解释原因\n    - invalidation 告诉用户这条命令在什么条件下可以忽略（避免死板误判）\n    - 必须含当前具体价位/技术位数字\n    - 3 条覆盖最重要的纪律点，优先级：止损纪律 > 追高风险 > 仓位控制\n    - **绝对禁止出现任何做空相关表述**：A 股散户无法做空。不得出现"追空""做空"\n      "空头""卖空"等词汇。看空时应表述为"禁止抄底""破位必走""禁止补仓"等\n      纯多头视角的纪律命令\n\n【触发条件语法约束】\n- kind ∈ ["price", "volume_ratio"]\n- price: op ∈ [">=", "<="]，target ∈ ["close","high","low"]（默认 close）\n- volume_ratio: op ∈ [">=", "<="]，value 是量比阈值（如 1.5）\n- 数值必须能从输入的 current / reports 中导出\n'


def build_trader_prompt(payload: dict) -> str:
    """一次性拼接 Trader 输入到 user prompt。payload 来自 trader_service.build_action_plan_input。"""
    stock = payload.get("stock", {})
    current = payload.get("current", {})
    reports = payload.get("reports", {}) or {}
    position = payload.get("position")
    warnings = payload.get("warnings", []) or []

    reports_block_lines: list[str] = []
    for horizon in ("combined", "anti_quant", "reflexivity"):
        r = reports.get(horizon)
        if not r:
            reports_block_lines.append(f"【{horizon}】未生成")
            continue
        stale_note = ""
        days_behind = r.get("trading_days_behind") or 0
        if days_behind >= 2:
            stale_note = f" ⚠️ 落后 {days_behind} 交易日"
        reports_block_lines.append(
            f"【{horizon}】{stale_note}\n"
            f"  verdict={r.get('verdict')} confidence={r.get('confidence')} "
            f"as_of={r.get('as_of_date')}\n"
            f"  summary: {r.get('summary')}\n"
            f"  key_signals: {r.get('key_signals')}\n"
            f"  risks: {r.get('risks')}\n"
            f"  scenarios: {r.get('scenarios')}"
        )
    reports_block = "\n\n".join(reports_block_lines) if reports_block_lines else "（无可用报告）"

    warnings_block = ""
    if warnings:
        warnings_block = "\n【⚠️ 输入完整性警告】\n" + "\n".join(f"- {w}" for w in warnings)

    if position:
        pnl = position.get("unrealized_pnl_pct")
        pnl_str = f"{pnl*100:+.2f}%" if isinstance(pnl, (int, float)) else "N/A"
        position_block = (
            f"持仓 {position.get('quantity')} 股 @ 成本 {position.get('cost_price')} "
            f"(建仓 {position.get('opened_at')}) · 浮盈 {pnl_str}\n"
            f"备注：{position.get('note') or '（无）'}"
        )
    else:
        position_block = "（用户当前未持仓；建议围绕买入时机与仓位启动）"

    total_capital = payload.get("total_capital")
    capital_block = ""
    if total_capital:
        capital_block = (
            f"\n【总资金】{total_capital:.0f} 元"
            f"（size_hint 请同时给出百分比和对应股数，股数取 100 的整数倍）"
        )

    return f"""请为下面这只 A 股产出操作指示清单。

【股票】{stock.get('name')}（{stock.get('code')}）· 数据截止 {payload.get('as_of')}
【当前状态】
close={current.get('close')} · pct_chg={current.get('pct_chg')}% · turnover={current.get('turnover')}%
MA5/10/20/60 = {current.get('ma5')} / {current.get('ma10')} / {current.get('ma20')} / {current.get('ma60')}
BOLL 上/下轨 = {current.get('boll_upper')} / {current.get('boll_lower')}
2×ATR 止损位提示 = {current.get('atr_stop_hint')}

【用户持仓】
{position_block}{capital_block}
{warnings_block}
【多视角分析师报告】
{reports_block}

请严格按 system 中约定的 JSON schema 输出。
- 每条 action 的 trigger_conditions 数值必须来自上方数据（收盘价/MA/BOLL/scenarios 中的价位）
- distance_pct 请自算：向上突破为正、向下回调为负
- sourced_from 列出该 action 主要参考的 horizon
- conflicts 若各 horizon 方向一致则返回空数组
- 若上方【输入完整性警告】非空，conflicts 数组第一位必须以"⚠️ 输入不完整："开头列出这些警告
- bias_checks 恰好 3 条，每条含 command + invalidation（失效条件）。"""

