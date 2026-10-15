// Capture only an explicitly selected local FlyMSG diagnostic page over CDP.
// node scripts/render_reference.mjs http://127.0.0.1:40621 TARGET_ID new-directory [time-ms]
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";

const [endpoint, targetId, out, timestamp = "0"] = process.argv.slice(2);
if (!endpoint || !targetId || !out || !Number.isFinite(Number(timestamp)))
  throw new Error("usage: render_reference.mjs CDP_ENDPOINT TARGET_ID NEW_DIRECTORY [time-ms]");
const url = new URL(endpoint);
if (!["127.0.0.1", "localhost"].includes(url.hostname)) throw new Error("CDP endpoint must be local");
const target = (await (await fetch(new URL("/json/list", url))).json()).find((t) => t.id === targetId);
if (!target || !target.url.startsWith("http://localhost:") || !new URL(target.url).searchParams.has("check"))
  throw new Error("Target must be an explicit local FlyMSG ?check page");
mkdirSync(out, { recursive: false });
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.addEventListener("open", resolve, { once: true }); ws.addEventListener("error", reject, { once: true }); });
try {
  const result = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Reference timed out; no complete artifact")), 120000);
    ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id !== 1) return;
      clearTimeout(timeout);
      if (message.error || message.result.exceptionDetails) reject(new Error(JSON.stringify(message)));
      else resolve(message.result.result.value);
    });
    ws.send(JSON.stringify({ id: 1, method: "Runtime.evaluate", params: {
      expression: `flymsg.reference({time:${Number(timestamp)}})`, awaitPromise: true, returnByValue: true,
    } }));
  });
  const images = result.images;
  delete result.images;
  result.images = {};
  for (const [name, image] of Object.entries(images)) {
    const bytes = Buffer.from(image.base64, "base64");
    if (createHash("sha256").update(bytes).digest("hex") !== image.sha256)
      throw new Error(`Readback hash mismatch: ${name}`);
    if (bytes.length !== result.width * result.height * 4) throw new Error("Invalid image size");
    const file = `${name}.rgba`;
    writeFileSync(join(out, file), bytes, { flag: "wx" });
    result.images[name] = { file, sha256: image.sha256 };
  }
  result.target_url = target.url;
  result.captured_at = new Date().toISOString();
  // Written last: incomplete captures never have a final reference.json.
  writeFileSync(join(out, "reference.json"), JSON.stringify(result, null, 2) + "\n", { flag: "wx" });
  console.log(`Reference complete: ${out}`);
} finally { ws.close(); }
