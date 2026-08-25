"""趋势/可入手判断（金叉驱动）：MACD 金叉死叉为主导，BOLL + 距高点衡量潜在空间。

决策口径：
- 金叉态（DIF > DEA）= 上升候选：
  - 贴上轨（%B 高）且非强趋势 → 短期过热，等回踩
  - ADX 强 + 已涨一段 + 动能未急刹 → 强趋势，可持有·不追高·逢高减
  - 距 60 日高点回撤极深（<-40%）且历史金叉延续差 → 深跌中刚金叉，不可靠
  - 动能掉头（顶部过峰放量确认 / 金叉·走弱动能衰减）→ 弱势金叉，别追
  - 历史金叉延续可靠（signal 分高）→ 可入手
  - 否则只要未过热、有空间 → 可入手
- 死叉态：下跌过峰 + 历史可靠 → 左侧机会（高风险可轻仓）；历史可靠 → 等下次金叉；
  距高点近或历史差 → 下跌趋势回避

MA 结构 / ADX / RSI 降为辅助参考（indicators），不再一票否决——MA 滞后，
反映不了 MACD 金叉的即时信号（实测高分股金叉态却被 MA 空头误判 downtrend）。
"""
from __future__ import annotations

import pandas as pd

from app.features.scoring import _PEAK_CONF_STRONG, _PEAK_CONF_STRONG_BY_TF, _signal_summary, compute_indicator_cache
from app.indicators.ma import compute_ma

_MIN_ROWS = 60  # MACD EMA26 预热需要 ~60 根

# 金叉延续分阈值：>= 此值视为历史金叉可靠
# 含金叉日跳涨后评分整体上移（中位 ~72），原 65 已无区分度（95% 达标），上调到 72
_SIGNAL_RELIABLE = 72

# 左侧机会（死叉态博反弹）的历史可靠门槛：低于金叉态可入手线（72）——
# 下跌过峰多为长期弱势股，历史金叉延续分天然偏低（实测全库 63~70），拿金叉标准卡
# 死叉态逻辑矛盾（可靠早就该金叉了），导致 left_entry 全库为 0。经验值 64 使今日
# 唯一强档下跌过峰（福耀 64.2）可进。
_LEFT_ENTRY_SIGNAL = 64

# ADX 强趋势判定线（经验值，上线后可数据校准）
_ADX_STRONG = 25

# 强趋势"已涨一段"门槛（% 涨幅）
_STRONG_TREND_GAIN = 8.0

_REASONS = {
    "pullback_entry": "金叉态·上方空间足，可入手",
    "left_entry": "死叉态·下跌动能衰竭（下跌过峰），高风险左侧机会·轻仓",
    "strong_uptrend": "金叉态·强趋势已涨，可持有·不追高·逢高减",
    "weak_golden": "金叉态·动能掉头（上涨过峰），别追等回踩",
    "overheat": "金叉态但贴上轨（短期过热），等回踩",
    "downtrend": "死叉态·历史金叉延续差，回避",
    "range": "观望（等金叉或信号不明）",
    "insufficient": "历史数据不足（需 ≥60 根日线）",
}


