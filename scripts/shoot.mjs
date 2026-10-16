#!/usr/bin/env node
// Headless check of the 3D view: open a URL in Chromium, wait in real time, save a screenshot and
// print the page's console output and exceptions. Uses the DevTools Protocol over node's
// built-in WebSocket, so it needs no npm packages.
//
//   [GL=swiftshader|gl|vulkan] [CLICK=x,y] [EVAL=js] node scripts/shoot.mjs <url> <out.png> [wait s=30] [w=1400] [h=900]
//
// GL picks the ANGLE backend: swiftshader (default, software, reproducible anywhere) or the
// hardware GPU through desktop GL or Vulkan, for frame-time measurements.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir, loadavg } from "node:os";
import { join } from "node:path";

const [url, out, wait = "30", width = "1400", height = "900"] =
  process.argv.slice(2);
if (!url || !out) {
  console.error("usage: shoot.mjs <url> <out.png> [wait s] [width] [height]");
  process.exit(2);
}
const evaluateTimeout = Number(process.env.EVAL_TIMEOUT_MS ?? 10000);
if (
  !Number.isInteger(evaluateTimeout) ||
  evaluateTimeout < 1000 ||
  evaluateTimeout > 600000
)
  throw new Error("EVAL_TIMEOUT_MS must be 1000..600000");
let port;
const profile = mkdtempSync(join(tmpdir(), "shoot-"));
const GL_FLAGS = {
  swiftshader: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"],
  gl: ["--ignore-gpu-blocklist", "--use-angle=gl"],
  vulkan: [
    "--ignore-gpu-blocklist",
    "--use-angle=vulkan",
    "--enable-features=Vulkan",
  ],
};
const gl = GL_FLAGS[process.env.GL ?? "swiftshader"];
if (!gl)
  throw new Error(`GL must be one of ${Object.keys(GL_FLAGS).join(", ")}`);
