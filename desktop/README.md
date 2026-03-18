# Orion Desktop (Windows)

This wraps your existing `frontend/` UI into a Windows desktop window and auto-starts the `backend/` FastAPI server.

## What this gives you
- Same UI design as the web page (loads `../frontend/index.html`)
- Backend started automatically (Uvicorn on `127.0.0.1:8000`)
- Easy place to debug which features work in desktop vs browser

## Prereqs (Windows)
- Rust toolchain (stable) + MSVC build tools
- Node.js (for Tauri tooling)
- Python (already used by your backend)

## Run (dev)
From `desktop/`:

```bash
npm install
npm run tauri:dev
```

The app will open a window and start the backend automatically.

## Notes
- The frontend still talks to `http://localhost:8000` (same as before).
- If port `8000` is in use, stop the other backend first.

