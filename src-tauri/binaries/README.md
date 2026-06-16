# Sidecar binary for Tauri `externalBin`

This directory holds the PyInstaller-built Python backend, named per target triple:

```
nightdiary-backend-x86_64-pc-windows-msvc.exe
```

Generate before `npm run tauri build`:

```bash
pyinstaller server/build.spec
npm run prepare-sidecar
```

Or: `make build-sidecar`
