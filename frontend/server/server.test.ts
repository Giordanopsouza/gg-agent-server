import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createServer, type Server } from "node:http";
import { connect } from "node:net";
import type { Duplex } from "node:stream";
import { after, before, test } from "node:test";
import { createWebServer } from "./server.js";

let api: Server;
let web: Server;
let origin: string;
const upgraded = new Set<Duplex>();

async function listen(server: Server): Promise<number> {
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("missing port");
  return address.port;
}

before(async () => {
  api = createServer(async (req, res) => {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(chunk);
    if (req.url === "/auth/google/start") {
      res.writeHead(302, { location: "/auth/google/callback?code=abc", "set-cookie": "session=abc; HttpOnly; Path=/" }).end();
      return;
    }
    res.writeHead(200, { "content-type": "application/json", "set-cookie": "session=xyz; HttpOnly; Path=/" });
    res.end(JSON.stringify({ path: req.url, method: req.method, cookie: req.headers.cookie, header: req.headers["x-test"], body: Buffer.concat(chunks).toString("hex") }));
  });
  api.on("upgrade", (req, socket, head) => {
    upgraded.add(socket);
    socket.on("close", () => upgraded.delete(socket));
    assert.equal(req.url, "/tasks/sockets/events/one?after=2");
    assert.equal(req.headers.cookie, "session=abc");
    assert.equal(req.headers.origin, origin);
    const accept = createHash("sha1").update(`${req.headers["sec-websocket-key"]}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`).digest("base64");
    socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
    if (head.length) socket.write(head);
    socket.write(Buffer.from([0x81, 0x02, 0x6f, 0x6b]));
  });
  const port = await listen(api);
  web = createWebServer(new URL(`http://127.0.0.1:${port}`));
  origin = `http://127.0.0.1:${await listen(web)}`;
});

after(async () => {
  for (const socket of upgraded) socket.destroy();
  web.closeAllConnections();
  api.closeAllConnections();
  await Promise.all([new Promise<void>((resolve) => web.close(() => resolve())), new Promise<void>((resolve) => api.close(() => resolve()))]);
});

test("serves the built React page and asset", async () => {
  const page = await fetch(origin);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /gg · Tasks/);
  assert.equal(page.headers.get("cache-control"), "no-cache");
  const asset = (await fetch(origin).then((response) => response.text())).match(/src="(\/assets\/[^"]+)"/)?.[1];
  assert.ok(asset);
  const script = await fetch(`${origin}${asset}`);
  assert.equal(script.status, 200);
  assert.match(script.headers.get("content-type") || "", /javascript/);
  assert.equal((await fetch(`${origin}/missing`)).status, 404);
});

test("proxies API headers, cookies, redirects, and exact webhook bytes", async () => {
  const body = Buffer.from([0, 1, 255, 10, 13, 34]);
  const response = await fetch(`${origin}/webhooks/github?delivery=1`, {
    method: "POST", headers: { cookie: "session=abc", "x-test": "value", "content-type": "application/octet-stream" }, body,
  });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("set-cookie"), "session=xyz; HttpOnly; Path=/");
  assert.deepEqual(await response.json(), { path: "/webhooks/github?delivery=1", method: "POST", cookie: "session=abc", header: "value", body: body.toString("hex") });
  const redirect = await fetch(`${origin}/auth/google/start`, { redirect: "manual" });
  assert.equal(redirect.status, 302);
  assert.equal(redirect.headers.get("location"), "/auth/google/callback?code=abc");
  assert.equal(redirect.headers.get("set-cookie"), "session=abc; HttpOnly; Path=/");
  for (const route of ["/tasks", "/ready", "/health"]) {
    assert.equal((await fetch(`${origin}${route}`)).status, 200);
  }
  assert.deepEqual(await (await fetch(`${origin}/web_health`)).json(), { status: "ok" });
});

test("forwards the task WebSocket upgrade", async () => {
  const port = Number(new URL(origin).port);
  const reply = await new Promise<Buffer>((resolve, reject) => {
    const socket = connect(port, "127.0.0.1");
    const chunks: Buffer[] = [];
    socket.on("connect", () => socket.write(`GET /tasks/sockets/events/one?after=2 HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\nCookie: session=abc\r\nOrigin: ${origin}\r\n\r\n`));
    socket.on("data", (chunk: Buffer) => {
      chunks.push(chunk);
      const joined = Buffer.concat(chunks);
      if (joined.includes(Buffer.from([0x81, 0x02, 0x6f, 0x6b]))) { socket.destroy(); resolve(joined); }
    });
    socket.on("error", reject);
  });
  assert.match(reply.toString(), /101 Switching Protocols/);
  assert.ok(reply.includes(Buffer.from([0x81, 0x02, 0x6f, 0x6b])));
});

test("returns 502 when the backend is unavailable", async () => {
  const unavailable = createWebServer(new URL("http://127.0.0.1:1"));
  const port = await listen(unavailable);
  try {
    assert.equal((await fetch(`http://127.0.0.1:${port}/tasks`)).status, 502);
    assert.equal((await fetch(`http://127.0.0.1:${port}/web_health`)).status, 200);
  } finally {
    await new Promise<void>((resolve) => unavailable.close(() => resolve()));
  }
});


test("rejects invalid HTTP and WebSocket targets without forwarding or crashing", async () => {
  let forwarded = 0;
  const record = () => { forwarded++; };
  api.on("request", record);
  api.on("upgrade", record);
  const alternate = createServer((_req, res) => { forwarded++; res.end("alternate"); });
  const alternatePort = await listen(alternate);
  const port = Number(new URL(origin).port);
  try {
    for (const upgrade of [false, true]) {
      for (const target of [
        "//",
        "//[invalid/tasks",
        `//127.0.0.1:${alternatePort}/tasks/sockets/events/one`,
        `http://127.0.0.1:${alternatePort}/tasks/sockets/events/one`,
        `/\\127.0.0.1:${alternatePort}/tasks/sockets/events/one`,
      ]) {
        const reply = await new Promise<string>((resolve, reject) => {
          const socket = connect(port, "127.0.0.1");
          let response = "";
          socket.setTimeout(3000, () => socket.destroy(new Error("request timed out")));
          socket.on("connect", () => socket.write(`GET ${target} HTTP/1.1\r\nHost: localhost\r\nConnection: ${upgrade ? "Upgrade" : "close"}\r\n${upgrade ? "Upgrade: websocket\r\n" : ""}\r\n`));
          socket.on("data", (chunk) => { response += chunk.toString(); });
          socket.on("end", () => { socket.destroy(); resolve(response); });
          socket.on("error", reject);
        });
        assert.match(reply, /^HTTP\/1.1 400 /, `${upgrade ? "WebSocket" : "HTTP"}: ${target}`);
        assert.equal((await fetch(`${origin}/web_health`)).status, 200);
      }
    }
    assert.equal(forwarded, 0);
  } finally {
    api.off("request", record);
    api.off("upgrade", record);
    alternate.closeAllConnections();
    await new Promise<void>((resolve) => alternate.close(() => resolve()));
  }
});
