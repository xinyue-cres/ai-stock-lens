# 选股趋势状态机重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构选股趋势状态机：新增 `left_entry`（左侧机会）、`weak_golden`（弱势金叉）、启用 `strong_uptrend`（可持有不追高逢高减）三个状态，并把 K 线历史窗口从 500 根（2年）扩展到 1000 根（4年）。

**Architecture:** `trend_judge.py::_decide_stage` 是纯决策函数（无 I/O），从 `compute_indicator_cache` 读取 `adx`/`dif_slope`/`bar_shrinking` 等维度，产出 8 态之一。前端 `TrendStage` 类型、`STAGE_PALETTE`、`STAGE_LABEL` 三处同步新枚举。K 线窗口通过 `config.scan_kline_bars` 单点配置 + `scoring_service._load_cached_kline` 阈值联动。

**Tech Stack:** Python 3.11 / FastAPI / SQLModel / SQLite / React 18 / TypeScript / AntD / pydantic

## Global Constraints

- 前端 `TrendStage` 类型、`STAGE_PALETTE`（constants.ts）、后端 `STAGE_LABEL`（ai/prompts/_common.py）三处枚举文案必须一致（设计文档明确要求）。
- `can_entry` 保持布尔字段，不改 DB schema；两档区分由前端按 `trend_stage` 判断。
- 新增枚举：`left_entry`（左侧机会·高风险）、`weak_golden`（弱势金叉）、`strong_uptrend`（上升趋势·可持有不追高逢高减）。
- K 线窗口：`scan_kline_bars: 500 → 1000`，`_load_cached_kline` 缓存覆盖阈值 `≥400 → ≥1000`。
- `_decide_stage` 保持纯函数（无 I/O），可单测。
- 改状态机后需**重扫**才生效；不自动触发扫描。
- 提交信息格式：`<type>(score): <描述>`，英文。

---

### Task 1: `_decide_stage` 新增状态与判定分支

**Files:**
- Modify: `backend/app/features/trend_judge.py`
- Test: `backend/tests/test_trend_judge.py`

**Interfaces:**
- Consumes: `compute_indicator_cache` 的 `adx["adx"]`、`dif_slope`、`bar_shrinking`（已存在于 `judge_trend`）
- Produces: `_decide_stage(golden, pct_b, dist_high, signal_score, peak_winrate, bar_shrinking, adx, dif_slope) -> str`（新增 `adx: float | None`、`dif_slope: float | None` 两个参数，向后兼容默认 None）

- [ ] **Step 1: 写失败测试（纯逻辑分支）**

在 `test_trend_judge.py` 追加：

```python
# 新增分支：左侧机会 / 弱势金叉 / 上升趋势
def test_decide_stage_left_entry():
    # 死叉态 + 下跌过峰（bar_shrinking=False 绿柱回升）+ 历史可靠 → 左侧机会
    assert _decide_stage(golden=False, pct_b=0.5, dist_high=-0.3, signal_score=85,
                         bar_shrinking=False) == "left_entry"


def test_decide_stage_left_entry_rejected_if_unreliable():
    # 死叉 + 过峰但历史差 → 仍下跌
    assert _decide_stage(golden=False, pct_b=0.5, dist_high=-0.3, signal_score=50,
                         bar_shrinking=False) == "downtrend"


def test_decide_stage_weak_golden():
    # 金叉态 + 柱体缩小（上涨过峰）→ 弱势金叉，别追
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.2, signal_score=85,
                         bar_shrinking=True) == "weak_golden"


def test_decide_stage_strong_uptrend():
    # 金叉态 + ADX 强 + 已涨 + 柱体未缩小 → 可持有不追高
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.1, signal_score=85,
                         bar_shrinking=False, adx=30.0, dif_slope=0.1) == "strong_uptrend"


def test_decide_stage_strong_uptrend_needs_adx():
    # ADX 弱 → 不判强趋势，走普通可入手
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.1, signal_score=85,
                         bar_shrinking=False, adx=15.0, dif_slope=0.1) == "pullback_entry"


def test_decide_stage_overheat_strong_trend():
    # 强趋势 + 贴上轨 → 仍是过热（过热度优先于强趋势）
    assert _decide_stage(golden=True, pct_b=0.9, dist_high=-0.1, signal_score=85,
                         bar_shrinking=False, adx=30.0) == "overheat"
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_trend_judge.py -k "left_entry or weak_golden or strong_uptrend or overheat_strong" -v`
Expected: FAIL（`_decide_stage` 不接受 `adx`/`dif_slope` 参数）

- [ ] **Step 3: 实现新决策分支**

修改 `trend_judge.py`：

