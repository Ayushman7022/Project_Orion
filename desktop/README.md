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

`tauri:dev` runs `npm run serve-frontend`, which runs **`serve-frontend.cjs`**: it always resolves the real **`../frontend`** path from the `desktop/` folder (so it still works if Tauri’s working directory is `src-tauri/`, where a plain `../frontend` would wrongly point at `desktop/frontend`).

`index.html` forces a fresh `styles.css` URL each load (`?t=timestamp`) and sets no-cache meta tags so WebView2 doesn’t keep an old stylesheet.

If the UI still looks wrong, fully quit the desktop app, kill anything on port **1420**, then run `npm run tauri:dev` again.

### Desktop looks like “one vertical column” but browser is fine

1. Confirm the console prints **`serving files from:`** and that path is your real **`…/Sid/frontend`** (not `…/desktop/frontend`). The dev server is **Node** (`serve-frontend.cjs`) and sends **`Content-Type: text/css`** + **`Cache-Control: no-store`** so WebView2 applies `styles.css`.
2. Your window title/branding should match this repo (**ORION**). If you see **NOVA** or different labels, the desktop is loading **another copy** of the project—open that project’s `desktop/` and run `tauri:dev` there, or align `frontend/` with the same files you use in the browser.
3. Press **F12** in the desktop window (devtools is enabled) → **Network** → reload: `styles.css` must be **200** and type **stylesheet**.

## Notes
- The frontend still talks to `http://localhost:8000` (same as before).
- If port `8000` is in use, stop the other backend first.

