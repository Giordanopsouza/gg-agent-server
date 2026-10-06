import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer as createHttpServer, request as httpRequest, type IncomingMessage } from "node:http";
import { request as httpsRequest } from "node:https";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import type { Socket } from "node:net";

const defaultDist = fileURLToPath(new URL("../dist/", import.meta.url));
const apiPrefixes = ["/auth", "/tasks", "/webhooks", "/ready", "/health"];
const mimeTypes: Record<string, string> = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

function apiPath(pathname: string): boolean {
  return apiPrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function requestTarget(req: IncomingMessage): URL | null {
  const raw = req.url || "/";
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return null;
  try {
    return new URL(raw, "http://localhost");
  } catch {
    return null;
  }
}

function backendRequest(req: IncomingMessage, backend: URL, path: URL) {
  const target = new URL(backend);
  target.pathname = path.pathname;
  target.search = path.search;
  return (backend.protocol === "https:" ? httpsRequest : httpRequest)(target, {
    method: req.method,
    headers: req.headers,
  });
}

export function createWebServer(backend: URL, dist = defaultDist) {
  if (backend.protocol !== "http:" && backend.protocol !== "https:") {
    throw new Error("GG_BACKEND_URL must use HTTP or HTTPS");
  }
  const distRoot = resolve(dist);
  const server = createHttpServer(async (req, res) => {
    const target = requestTarget(req);
    if (!target) {
      res.writeHead(400).end();
      return;
    }
    const pathname = target.pathname;
    if (pathname === "/web_health") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ status: "ok" }));
      return;
    }
    if (apiPath(pathname)) {
      const upstream = backendRequest(req, backend, target);
      upstream.on("response", (response) => {
        res.writeHead(response.statusCode || 502, response.headers);
        response.pipe(res);
      });
      upstream.on("error", () => {
        if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
        res.end("Backend unavailable");
      });
      req.pipe(upstream);
      return;
    }
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405).end();
      return;
    }
    let decoded: string;
    try {
      decoded = decodeURIComponent(pathname);
    } catch {
      res.writeHead(400).end();
      return;
    }
    const file = resolve(distRoot, `.${decoded === "/" ? "/index.html" : decoded}`);
    if (file !== distRoot && !file.startsWith(`${distRoot}${sep}`)) {
      res.writeHead(404).end();
      return;
    }
    try {
      const info = await stat(file);
      if (!info.isFile()) throw new Error("not a file");
      res.writeHead(200, {
        "content-type": mimeTypes[extname(file)] || "application/octet-stream",
        "content-length": info.size,
        "cache-control": file.endsWith("index.html") ? "no-cache" : "public, max-age=31536000, immutable",
      });
      if (req.method === "HEAD") res.end();
      else createReadStream(file).pipe(res);
    } catch {
      res.writeHead(404).end();
    }
  });

  server.on("upgrade", (req, socket: Socket, head) => {
    const target = requestTarget(req);
    if (!target) {
      socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
      return;
    }
    const pathname = target.pathname;
    if (!pathname.startsWith("/tasks/sockets/events/")) {
      socket.end("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
      return;
    }
    const upstream = backendRequest(req, backend, target);
    upstream.on("upgrade", (response, backendSocket, backendHead) => {
      const lines = [`HTTP/${response.httpVersion} ${response.statusCode} ${response.statusMessage}`];
      for (let i = 0; i < response.rawHeaders.length; i += 2) {
        lines.push(`${response.rawHeaders[i]}: ${response.rawHeaders[i + 1]}`);
      }
      socket.write(`${lines.join("\r\n")}\r\n\r\n`);
      if (backendHead.length) socket.write(backendHead);
      if (head.length) backendSocket.write(head);
      socket.pipe(backendSocket).pipe(socket);
      socket.on("error", () => backendSocket.destroy());
      backendSocket.on("error", () => socket.destroy());
      socket.on("close", () => backendSocket.destroy());
      backendSocket.on("close", () => socket.destroy());
    });
    upstream.on("response", (response) => {
      socket.end(`HTTP/1.1 ${response.statusCode || 502} ${response.statusMessage || "Bad Gateway"}\r\nConnection: close\r\n\r\n`);
    });
    upstream.on("error", () => socket.end("HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n"));
    upstream.end();
  });
  return server;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!process.env.GG_BACKEND_URL) throw new Error("GG_BACKEND_URL is required");
  const backend = new URL(process.env.GG_BACKEND_URL);
  const port = Number(process.env.PORT || 3000);
  createWebServer(backend).listen(port, "0.0.0.0", () => {
    process.stdout.write(`gg-web listening on ${port}\n`);
  });
}
