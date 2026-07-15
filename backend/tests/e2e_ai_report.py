"""端到端验证：AKShare 拉数据 → 算指标 → 调 DeepSeek → 打印报告。

不依赖 sqlmodel/apscheduler，只测核心链路是否可用。

运行前确保：
  1) backend/.env 已配置 AI_API_KEY
  2) pip install --user akshare openai pandas numpy
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 手动加载 .env（避免依赖 pydantic_settings）
def _load_env():
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

import akshare as ak  # noqa: E402,F401  # 触发早期导入检查
from openai import OpenAI  # noqa: E402

from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from app.datasource.router import get_data_router  # noqa: E402
from app.indicators.engine import compute_all  # noqa: E402
from app.indicators.signals import scan_signals  # noqa: E402

CODE = "600519"
NAME = "贵州茅台"


def fetch_kline():
    end = date.today()
    start = end - timedelta(days=365 * 2)
    print(f"→ 通过 DataRouter 拉取 {CODE} {NAME} 的日线（{start} ~ {end}）")
    df = get_data_router().fetch_stock_daily(CODE, start, end, adjust="qfq")
    print(f"  ✓ 拉到 {len(df)} 根 K 线，最新日期 {df['trade_date'].iloc[-1]}")
    return df


def call_ai(indicators: dict) -> dict:
    api_key = os.environ.get("AI_API_KEY")
    base_url = os.environ.get("AI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("AI_MODEL", "deepseek-chat")
    if not api_key:
        raise RuntimeError("AI_API_KEY 未设置")

    print(f"→ 调用 {model} @ {base_url}")
    client = OpenAI(api_key=api_key, base_url=base_url)
    stock_info = {"code": CODE, "name": NAME, "market": "SH"}
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(stock_info, indicators, horizon="medium")},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)


def main():
    df = fetch_kline()

    print("→ 计算指标")
    indicators = compute_all(df)
    print(f"  ✓ 均线排列：{indicators['ma']['arrangement']}")
    print(f"  ✓ MACD 交叉：{indicators['oscillators']['macd']['cross']}")
    print(f"  ✓ 量比：{indicators['volume']['vol_ratio']}")
    print(f"  ✓ 形态：{indicators['patterns']}")
    print(f"  ✓ 20 日涨幅：{indicators['rs']['pct_20d']}%")

    print("→ 生成信号")
    signals = scan_signals(indicators)
    print(f"  ✓ 触发 {len(signals)} 条信号")
    for s in signals[:5]:
        print(f"    - [{s['direction']:8s}] {s['label']}  (weight={s['weight']})")

    report = call_ai(indicators)
    print("\n=" * 30)
    print("AI 报告：")
    print("=" * 60)
    print(f"倾向：{report.get('verdict')}  置信度：{report.get('confidence')}")
    print(f"摘要：{report.get('summary')}")
    print(f"关键信号：{report.get('key_signals')}")
    print(f"风险提示：{report.get('risks')}")
    print("\n--- Markdown 报告 ---")
    print(report.get("report_md", "")[:2000])
    print("=" * 60)


if __name__ == "__main__":
    main()