def _decide_stage(golden: bool, pct_b: float | None, dist_high: float,
                  signal_score: float | None, peak_winrate: float | None = None,
                  peak_conf: int = 0, slope_up: bool | None = None,
                  adx: float | None = None,
                  signal_gain_pct: float | None = None,
                  peak_signal: str | None = None,
                  timeframe: str = "daily") -> str:
    """金叉驱动的阶段决策（纯逻辑，无 I/O，可直接单测）。

    - 金叉态 = 上升候选：贴上轨且非强趋势→过热；ADX 强且已涨一段→强趋势
      （可持有·不追高·逢高减）；深跌且历史差→下跌；动能急刹（顶部过峰预警）
      →弱势金叉，别追；历史可靠→可入手；未过热有空间→可入手；
      否则贴下轨（%B<0.2 弱势）→震荡
    - 死叉态：下跌动能急转（底部过峰）且历史可靠→左侧机会；否则历史可靠→观望等下次金叉；
      距高点过近或历史差→下跌回避
    peak_winrate：历史金叉冲过 +5% 的占比；peak_conf：过峰置信度 0-100（bar|acc_z × 量能），
    强档以上(≥_PEAK_CONF_STRONG)才认定"动能急刹/急转"；slope_up：动能方向（顶/底）。
    peak_signal：完整位置标签（四象限：上涨过峰/顶部回落=水上衰竭偏空预警，
    下跌过峰/底部反转=水下衰竭偏多预警）。peak_top 组=水上（拦金叉追入），
    peak_bot 组=水下（喂 left_entry）；兼容老调用方回退到 slope_up 判定。
    adx：ADX 趋势强度；signal_gain_pct：当前信号期间累计涨幅%（% 为单位，如 10.5 表示 10.5%）
    """
    # 顶/底判定：优先按 peak_signal 位置标签（含 dif 位置语义），slope_up 仅作方向
    # 强档阈值按 timeframe 校准：weekly 的 acc_z 分布系统性偏低，沿用 daily=51 会无人触发
    conf_strong = _PEAK_CONF_STRONG_BY_TF.get(timeframe, _PEAK_CONF_STRONG)
    if peak_signal:
        peak_top = peak_conf >= conf_strong and peak_signal in ("上涨过峰", "顶部回落")
        peak_bot = peak_conf >= conf_strong and peak_signal in ("下跌过峰", "底部反转")
    else:
        peak_top = peak_conf >= conf_strong and slope_up is True
        peak_bot = peak_conf >= conf_strong and slope_up is False
    if golden:
        # 1. 过热度（贴顶只在没有强趋势授权时才算）。
        #    pct_b>1.10 本身不是"过热"标志——强趋势（ADX≥25）的 momentum breakout
        #    经常以贴上轨开启主升浪，无脑拦截会错过（000703 恒逸石化 pct_b=1.14, ADX=48.7
        #    今日突破新高 +19% 周线巨长阳，是该追不该避）。
        #    所以贴上轨只在 ADX 弱（趋势力不足）时才 alert。
        if pct_b is not None and pct_b > 1.10 and (adx is None or adx < _ADX_STRONG):
            return "overheat"  # 贴顶但趋势不硬：继续追涨胜率低
        if pct_b is not None and pct_b > 0.85 and (adx is None or adx < _ADX_STRONG):
            return "overheat"  # 贴上轨、非强趋势，短期涨过头
        # 2. 强趋势中已涨一段 → 可持有·不追高·逢高减（动能未急刹）
        if (adx is not None and adx >= _ADX_STRONG
                and signal_gain_pct is not None and signal_gain_pct > _STRONG_TREND_GAIN
                and not peak_top):
            return "strong_uptrend"
        if dist_high < -0.4 and (signal_score is None or signal_score < _SIGNAL_RELIABLE):
            return "downtrend"  # 深跌中刚金叉且历史不可靠
        if peak_top or slope_up is False:
            return "weak_golden"  # 金叉但动能掉头（顶部过峰 / 金叉·走弱）→ 弱势金叉，别追
        if signal_score is not None and signal_score >= _SIGNAL_RELIABLE:
            if peak_winrate is not None and peak_winrate < 50:
                return "range"  # 历史分高但胜率不足（过半金叉没冲过 +5%），可靠性打折
            return "pullback_entry"  # 金叉 + 历史可靠 → 可入手
        if pct_b is None or pct_b >= 0.2:
            return "pullback_entry"  # 金叉、未过热、有上方空间
        return "range"  # 金叉但贴下轨（弱势）
    # 死叉态
    if peak_bot and signal_score is not None and signal_score >= _LEFT_ENTRY_SIGNAL:
        return "left_entry"  # 下跌动能急转（底部过峰）+ 历史尚可 → 左侧机会
    if dist_high > -0.1 or (signal_score is None or signal_score < _SIGNAL_RELIABLE):
        return "downtrend"  # 距高点近或历史差 → 回避
    return "range"


def _entry_reason(stage: str, golden: bool, peak_conf: int, slope_up: bool | None,
                  signal_score: float | None, peak_winrate: float | None,
                  adx: float | None = None, signal_gain_pct: float | None = None,
                  peak_signal: str | None = None,
                  timeframe: str = "daily") -> str:
    """细化 entry_reason：覆盖决策树降级的具体原因。"""
    # 顶/底判定优先按 peak_signal 位置标签（含 dif 位置语义）；
    # 老调用方未传 peak_signal 时回退到 slope_up 单方向判定
    conf_strong = _PEAK_CONF_STRONG_BY_TF.get(timeframe, _PEAK_CONF_STRONG)
    if peak_signal:
        peak_top = peak_conf >= conf_strong and peak_signal in ("上涨过峰", "顶部回落")
        peak_bot = peak_conf >= conf_strong and peak_signal in ("下跌过峰", "底部反转")
    else:
        peak_top = peak_conf >= conf_strong and slope_up is True
        peak_bot = peak_conf >= conf_strong and slope_up is False
    if golden and peak_top:
        if peak_signal == "顶部回落":
            return "金叉态·高位回落首波（顶部回落预警），别追等企稳"
        return "金叉态·动能急刹（上涨过峰预警），别追等回踩"
    if golden and slope_up is False:
        return "金叉态·动能走弱（金叉衰减），随时可能死叉，别追等动能修复"
    if golden and adx is not None and adx >= _ADX_STRONG \
            and signal_gain_pct is not None and signal_gain_pct > _STRONG_TREND_GAIN \
            and not peak_top:
        return "金叉态·强趋势已涨，可持有·不追高·逢高减"
    if not golden and peak_bot and signal_score is not None and signal_score >= _LEFT_ENTRY_SIGNAL:
        return "死叉态·下跌动能急转（底部过峰）+ 历史尚可，左侧机会·建议轻仓"
    if golden and signal_score is not None and signal_score >= _SIGNAL_RELIABLE \
            and peak_winrate is not None and peak_winrate < 50:
        return "金叉态·历史峰值胜率低（<50%），观望"
    return _REASONS.get(stage, "")


