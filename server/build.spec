# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Night Diary Python sidecar — ONEDIR mode.

Only collects packages that are actually imported by the server code.
The anaconda base env contains hundreds of unrelated scientific packages
that must NOT be bundled.

Build (from repo root)::

    python -m PyInstaller server/build.spec

Output::

    dist/nightdiary-backend/nightdiary-backend.exe   (+ _internal/)
"""

from __future__ import annotations

import os

block_cipher = None

# --- Hidden imports that PyInstaller's static analysis cannot discover ---
HIDDEN_IMPORTS: list[str] = [
    # Web framework
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
    # Database
    "sqlalchemy.dialects.sqlite",
    "aiosqlite",
    "pydantic_settings",
    # ChromaDB runtime
    "chromadb",
    # AI / embedding (lazy-loaded at runtime, but needed in bundle)
    "sentence_transformers",
    "onnxruntime",
    "huggingface_hub",
    "safetensors",
    "tokenizers",
    "transformers",
    # Chinese tokenisation
    "jieba",
    # LLM
    "langchain_text_splitters",
    "langchain_openai",
    "langchain_core",
    "openai",
    # HTTP stack
    "httpx",
    "httpcore",
    "anyio",
    "sniffio",
    "certifi",
    "charset_normalizer",
    "idna",
    "urllib3",
    "requests",
    "packaging",
    "filelock",
    "tqdm",
    "regex",
    "yaml",
    # Crypto
    "cryptography",
]

# --- Packages whose data / native libs we need at runtime ---
_COLLECT_DATA_PACKAGES = (
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
    "transformers",
    "huggingface_hub",
    "langchain_text_splitters",
    "langchain_openai",
    "cryptography",
)

# --- Exclude unrelated anaconda base packages ---
EXCLUDES: list[str] = [
    # Unused ML backends (we only use PyTorch)
    "tensorflow",
    "tensorflow_intel",
    "tensorboard",
    "tensorboard_data_server",
    "keras",
    "jax",
    "jaxlib",
    "flax",
    # Anaconda bloat — not imported by our code
    "botocore",
    "boto3",
    "s3transfer",
    "awscli",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "panel",
    "bokeh",
    "numba",
    "llvmlite",
    "jupyterlab",
    "notebook",
    "jupyter_server",
    "nbconvert",
    "nbformat",
    "ipykernel",
    "ipywidgets",
    "traitlets",
    "astropy",
    "skimage",
    "scikit_image",
    "sphinx",
    "matplotlib",
    "pandas",
    "pyarrow",
    "scipy",
    "sklearn",
    "nltk",
    "nltk_data",
    "IPython",
    "ipython",
    "conda",
    "conda_package_handling",
    "menuinst",
    "navigator",
    "anaconda_navigator",
    "distlib",
    "bleach",
    "defusedxml",
    "json5",
    "mistune",
    "nbclient",
    "prometheus_client",
    "terminado",
    "tornado",
    "winpty",
    "pytest",
    "mypy",
    "ruff",
    # tiktoken not used (project has its own token estimator)
    "tiktoken",
    # PyInstaller hook-torch auto-pulls these, but project doesn't use them
    "torchvision",
    "torchaudio",
    # Other auto-pulled packages not used by project
    "lxml",
    "PIL",
    "Pillow",
    "h5py",
    "distributed",
    "zstandard",
    "paramiko",
    "bcrypt",
    "nacl",
    "zmq",
    "win32com",
    "pythoncom",
    "pywintypes",
    "pywin32",
]

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str, str]] = []
hiddenimports = list(HIDDEN_IMPORTS)


def _collect_package_data(name: str) -> None:
    """Collect data files and dynamic libs for *name* only — no submodules."""
    try:
        from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
    except ImportError:
        return

    try:
        datas.extend(collect_data_files(name))
    except Exception:
        pass

    try:
        binaries.extend(collect_dynamic_libs(name))
    except Exception:
        pass


for _pkg in _COLLECT_DATA_PACKAGES:
    _collect_package_data(_pkg)

a = Analysis(
    [os.path.join(SPECPATH, "app", "main.py")],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_forwarders=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# === ONEDIR MODE: exclude binaries from EXE, use COLLECT ===
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nightdiary-backend",
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="nightdiary-backend",
)
