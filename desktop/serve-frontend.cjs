/**
 * Dev static server for Tauri WebView2.
 *
 * Why not `python -m http.server`?
 * - CWD issues (see previous comments in git history).
 * - WebView2 can be picky: we send explicit MIME types + no-cache for .css/.js.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
const { URL } = require("url");

const ROOT = path.resolve(__dirname, "..", "frontend");
const ROOT_WITH_SEP = path.resolve(ROOT) + path.sep;
const PORT = 1420;
const HOST = "127.0.0.1";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json",
  ".webm": "video/webm",
  ".mp3": "audio/mpeg",
  ".txt": "text/plain; charset=utf-8",
};

function isInsideRoot(filePath) {
  const resolved = path.resolve(filePath);
  return resolved === path.resolve(ROOT) || resolved.startsWith(ROOT_WITH_SEP);
}

function filePathForUrl(pathname) {
  const clean = pathname === "/" || pathname === "" ? "/index.html" : pathname;
  const relative = clean.replace(/^\/+/, "").replace(/\//g, path.sep);
  const candidate = path.resolve(ROOT, relative);
  if (!isInsideRoot(candidate)) return null;
  return candidate;
}

const server = http.createServer((req, res) => {
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405);
    return res.end();
  }

  let u;
  try {
    u = new URL(req.url || "/", `http://${HOST}:${PORT}`);
  } catch {
    res.writeHead(400);
    return res.end("Bad request");
  }

  const filePath = filePathForUrl(u.pathname);
  if (!filePath) {
    res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
    return res.end("Forbidden");
  }

  fs.stat(filePath, (err, st) => {
    if (err || !st.isFile()) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      return res.end("Not found");
    }

    const ext = path.extname(filePath).toLowerCase();
    const type = MIME[ext] || "application/octet-stream";

    res.writeHead(200, {
      "Content-Type": type,
      "Cache-Control": "no-store, no-cache, must-revalidate",
      Pragma: "no-cache",
      Expires: "0",
    });

    if (req.method === "HEAD") return res.end();

    fs.createReadStream(filePath).on("error", () => {
      if (!res.headersSent) res.writeHead(500);
      res.end();
    }).pipe(res);
  });
});

server.listen(PORT, HOST, () => {
  console.error("[orion-desktop] static server:", `http://${HOST}:${PORT}/`);
  console.error("[orion-desktop] serving files from:", ROOT);
});

server.on("error", (e) => {
  console.error("[orion-desktop] server error:", e.message);
  process.exit(1);
});
