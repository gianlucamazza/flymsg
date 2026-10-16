// Explicit Quest observer diagnostic with target-scoped CPU profiling and native GPU counters.
// node scripts/observer_browser.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY QUEST_SERIAL
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { localObserver } from "./observer_cdp.mjs";
import { browserProbe } from "../src/flymsg/viz_static/browser-probe.js";
const [endpoint, target, out, serial, pipeline = "direct"] =
  process.argv.slice(2);
if (!endpoint || !target || !out || !serial || !/^[A-Za-z0-9]+$/.test(serial))
  throw Error(
    "usage: observer_browser.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY QUEST_SERIAL",
  );
const browser = await localObserver(endpoint, target);
let processGPU,
  profiling = false;
const write = (name, data) =>
  writeFileSync(
    join(out, name),
    typeof data === "string" ? data : JSON.stringify(data, null, 2) + "\n",
    { flag: "wx" },
  );
try {
  mkdirSync(out, { recursive: false });
  const source = readFileSync(
    new URL("../src/flymsg/viz_static/browser-probe.js", import.meta.url),
  );
  const sha256 = createHash("sha256").update(source).digest("hex");
  write("protocol.json", {
    seconds: 8,
    size: 512,
    pipeline,
    sha256,
    rule: "No FPS verdict. Retain native metrics verbatim; no driver profiling mode, clock or browser flag changes. Require complete anatomy and reference restoration.",
  });
  write("browser-probe.js", source.toString());
  const device = spawnSync(
    "adb",
    ["-s", serial, "shell", "getprop", "ro.product.model"],
    { encoding: "utf8", timeout: 10000 },
  );
  if (device.status || device.stdout.trim() !== "Quest 2")
    throw Error("Explicit serial must identify Quest 2");
  write("device.json", {
    model: device.stdout.trim(),
    adb_server_port: process.env.ANDROID_ADB_SERVER_PORT ?? "5037",
  });
  const served =
    await browser.evaluate(`(async()=>Object.fromEntries(await Promise.all(['main.js','resident-lines.js','geometry-pages.js','page-views.js','paged-scene.js','gpu-upload.js','primitive-pages.js','source-slots.js','context-readiness.js'].map(async name=>{
    const response=await fetch(new URL(name,location.href));if(!response.ok)throw Error(name);
    const hash=await crypto.subtle.digest('SHA-256',await response.arrayBuffer());
    return [name,[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('')];
  }))))()`);
  const loaded = await browser.loadedSources(Object.keys(served));
  const loadedHashes = Object.fromEntries(
    Object.entries(loaded).map(([name, text]) => [
      name,
      createHash("sha256").update(text).digest("hex"),
    ]),
  );
  if (JSON.stringify(loadedHashes) !== JSON.stringify(served))
    throw Error("Loaded and served module hashes differ");
  write("served-sources.json", { served, loaded: loadedHashes });
  const before = await browser.evaluate("flymsg.diagnosticState()");
  const native = [];
  processGPU = spawn(
    "adb",
    [
      "-s",
      serial,
      "shell",
      "timeout",
      "14",
      "ovrgpuprofiler",
      "--realtime=2,3,4,7,8,11,17,25,26,32,33,65",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  processGPU.stdout.on("data", (data) =>
    native.push({
      at: new Date().toISOString(),
      stream: "stdout",
      text: data.toString(),
    }),
  );
  processGPU.stderr.on("data", (data) =>
    native.push({
      at: new Date().toISOString(),
      stream: "stderr",
      text: data.toString(),
    }),
  );
  const nativeExit = new Promise((resolve, reject) => {
    processGPU.on("error", reject);
    processGPU.on("close", (code, signal) => resolve({ code, signal }));
  });
  await browser.command("Profiler.enable");
  await browser.command("Profiler.setSamplingInterval", { interval: 1000 });
  await browser.command("Profiler.start");
  profiling = true;
  const result = await browser.evaluate(
    `(${browserProbe.toString()})(flymsg,${JSON.stringify({ pipeline })})`,
  );
  const profile = await browser.command("Profiler.stop");
  profiling = false;
  write("cpu.cpuprofile", profile.profile);
  write("probe.json", {
    ...result,
    recorded_at: new Date().toISOString(),
    url: browser.url,
  });
  const after = await browser.evaluate("flymsg.diagnosticState()");
  if (JSON.stringify(before) !== JSON.stringify(after))
    throw Error("Observer state restoration failed");
  write("native.json", { result: await nativeExit, chunks: native });
  if (
    !source.equals(
      readFileSync(
        new URL("../src/flymsg/viz_static/browser-probe.js", import.meta.url),
      ),
    )
  )
    throw Error("Probe source changed during diagnostic");
  write("complete.json", { status: "complete", state_restored: true, sha256 });
  console.log(`Browser diagnostic complete: ${out}`);
} finally {
  if (profiling) await browser.command("Profiler.stop").catch(() => {});
  await browser.command("Profiler.disable").catch(() => {});
  processGPU?.kill();
  browser.close();
}
