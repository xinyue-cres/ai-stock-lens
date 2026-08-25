"""打包态首启动的种子库复制。

把打进包里的 seed.sqlite（全 A 元数据）复制为 data/app.db，让首搜零等待。
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _seed_from_bundle() -> None:
    """打包态首启动：data/app.db 不存在时，从打进包里的种子库（全 A 元数据）复制。

    让"添加股票"搜索联想首搜即命中本地，不用现场拉 20s 远程列表。
    种子随构建时间过时（新股/改名）由 search_stocks 的远程兜底自然补齐。
    源码开发态没有 _MEIPASS，直接跳过。

    假设：单实例启动（桌面应用双击启动一次）。双进程并发的 exists→copyfile 竞态
    未加文件锁——当前使用场景（桌面单机）不出现，若将来做分布式/服务化需补锁。
    """
    import shutil
    import sys

    if not getattr(sys, "frozen", False):
        return
    from app.config import get_settings

    db_path = Path(get_settings().db_path)
    if db_path.exists():
        return  # 已有库（老用户升级），不动
    seed = Path(getattr(sys, "_MEIPASS", "")) / "seed.sqlite"
    if not seed.exists():
        logger.warning("打包内未找到 seed.sqlite，首搜将走远程兜底")
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(seed, db_path)
    logger.info("首启动：已从种子库初始化 %s（全 A 元数据）", db_path)
