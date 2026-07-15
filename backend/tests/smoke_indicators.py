"""指标层烟雾测试：用合成数据跑一遍，验证 shape 与关键字段。

不依赖网络与 AKShare，用 pandas 生成随机日线数据即可。
运行：pip install pandas numpy && python -m tests.smoke_indicators
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.indicators.engine import build_chart_series, compute_all


def _gen_df(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = [date.today() - timedelta(days=n - i) for i in range(n)]
    close = 10 + np.cumsum(rng.normal(0, 0.3, n))
    open_ = close + rng.normal(0, 0.1, n)
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.15, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.15, n))
    volume = rng.integers(1_000_000, 5_000_000, n)
    amount = volume * close
    turnover = rng.uniform(0.5, 5, n)
    pct_chg = pd.Series(close).pct_change().fillna(0).values * 100

    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": amount,
            "turnover": turnover,
            "pct_chg": pct_chg,
        }
    )


def main():
    df = _gen_df(300)

    ind = compute_all(df)
    assert "as_of_date" in ind, "缺 as_of_date"
    assert "ma" in ind and "ma5" in ind["ma"], "缺 MA"
    assert ind["ma"]["arrangement"] in ("bullish", "bearish", "tangled", "insufficient")
    assert "oscillators" in ind and "macd" in ind["oscillators"], "缺 MACD"
    assert "rsi6" in ind["oscillators"]["rsi"], "缺 RSI"
    assert "kdj" in ind["oscillators"], "缺 KDJ"
    assert "boll" in ind["oscillators"], "缺 BOLL"
    assert "volume" in ind and "vol_ratio" in ind["volume"], "缺量比"
    assert "patterns" in ind, "缺 patterns"
    assert "rs" in ind and "pct_20d" in ind["rs"], "缺 RS"

    series = build_chart_series(df)
    assert len(series["candles"]) == 300, f"candles 数量错，实际 {len(series['candles'])}"
    assert len(series["volumes"]) == 300
    assert len(series["ma5"]) > 0
    assert set(series["candles"][0].keys()) == {"time", "open", "high", "low", "close"}
    assert set(series["volumes"][0].keys()) == {"time", "value", "color"}

    print("✓ compute_all OK, keys:", list(ind.keys()))
    print("✓ build_chart_series OK, candles:", len(series["candles"]))
    print("✓ MA arrangement:", ind["ma"]["arrangement"])
    print("✓ MACD cross:", ind["oscillators"]["macd"]["cross"])
    print("✓ vol_ratio:", ind["volume"]["vol_ratio"])
    print("✓ patterns:", ind["patterns"])


if __name__ == "__main__":
    main()
