# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Night Diary Python sidecar.

Build (from repo root)::

    pyinstaller server/build.spec

Output::

    dist/nightdiary-backend.exe   # Windows (repo root)
    dist/nightdiary-backend       # Linux / macOS

When Phase B AI dependencies are installed, ``collect_all`` hooks bundle their
data files and native libraries (onnxruntime DLLs, tokenizers, etc.).
"""

from __future__ import annotations

import os

block_cipher = None

# task.md phase-a-5: mandated hidden imports for the Phase B AI stack.
HIDDEN_IMPORTS: list[str] = [
    "chromadb",
    "onnxruntime",
    "sentence_transformers",
    "jieba",
    "torch",
    "tokenizers",
    # FastAPI / uvicorn runtime (one-file bundle)
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "sqlalchemy.dialects.sqlite",
    "aiosqlite",
    "pydantic_settings",
]

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str, str]] = []
hiddenimports = list(HIDDEN_IMPORTS)

# Packages whose native binaries / data should be collected when installed.
_COLLECT_PACKAGES = (
    "uvicorn",
    "fastapi",
    "starlette",
    "sqlalchemy",
    "chromadb",
    "onnxruntime",
    "sentence_transformers",
    "tokenizers",
    "torch",
    "jieba",
)


def _collect_package(name: str) -> None:
    try:
        from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs
    except ImportError:
        return

    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(name)
        datas.extend(pkg_datas)
        binaries.extend(pkg_binaries)
        hiddenimports.extend(pkg_hidden)
    except Exception:
        pass

    try:
        binaries.extend(collect_dynamic_libs(name))
    except Exception:
        pass


for _package in _COLLECT_PACKAGES:
    _collect_package(_package)

a = Analysis(
    [os.path.join(SPECPATH, "app", "main.py")],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_forwarders=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="nightdiary-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