```python
def _decide_stage(golden: bool, pct_b: float | None, dist_high: float,
                  signal_score: float | None, peak_winrate: float | None = None,
                  bar_shrinking: bool | None = None,
                  adx: float | None = None, dif_slope: float | None = None) -> str:
    if golden:
        # 1. 过热度（非强趋势才叫过热；强趋势贴轨是顺势）
        if pct_b is not None and pct_b > 0.85:
            return "overheat"
        # 2. 强趋势中已涨一段 → 可持有·不追高·逢高减
        if adx is not None and adx >= 25 and dif_slope is not None and dif_slope > 0:
            return "strong_uptrend"
        if dist_high < -0.4 and (signal_score is None or signal_score < _SIGNAL_RELIABLE):
            return "downtrend"
        if bar_shrinking is True:
            return "weak_golden"  # 金叉但动能掉头 → 弱势金叉，别追
        if signal_score is not None and signal_score >= _SIGNAL_RELIABLE:
            if peak_winrate is not None and peak_winrate < 50:
                return "range"
            return "pullback_entry"
        if pct_b is None or pct_b >= 0.2:
            return "pullback_entry"
        return "range"
    # 死叉态
    if bar_shrinking is False and signal_score is not None and signal_score >= _SIGNAL_RELIABLE:
        return "left_entry"  # 下跌过峰 + 历史可靠 → 左侧机会
    if dist_high > -0.1 or (signal_score is None or signal_score < _SIGNAL_RELIABLE):
        return "downtrend"
    return "range"
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_trend_judge.py -k "left_entry or weak_golden or strong_uptrend or overheat_strong" -v`
Expected: PASS（6 个新测试通过）

- [ ] **Step 5: 修复受影响的旧测试断言**

现有测试在 `test_decide_stage_golden_reliable` 用 `signal_score=70`（<72）期望 `pullback_entry`，`test_decide_stage_golden_space` 用 `signal_score=50` 期望 `pullback_entry`——这些在纯逻辑里不受影响（未传 adx/bar_shrinking）。但 `test_decide_stage_deadcross` 断言 `golden=False, signal=85 → range`，现在死叉态若 `bar_shrinking` 默认 None（既不 True 也不 False），走 `range` 仍成立。运行全量测试确认：

Run: `PYTHONPATH=. python -m pytest tests/test_trend_judge.py -v`
Expected: 全部 PASS（若某个旧断言因新分支变化失败，调整该断言以匹配新语义）

- [ ] **Step 6: 提交**

```bash
git add backend/app/features/trend_judge.py backend/tests/test_trend_judge.py
git commit -m "feat(score): add left_entry/weak_golden/strong_uptrend to trend decision tree"
```

---

### Task 2: `judge_trend` 传入 adx/dif_slope + 更新 STAGE_LABEL

**Files:**
- Modify: `backend/app/features/trend_judge.py`
- Modify: `backend/app/ai/prompts/_common.py`
- Test: `backend/tests/test_trend_judge.py`

**Interfaces:**
- Consumes: Task 1 的 `_decide_stage` 新签名；`compute_indicator_cache` 的 `adx`/`dif_slope`/`bar_shrinking`
- Produces: `judge_trend` 传入新维度；`STAGE_LABEL` 含 3 个新枚举文案

- [ ] **Step 1: `judge_trend` 传入 adx/dif_slope**

在 `trend_judge.py` 的 `judge_trend` 中，把 `adx_info`、`dif_slope` 传入 `_decide_stage`：

```python
    # 决策：金叉死叉为主导（纯逻辑，见 _decide_stage）
    stage = _decide_stage(golden, pct_b, dist_high, signal_score, peak_winrate,
                          bar_shrinking, adx=adx_info.get("adx"), dif_slope=dif_slope)
```

（`dif_slope` 和 `adx_info` 已在 `judge_trend` 作用域内，见 106-110 行；无需新引入。）

- [ ] **Step 2: 更新 `STAGE_LABEL`**

在 `_common.py` 更新：

```python
STAGE_LABEL = {
    "strong_uptrend": "上升趋势",
    "pullback_entry": "回踩可入手",
    "overheat": "过热",
    "weak_golden": "弱势金叉",
    "left_entry": "左侧机会",
    "downtrend": "下跌趋势",
    "range": "震荡",
    "insufficient": "数据不足",
}
```

- [ ] **Step 3: 更新 `_REASONS` 与 `_entry_reason`**

在 `trend_judge.py`：

```python
_REASONS = {
    "pullback_entry": "金叉态·上方空间足，可入手",
    "overheat": "金叉态但贴上轨（短期过热），等回踩",
    "strong_uptrend": "金叉态·强趋势已涨，可持有·不追高·逢高减",
    "weak_golden": "金叉态·动能掉头（上涨过峰），别追等回踩",
    "left_entry": "死叉态·下跌动能衰竭（下跌过峰），高风险左侧机会·轻仓",
    "downtrend": "死叉态·历史金叉延续差，回避",
    "range": "观望（等金叉或信号不明）",
    "insufficient": "历史数据不足（需 ≥60 根日线）",
}
```

