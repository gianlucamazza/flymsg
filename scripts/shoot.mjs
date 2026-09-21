#!/usr/bin/env node
// Headless check of the 3D view: open a URL in Chromium, wait in real time, save a screenshot and
// print the page's console output and exceptions. Uses the DevTools Protocol over node's
// built-in WebSocket, so it needs no npm packages.
//
//   [CLICK=x,y] node scripts/shoot.mjs <url> <out.png> [wait seconds=30] [width=1400] [height=900]
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, out, wait = "30", width = "1400", height = "900"] = process.argv.slice(2);
if (!url || !out) {
  console.error("usage: shoot.mjs <url> <out.png> [wait s] [width] [height]");
  process.exit(2);
}
const port = 9300 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "shoot-"));
const chrome = spawn(
  "chromium",
  [
    "--headless=new",
    "--enable-unsafe-swiftshader",
    "--use-angle=swiftshader",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    `--window-size=${width},${height}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let target;
for (let i = 0; i < 50 && !target; i++) {
  await sleep(200);
  try {
    target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page");
  } catch {
    // browser still starting
  }
}
if (!target) throw new Error("chromium did not expose a page target");

const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
  } else if (msg.method === "Runtime.consoleAPICalled") {
    const text = msg.params.args.map((a) => a.value ?? a.description ?? a.type).join(" ");
    console.log(`[console.${msg.params.type}] ${text}`);
  } else if (msg.method === "Runtime.exceptionThrown") {
    const d = msg.params.exceptionDetails;
    console.log(`[exception] ${d.exception?.description ?? d.text} (${d.url ?? ""}:${d.lineNumber})`);
  } else if (msg.method === "Log.entryAdded") {
    console.log(`[log.${msg.params.entry.level}] ${msg.params.entry.text} ${msg.params.entry.url ?? ""}`);
  }
});
const send = (method, params = {}) =>
  new Promise((resolve) => {
    pending.set(++id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
  });

await send("Runtime.enable");
await send("Log.enable");
await send("Page.enable");
// a DevTools-created page starts in the background, where requestAnimationFrame is paused
await send("Page.bringToFront");
await send("Emulation.setFocusEmulationEnabled", { enabled: true });
await send("Emulation.setDeviceMetricsOverride", {
  width: Number(width),
  height: Number(height),
  deviceScaleFactor: 1,
  mobile: false,
});
await send("Page.navigate", { url });
await sleep(Number(wait) * 1000);
// CLICK=x,y: click there before reading the HUD (checks picking)
if (process.env.CLICK) {
  const [x, y] = process.env.CLICK.split(",").map(Number);
  for (const type of ["mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 });
  }
  await sleep(1500);
}
// EVAL=<expression>: evaluate in the page (awaiting promises) and print the result
if (process.env.EVAL) {
  const r = await send("Runtime.evaluate", { expression: process.env.EVAL, awaitPromise: true, returnByValue: true });
  console.log(`[eval] ${JSON.stringify(r.result?.result?.value ?? r.result?.exceptionDetails?.exception?.description)}`);
}
const hud = await send("Runtime.evaluate", {
  expression: "[...document.querySelectorAll('#hud > div')].map(d => d.textContent).join(' | ')",
  returnByValue: true,
});
console.log(`[hud] ${hud.result?.result?.value ?? ""}`);
const shot = await send("Page.captureScreenshot", { format: "png" });
writeFileSync(out, Buffer.from(shot.result.data, "base64"));
console.log(`[saved] ${out}`);
ws.close();
chrome.kill();
await sleep(300);
rmSync(profile, { recursive: true, force: true });
