# -*- mode: python ; coding: utf-8 -*-
r"""
PyInstaller 规格文件：从项目根目录的 main.py 打包 QwenPaw（控制台 CLI）。

构建（在项目根目录执行，且已安装 pyproject 中的依赖，建议使用 venv）：
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-windows.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-paw.ps1

输出（目录模式 onedir）：
  - dist/paw/paw.exe 与同目录的 _internal/ 必须一起发布。
  - scripts/build-paw.ps1 另外生成应用包 dist/paw-runtime.zip 和独立工具包 dist/runtimes.zip。
  - Playwright 浏览器需另外安装，浏览器二进制不打进 exe。
"""
from __future__ import annotations

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

# 项目根目录（与 paw.spec 同目录）
try:
    ROOT = os.path.dirname(os.path.abspath(SPEC))
except NameError:  # 直接以 python paw.spec 调试时
    ROOT = os.path.dirname(os.path.abspath(__file__))

SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

MAIN_SCRIPT = os.path.join(ROOT, "main.py")

# Web 控制台静态资源：与源码布局一致放进包内 qwenpaw/console（见 qwenpaw/app/_app.py::_resolve_console_static_dir）。
# 须先在 console/ 执行前端构建（npm ci && npm run build），生成 console/dist（index.html + assets/）。
# 运行时浏览器加载的是构建产物；npm 依赖已由 Vite 打进 dist，无需也不会打包 node_modules。
# hook 风格二元组 (源路径, 目标相对目录)，见 PyInstaller format_binaries_and_datas；
# 源为目录时会递归拷贝，不能用 Tree 对象（Analysis 仅接受二元组）。
_CONSOLE_DIST = os.path.normpath(os.path.join(ROOT, "console", "dist"))
_console_datas_entry = None
if os.path.isdir(_CONSOLE_DIST) and os.path.isfile(
    os.path.join(_CONSOLE_DIST, "index.html"),
):
    _console_datas_entry = (_CONSOLE_DIST, "qwenpaw/console")
else:
    raise FileNotFoundError(
        "未找到 console/dist/index.html。请运行 scripts/build-paw.ps1 构建前端。",
    )

# qwenpaw 包：数据、.pyd/.dll、全部子模块（含 cli 懒加载），并复制发行元数据
pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(
    "qwenpaw",
    include_py_files=False,
)
pkg_datas = [
    entry
    for entry in pkg_datas
    if "qwenpaw/agents/bundled_workspaces" not in entry[1].replace("\\", "/")
]

# reme-ai（import: reme）：ReMeConfigParser 在 reme/config/ 下解析 light.yaml 等，未收集会 FileNotFoundError
reme_datas, reme_binaries, reme_hiddenimports = collect_all(
    "reme",
    include_py_files=False,
)

datas = list(pkg_datas) + list(reme_datas)
if _console_datas_entry is not None:
    datas.insert(0, _console_datas_entry)
_BUNDLED_AGENTS_ZIP = os.path.normpath(
    os.path.join(ROOT, "src", "qwenpaw", "agents", "bundled_workspaces.zip"),
)
if os.path.isfile(_BUNDLED_AGENTS_ZIP):
    datas.insert(
        0,
        (_BUNDLED_AGENTS_ZIP, "qwenpaw/agents"),
    )
binaries = list(pkg_binaries) + list(reme_binaries)
hiddenimports = list(pkg_hiddenimports) + list(reme_hiddenimports)

# Glob 动态导入此资源包，再按文件路径读取/执行 _glob_helper.py；
# 必须同时收集包和原始 .py 文件，仅收集 PYZ 字节码不能提供脚本文件。
hiddenimports.append("agentscope.tool._builtin._scripts")
datas += collect_data_files(
    "agentscope.tool._builtin._scripts",
    include_py_files=True,
)

# 时区数据（tzdata）
try:
    datas += copy_metadata("tzdata")
except Exception:
    pass

# importlib.metadata / version 查询：需带上对应发行版的 .dist-info，否则报 PackageNotFoundError
for _meta_pkg in (
    "fastmcp",
    "mcp",
):
    try:
        datas += copy_metadata(_meta_pkg)
    except Exception:
        pass

# 若运行时报 SSL/证书相关错误，可取消下一行注释
# try:
#     import certifi
#     datas += [(certifi.where(), "certifi")]
# except Exception:
#     pass

# 部分依赖在运行时仍可能访问 pkg_resources
hiddenimports += ["pkg_resources"]

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[ROOT, SRC],
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

# ---------- onedir（默认）：解释器/依赖直接放在 dist/paw，启动时不再自解压到临时目录 ----------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="paw",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=True,
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
    upx=False,
    upx_exclude=[],
    name="paw",
)