并在 `_entry_reason` 增加两条细化。`_entry_reason` 签名从
`(stage, golden, bar_shrinking, signal_score, peak_winrate)` 改为
`(stage, golden, bar_shrinking, signal_score, peak_winrate, adx, dif_slope)`：

```python
def _entry_reason(stage: str, golden: bool, bar_shrinking: bool | None,
                  signal_score: float | None, peak_winrate: float | None,
                  adx: float | None = None, dif_slope: float | None = None) -> str:
    """细化 entry_reason：覆盖决策树降级的具体原因。"""
    if golden and bar_shrinking:
        return "金叉态·MACD柱掉头（上涨过峰预警），观望"
    if golden and adx is not None and adx >= 25 and dif_slope is not None and dif_slope > 0:
        return "金叉态·强趋势已涨，可持有·不追高·逢高减"
    if not golden and bar_shrinking is False and signal_score is not None and signal_score >= _SIGNAL_RELIABLE:
        return "死叉态·下跌过峰（动能衰竭）+ 历史可靠，左侧机会·建议轻仓"
    if golden and signal_score is not None and signal_score >= _SIGNAL_RELIABLE \
            and peak_winrate is not None and peak_winrate < 50:
        return "金叉态·历史峰值胜率低（<50%），观望"
    return _REASONS.get(stage, "")
```

`judge_trend` 末尾调用处同步传参：

```python
        "entry_reason": _entry_reason(stage, golden, bar_shrinking, signal_score,
                                      peak_winrate, adx=adx_info.get("adx"), dif_slope=dif_slope),
```

- [ ] **Step 4: 运行测试确认**

Run: `PYTHONPATH=. python -m pytest tests/test_trend_judge.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/features/trend_judge.py backend/app/ai/prompts/_common.py
git commit -m "feat(score): wire adx/dif_slope into judge_trend, update stage labels"
```

---

### Task 3: 模型字段 description 更新 + K 线窗口 500→1000

**Files:**
- Modify: `backend/app/models/stock_score.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/scoring_service.py`

**Interfaces:**
- Consumes: 无（纯配置/注释变更）
- Produces: `scan_kline_bars=1000`；`_load_cached_kline` 阈值 `≥1000`

- [ ] **Step 1: 更新模型字段 description**

`stock_score.py` 第 30 行：

```python
    trend_stage: str | None = Field(default=None, description="strong_uptrend/pullback_entry/overheat/weak_golden/left_entry/downtrend/range/insufficient")
```

- [ ] **Step 2: 更新 K 线窗口配置**

`config.py`：

```python
    scan_concurrency: int = 12
    scan_kline_bars: int = 1000  # 扫描拉取约 4 年（覆盖完整牛熊周期）
```

`config.py` 的 `scan_kline_days` 属性注释更新：

```python
    @property
    def scan_kline_days(self) -> int:
        """扫描拉取的自然日窗口：1000 交易日 ≈ 1.4 倍自然日 ≈ 4 年。"""
        return int(self.scan_kline_bars * 1.4)
```

- [ ] **Step 3: 更新缓存覆盖阈值**

`scoring_service.py`：

```python
def _fetch_kline(code: str, settings) -> object | None:
    """拉近 ~1000 根日线（优先用库内 K 线缓存，缺失才拉网络）。带限流 sleep。"""
    try:
        end = date.today()
        start = end - timedelta(days=settings.scan_kline_days)  # 约 4 自然年 ≈ 1000 交易日
```

```python
    if len(rows) < 1000:
        return None
```

同时更新文件顶部 docstring 的 "~500 根" → "~1000 根"。

- [ ] **Step 4: 确认无其他引用旧值**

Run: `grep -rn "scan_kline_bars\|< 400\|500 根\|2 自然年\|2 年" backend/app/ | grep -v __pycache__`
Expected: 无残留旧值引用（或全部已更新）

- [ ] **Step 5: 语法检查**

Run: `python -m py_compile backend/app/models/stock_score.py backend/app/config.py backend/app/services/scoring_service.py`
Expected: 无输出（成功）

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/stock_score.py backend/app/config.py backend/app/services/scoring_service.py
git commit -m "feat(score): extend kline window to 4y + update stage enum description"
```

---

### Task 4: 前端类型 + STAGE_PALETTE + 两档展示

**Files:**
- Modify: `frontend/src/api/score.ts`
- Modify: `frontend/src/pages/Scoreboard/constants.ts`
- Modify: `frontend/src/pages/Scoreboard/components/ScoreRow.tsx`
- Modify: `frontend/src/pages/Scoreboard/components/ScoreDetail.tsx`

**Interfaces:**
- Consumes: 后端新 `trend_stage` 枚举值
- Produces: 前端 `TrendStage` 类型、`STAGE_PALETTE` 样式、两档 `can_entry` 展示

- [ ] **Step 1: 更新 `TrendStage` 类型**

`api/score.ts`：

```typescript
export type TrendStage =
  | 'strong_uptrend'
  | 'pullback_entry'
  | 'overheat'
  | 'weak_golden'
  | 'left_entry'
  | 'downtrend'
  | 'range'
  | 'insufficient'
