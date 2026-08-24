# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包 spec：AI Stock Lens 可执行版（Windows onedir）。

用法（仓库根目录执行）：
    pyinstaller packaging/AI-Stock-Lens.spec
产物：dist/AI-Stock-Lens/AI-Stock-Lens.exe

要点：
- onedir 模式（启动快、便于排查）
- akshare 运行时懒加载大量子模块 → collect_submodules 全收集
- baostock / py_mini_racer 含原生扩展与数据文件 → collect_all 兜底
- 前端 dist 打进 _MEIPASS/frontend_dist（main.py 的 _static_dir 从这里读）
- console=True 保留控制台窗口（看日志、关闭即退出）
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND_DIST = os.path.join(ROOT, "frontend", "dist")

hiddenimports = collect_submodules("akshare") + ["py_mini_racer"]
datas = collect_data_files("akshare")
binaries = []

# baostock（.pyd 原生扩展）/ py_mini_racer（mini_racer.dll 二进制）→ collect_all 兜底
for pkg in ("baostock", "py_mini_racer"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 前端构建产物（需先 pnpm build）
if os.path.isdir(FRONTEND_DIST):
    datas += [(FRONTEND_DIST, "frontend_dist")]

# 种子库（CI 打包前 scripts/build_seed_db.py 生成；首启动复制为 data/app.db，
# 让搜索联想首搜即命中本地全 A 元数据）
SEED_DB = os.path.join(BACKEND, "seed.sqlite")
if os.path.exists(SEED_DB):
    datas += [(SEED_DB, ".")]

a = Analysis(
    [os.path.join(BACKEND, "run.py")],
    pathex=[BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="AI-Stock-Lens",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 保留控制台窗口：日志可见 + 关闭即退出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AI-Stock-Lens",
)
