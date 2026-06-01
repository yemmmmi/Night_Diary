# Night Diary — Python Sidecar

FastAPI AI engine for the Tauri desktop shell. Binds to `127.0.0.1` only.

## Development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

python -m app.main --port 8000 --data-dir ./testdata
curl http://127.0.0.1:8000/health
```

From repo root: `make dev-api`

## PyInstaller packaging

### Build

Install dev dependencies (includes PyInstaller) in a **virtualenv** (avoid Anaconda base env — its obsolete `pathlib` backport breaks PyInstaller):

```bash
cd server
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
cd ..
pyinstaller server/build.spec
```

Output (from repo root):

| Platform | Path |
|----------|------|
| Windows | `dist/nightdiary-backend.exe` |
| Linux / macOS | `dist/nightdiary-backend` |

The Tauri release shell looks for `nightdiary-backend(.exe)` next to the desktop app binary (`src-tauri/src/process.rs`).

### Run the bundled sidecar

```bash
mkdir testdata
dist\nightdiary-backend.exe --port 8000 --data-dir .\testdata
curl http://127.0.0.1:8000/health
```

### Hidden imports & binary deps

`build.spec` lists Phase B AI packages (`chromadb`, `onnxruntime`, `sentence_transformers`, `jieba`, `torch`, `tokenizers`) as hidden imports. When those packages are installed in the build environment, PyInstaller hooks collect:

- **onnxruntime** — native `.dll` / `.so` libraries (ChromaDB embedding backend)
- **tokenizers / torch** — Rust/Python extension modules
- **chromadb / sentence_transformers** — package data files

### Model files (runtime, not bundled)

Sentence-transformer and reranker weights are **not** embedded in the `.exe`. They are stored under the runtime data directory:

```
{DATA_DIR}/models/
```

Use `--data-dir` (Tauri passes `%APPDATA%/night-diary` in production). Download or copy model files there before first RAG use (Phase B+).

### Common issues

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError` after build | Add the missing module to `hiddenimports` in `build.spec`, rebuild |
| onnxruntime DLL load failure | Ensure `onnxruntime` is installed before building; check `collect_dynamic_libs` output |
| Large bundle size (~1–2 GB with full AI stack) | Expected when `torch` + `chromadb` are installed; Phase A scaffold builds are much smaller |
| Port already in use | Pass a different `--port` or stop the dev server |
