"""可执行版启动入口（PyInstaller spec 的 entry point）。

双击运行：起本地 uvicorn + 自动打开浏览器。
保留控制台窗口：日志可见，关闭窗口即退出。
"""
from __future__ import annotations

import logging
import socket
import sys
import threading
import webbrowser

from app.main import app  # noqa: F401  # 直接传 app 实例，避免打包后字符串 import 失效


def _find_free_port(preferred: int = 8000) -> int:
    """从 preferred 开始找可用端口（被占则 +1）。

    不用 SO_REUSEADDR：macOS(BSD) 下它会允许绑定"已被 0.0.0.0 占用的具体地址"，
    导致探测失真；去掉后探测结果在各平台都严格可靠。
    """
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("找不到可用端口（8000-8049 均被占用）")


def main() -> None:
    port = _find_free_port()
    logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print("=" * 56)
    print("  AI Stock Lens 已启动")
    print(f"  地址：http://localhost:{port}  ·  浏览器即将自动打开")
    print("  关闭此窗口即退出程序。")
    print("=" * 56)

    # 等服务真正起来后再开浏览器
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