const chrome = spawn(
  "chromium",
  [
    "--headless=new",
    ...gl,
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    `--window-size=${width},${height}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let ws;
try {
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    await sleep(200);
    try {
      port = Number(
        readFileSync(join(profile, "DevToolsActivePort"), "utf8").split(
          "\n",
        )[0],
      );
      target = (
        await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()
      ).find((t) => t.type === "page");
    } catch {
      // browser still starting
    }
  }
  if (!target) throw new Error("chromium did not expose a page target");

  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  let id = 0;
  const pending = new Map();
  const disconnect = (reason) => {
    if (!pending.size) return;
    for (const callback of pending.values()) callback({ error: { message: reason } });
    pending.clear();
  };
  ws.addEventListener("close", (event) => disconnect(`CDP disconnected (${event.code}): ${event.reason}`));
  ws.addEventListener("error", () => disconnect("CDP connection failed"));
  let benchmark = null;
  let phase = "cold";
  const requestPhase = new Map();
  const networks = new Map();
  let network = { responses: 0, cachedResponses: 0, encodedBytes: 0 };
  const cached = new Set();
  function noteCached(requestId, stats) {
    if (!cached.has(requestId)) {
      cached.add(requestId);
      stats.cachedResponses++;
    }
  }
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    } else if (msg.method === "Runtime.consoleAPICalled") {
      const text = msg.params.args
        .map((a) => a.value ?? a.description ?? a.type)
        .join(" ");
      console.log(`[console.${msg.params.type}] ${text}`);
      if (text.startsWith("BENCH ")) {
        try {
          benchmark = JSON.parse(text.slice(6));
        } catch {
          benchmark = null;
          console.error("invalid BENCH JSON");
        }
      }
    } else if (msg.method === "Network.requestWillBeSent") {
      if (!requestPhase.has(msg.params.requestId))
        requestPhase.set(msg.params.requestId, phase);
    } else if (msg.method?.startsWith("Network.")) {
      const stats = networks.get(requestPhase.get(msg.params.requestId));
      if (stats) {
        if (msg.method === "Network.responseReceived") {
          stats.responses++;
          if (
            msg.params.response.fromDiskCache ||
            msg.params.response.fromPrefetchCache
          )
            noteCached(msg.params.requestId, stats);
        } else if (msg.method === "Network.requestServedFromCache")
          noteCached(msg.params.requestId, stats);
        else if (msg.method === "Network.loadingFinished")
          stats.encodedBytes += msg.params.encodedDataLength;
      }
    } else if (msg.method === "Runtime.exceptionThrown") {
      const d = msg.params.exceptionDetails;
      console.log(
        `[exception] ${d.exception?.description ?? d.text} (${d.url ?? ""}:${d.lineNumber})`,
      );
    } else if (msg.method === "Log.entryAdded") {
      console.log(
        `[log.${msg.params.entry.level}] ${msg.params.entry.text} ${msg.params.entry.url ?? ""}`,
      );
    }
  });
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const request = ++id;
      const timeout = setTimeout(
        () => {
          pending.delete(request);
          reject(new Error(`CDP timeout: ${method}`));
        },
        method === "Runtime.evaluate" ? evaluateTimeout : 10000,
      );
      pending.set(request, (message) => {
        clearTimeout(timeout);
        if (message.error)
          reject(new Error(`CDP ${method}: ${JSON.stringify(message.error)}`));
        else resolve(message);
      });
      ws.send(JSON.stringify({ id: request, method, params }));
    });

  await send("Runtime.enable");
  await send("Log.enable");
  await send("Page.enable");
  await send("Network.enable");
  // a DevTools-created page starts in the background, where requestAnimationFrame is paused
  await send("Page.bringToFront");
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await send("Emulation.setDeviceMetricsOverride", {
    width: Number(width),
    height: Number(height),
    deviceScaleFactor: 1,
    mobile: process.env.MOBILE === "1",
  });
  await send("Emulation.setTouchEmulationEnabled", {
    enabled: process.env.MOBILE === "1",
  });
  for (const cache of process.env.BENCH_WARM === "1"
    ? ["cold", "warm"]
    : ["cold"]) {
    phase = cache;
    benchmark = null;
    network = { responses: 0, cachedResponses: 0, encodedBytes: 0 };
    networks.set(cache, network);
    const loadBefore = loadavg();
    if (cache === "cold") await send("Page.navigate", { url });
    else await send("Page.reload", { ignoreCache: false });
    await sleep(Number(wait) * 1000);
    const gpuReply = await send("Runtime.evaluate", {
      expression: `(() => { const gl = document.querySelector('canvas')?.getContext('webgl2'); if (!gl) return null; const ext = gl.getExtension('WEBGL_debug_renderer_info'); return {renderer: gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER), vendor: gl.getParameter(ext ? ext.UNMASKED_VENDOR_WEBGL : gl.VENDOR), version: gl.getParameter(gl.VERSION)}; })()`,
      returnByValue: true,
    });
    const gpu = gpuReply.result?.result?.value ?? null;
    console.log(
      `CACHE_PASS ${JSON.stringify({ cache, load_before: loadBefore, load_after: loadavg(), bench: benchmark, network, gpu })}`,
    );
  }
  // CLICK=x,y: click there before reading the HUD (checks picking)
  if (process.env.CLICK) {
    const [x, y] = process.env.CLICK.split(",").map(Number);
    for (const type of ["mousePressed", "mouseReleased"]) {
      await send("Input.dispatchMouseEvent", {
        type,
        x,
        y,
        button: "left",
        clickCount: 1,
      });
    }
    await sleep(1500);
  }
  // EVAL=<expression>: evaluate in the page (awaiting promises) and print the result
  if (process.env.EVAL) {
    const r = await send("Runtime.evaluate", {
      expression: process.env.EVAL,
      awaitPromise: true,
      returnByValue: true,
    });
    console.log(
      `[eval] ${JSON.stringify(r.result?.result?.value ?? r.result?.exceptionDetails?.exception?.description)}`,
    );
  }
  const hud = await send("Runtime.evaluate", {
    expression:
      "[...document.querySelectorAll('#hud > div')].map(d => d.textContent).join(' | ')",
    returnByValue: true,
  });
  console.log(`[hud] ${hud.result?.result?.value ?? ""}`);
  const shot = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(out, Buffer.from(shot.result.data, "base64"));
  console.log(`[saved] ${out}`);
} finally {
  ws?.close();
  chrome.kill();
  await sleep(300);
  rmSync(profile, { recursive: true, force: true });
}
