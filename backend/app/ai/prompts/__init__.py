"""AI 提示词模板包。

所有外部 import 从这里获取，内部文件按 Agent 分组。
"""
from app.ai.prompts.bull_bear import (
    BULL_SYSTEM,
    BEAR_SYSTEM,
    JUDGE_SYSTEM,
    build_bull_prompt,
    build_bear_prompt,
    build_judge_prompt,
)
from app.ai.prompts.quant import (
    QUANT_SIMULATOR_SYSTEM,
    ANTI_QUANT_SYSTEM,
    build_quant_prompt,
    build_anti_quant_prompt,
)
from app.ai.prompts.reflexivity import (
    REFLEXIVITY_SYSTEM,
    build_reflexivity_prompt,
)
from app.ai.prompts.trader import (
    TRADER_SYSTEM,
    build_trader_prompt,
)
from app.ai.prompts.chat import (
    CHAT_SYSTEM,
)

__all__ = [
    "BULL_SYSTEM",
    "BEAR_SYSTEM",
    "JUDGE_SYSTEM",
    "build_bull_prompt",
    "build_bear_prompt",
    "build_judge_prompt",
    "QUANT_SIMULATOR_SYSTEM",
    "ANTI_QUANT_SYSTEM",
    "build_quant_prompt",
    "build_anti_quant_prompt",
    "REFLEXIVITY_SYSTEM",
    "build_reflexivity_prompt",
    "TRADER_SYSTEM",
    "build_trader_prompt",
    "CHAT_SYSTEM",
]