```

- [ ] **Step 2: 更新 `STAGE_PALETTE`**

`constants.ts`：

```typescript
export const STAGE_PALETTE: Record<TrendStage, StagePalette> = {
  pullback_entry: { label: '可入手', color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
  left_entry: { label: '左侧·轻仓', color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe' },
  strong_uptrend: { label: '上升趋势', color: '#b91c1c', bg: '#fff7ed', border: '#fed7aa' },
  overheat: { label: '过热', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  weak_golden: { label: '弱势金叉', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  range: { label: '震荡', color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  downtrend: { label: '下跌趋势', color: '#059669', bg: '#ecfdf5', border: '#a7f3d0' },
  insufficient: { label: '数据不足', color: '#6b7280', bg: '#f3f4f6', border: '#e5e7eb' },
}
```

- [ ] **Step 3: `ScoreRow` 两档展示（左侧机会高风险提示）**

在 `ScoreRow.tsx` 的趋势徽章区域，对 `left_entry` 加高风险提示（Tag 已由 STAGE_PALETTE 上色，附加 tooltip）：

```tsx
      {stage && (
        <Tag
          style={{ margin: 0, marginLeft: 6, color: stage.color, borderColor: stage.border, background: stage.bg, fontSize: 11, flexShrink: 0 }}
        >
          {stage.label}
        </Tag>
      )}
      {item.trend_stage === 'left_entry' && (
        <Tooltip title="死叉下跌动能衰竭的左侧机会，逆势·高风险，建议轻仓">
          <span style={{ fontSize: 10, marginLeft: 6, color: '#7c3aed', flexShrink: 0 }}>⚠逆势</span>
        </Tooltip>
      )}
```

- [ ] **Step 4: `ScoreDetail` 两档区分文案**

`ScoreDetail.tsx` 在 stage Tag 旁，区分可入手两档：

```tsx
            {stage && <Tag style={{ color: stage.color, borderColor: stage.border, background: stage.bg }}>{stage.label}</Tag>}
            {detail.trend_stage === 'left_entry' && (
              <Tag style={{ color: '#7c3aed', borderColor: '#ddd6fe', background: '#f5f3ff' }}>高风险·轻仓</Tag>
            )}
```

（若该文件已有类似 entry_reason 展示，确保 `left_entry` 时 entry_reason 提示"轻仓"。）

- [ ] **Step 5: 前端类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: EXIT=0

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/score.ts frontend/src/pages/Scoreboard/constants.ts frontend/src/pages/Scoreboard/components/ScoreRow.tsx frontend/src/pages/Scoreboard/components/ScoreDetail.tsx
git commit -m "feat(score): frontend support for left_entry/weak_golden/strong_uptrend + two-tier entry display"
```

---

### Task 5: 端到端验证

**Files:**
- Test: 后端单测 + 前端类型检查

- [ ] **Step 1: 后端全量单测**

Run: `cd backend && PYTHONPATH=. python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 2: 前端类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: EXIT=0

- [ ] **Step 3: 重启后端确认启动正常**

Run: `cd /Users/zhangguiyang.15/Desktop/personal/ai-stock-lens && ./dev.sh restart`
Expected: 前后端启动成功，`curl http://localhost:8000/api/health` 返回 ok

- [ ] **Step 4: 确认新枚举已入库（抽查现有打分）**

Run: `curl -s "http://localhost:8000/api/score/list?scope=watchlist&limit=5" | python3 -m json.tool | grep trend_stage`
Expected: 返回 trend_stage 字段（旧批次可能仍是旧枚举，重扫后才是新枚举——此处仅确认接口正常）

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "chore(score): end-to-end verification of trend stage machine refactor"
```

---

## 重扫提醒

状态机与 K 线窗口都改了，需**重扫**才能让排行反映新状态机与 4 年窗口。按用户约束不自动触发，由用户在选股页手动点「开始扫描」。重扫后抽查：
- 死叉 + 下跌过峰 + 历史可靠 → 「左侧机会」
- 金叉 + 柱体缩小 → 「弱势金叉」
- 强趋势金叉已涨 → 「上升趋势」
- 金叉回踩历史可靠 → 「可入手」
- `signal_count` 显著大于 38（4 年窗口样本更多）