def judge_trend(df: pd.DataFrame, signal_score: float | None = None,
                cache: dict | None = None, timeframe: str = "daily") -> dict:
    """对单只标的做金叉驱动的趋势/可入手判断。

    df 需含 trade_date/open/high/low/close/volume/amount/turnover/pct_chg（升序）。
    signal_score 为金叉延续性分（0-100，历史可靠性），由打分引擎提供，可 None。
    cache：compute_indicator_cache 预计算指标（扫描复用，避免同一 df 重复算
    MACD/ADX/BOLL/Risk/峰值胜率）；独立调用（详情页）不传则内部自行计算一次。
    返回 {trend_stage, can_entry, entry_reason, key_prices, indicators}。
    """
    if df is None or df.empty or len(df) < _MIN_ROWS:
        return {
            "trend_stage": "insufficient",
            "can_entry": False,
            "entry_reason": "历史数据不足（需 ≥60 根日线）",
            "key_prices": {},
            "indicators": {},
        }
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date").reset_index(drop=True)

    # 复用打分引擎的指标缓存（无则自行计算一次），避免重复算 MACD/ADX/BOLL/Risk
    if cache is None:
        cache = compute_indicator_cache(df)
    close_s = cache["close"]
    dif = cache["dif"]
    dea = cache["dea"]
    close = float(close_s.iloc[-1])
    golden = cache["golden"]
    dif_slope = cache["dif_slope"]
    peak_conf = cache.get("peak_conf", 0)
    slope_up = cache.get("slope_up")
    peak_winrate = cache["peak_winrate"]
    boll = cache["boll"]
    adx_info = cache["adx"]
    stop_loss = cache["risk"].get("stop_loss_hint")

    # 潜在空间：BOLL %B/带宽 + 距 60 日高点回撤
    pct_b = boll["pct_b"]
    bandwidth = boll["bandwidth"]
    high_60 = float(df["high"].tail(60).max()) if len(df) >= 60 else float(df["high"].max())
    dist_high = close / high_60 - 1 if high_60 else 0.0

    # 当前信号期间涨幅（金叉后已涨一段 = 强趋势别追高的判据；复用打分引擎统计）
    sig_summary = _signal_summary(close_s, cache["signals"], cache.get("cycles"))
    signal_gain_pct = sig_summary.get("signal_gain_pct")

    # 决策：金叉死叉为主导（纯逻辑，见 _decide_stage）。
    # 传 peak_signal 全标签（含 dif 位置），不用 slope_up 单方向判断顶/底——避免
    # "dif<0+slope_up=True 底部抬头β"被误识为顶部过峰进而漏掉 left_entry。
    stage = _decide_stage(golden, pct_b, dist_high, signal_score, peak_winrate,
                          peak_conf, slope_up, adx=adx_info.get("adx"),
                          signal_gain_pct=signal_gain_pct,
                          peak_signal=cache.get("peak_signal"),
                          timeframe=timeframe)

    # 辅助参考（不参与决策）
    arrangement = compute_ma(df).get("arrangement")

    ma20 = boll["middle"]
    ma60 = float(close_s.rolling(60).mean().iloc[-1]) if len(df) >= 60 else None
    ma120 = float(close_s.rolling(120).mean().iloc[-1]) if len(df) >= 120 else None

    return {
        "trend_stage": stage,
        # 可入手两档：pullback_entry（安全可入手）+ left_entry（左侧机会·高风险可轻仓）
        "can_entry": stage in ("pullback_entry", "left_entry"),
        "entry_reason": _entry_reason(stage, golden, peak_conf, slope_up, signal_score, peak_winrate,
                                      adx=adx_info.get("adx"), signal_gain_pct=signal_gain_pct,
                                      peak_signal=cache.get("peak_signal"),
                                      timeframe=timeframe),
        "key_prices": {
            "close": round(close, 3),
            "ma20": round(ma20, 3) if ma20 is not None else None,
            "ma60": round(ma60, 3) if ma60 is not None else None,
            "ma120": round(ma120, 3) if ma120 is not None else None,
            "resistance_60d": round(high_60, 3),
            "stop_loss": stop_loss,
        },
        "indicators": {
            "adx": adx_info["adx"],
            "plus_di": adx_info["plus_di"],
            "minus_di": adx_info["minus_di"],
            "arrangement": arrangement,
            # 金叉 + 空间因子
            "golden": golden,
            "dif": round(float(dif.iloc[-1]), 4) if pd.notna(dif.iloc[-1]) else None,
            "dea": round(float(dea.iloc[-1]), 4) if pd.notna(dea.iloc[-1]) else None,
            "dif_slope": dif_slope,
            "pct_b": round(pct_b, 3) if pct_b is not None else None,
            "bandwidth": round(bandwidth, 4) if bandwidth is not None else None,
            "dist_high_60_pct": round(dist_high * 100, 2),
        },
    }
