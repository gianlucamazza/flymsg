// Execute only the local diagnostic function against one explicitly chosen page.
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join } from "node:path";
import { serializedGpuProbe } from "../src/flymsg/viz_static/gpu-probe.js";
const [endpoint, targetId, out] = process.argv.slice(2);
if (!endpoint || !targetId || !out)
  throw Error(
    "usage: observer_gpu_probe.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY",
  );
if (!["localhost", "127.0.0.1"].includes(new URL(endpoint).hostname))
  throw Error("Local endpoint required");
const target = (
  await (await fetch(new URL("/json/list", endpoint))).json()
).find((t) => t.id === targetId);
if (
  !target?.url.startsWith("http://localhost:") ||
  !new URL(target.url).searchParams.has("check")
)
  throw Error("Explicit local ?check page required");
mkdirSync(out, { recursive: false });
const protocol = { sizes: [256, 512, 1024], warmup: 2, repeats: 5 };
const implementation = readFileSync(
  new URL("../src/flymsg/viz_static/gpu-probe.js", import.meta.url),
);
writeFileSync(
  join(out, "protocol.json"),
  JSON.stringify(
    {
      ...protocol,
      implementation_sha256: createHash("sha256")
        .update(implementation)
        .digest("hex"),
      rule: "Compare full vs discard at fixed geometry; compare discard vs minimal line vertex at fixed geometry; pixel scaling is diagnostic. No GPU-time/FPS or qualification claim.",
    },
    null,
    2,
  ) + "\n",
  { flag: "wx" },
);
writeFileSync(join(out, "implementation.js"), implementation, { flag: "wx" });
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve, { once: true });
  ws.addEventListener("error", reject, { once: true });
});
let id = 0;
const pending = new Map();
ws.addEventListener("message", (event) => {
  const m = JSON.parse(event.data);
  pending.get(m.id)?.(m);
});
const evaluate = (expression) =>
  new Promise((resolve, reject) => {
    const request = ++id,
      timer = setTimeout(() => {
        pending.delete(request);
        reject(Error("Probe timeout; no complete artifact"));
      }, 180000);
    pending.set(request, (m) => {
      clearTimeout(timer);
      pending.delete(request);
      if (m.error || m.result?.exceptionDetails)
        reject(Error(JSON.stringify(m)));
      else resolve(m.result.result.value);
    });
    ws.send(
      JSON.stringify({
        id: request,
        method: "Runtime.evaluate",
        params: { expression, awaitPromise: true, returnByValue: true },
      }),
    );
  });
let saved;
try {
  const before = await evaluate(`(() => {
    if(flymsg.renderer.xr.isPresenting || !/(?:^| · )0 loading(?: · |$)/.test(document.getElementById('stats').textContent))throw Error('Completed non-immersive scene required');
    return {state:flymsg.diagnosticState(),fidelity:flymsg.fidelity(),resources:flymsg.resources(),visibility:document.visibilityState};
  })()`);
  saved = before.state;
  await evaluate(
    "flymsg.diagnostic({suspended:true,continuous:false,time:0,pageCulling:false})",
  );
  // Explicitly prepare original indices/activity even when the runtime suspends rAF.
  const reference = await evaluate(
    "flymsg.reference({width:32,height:32,time:0,culling:false,pipeline:flymsg.paged?'paged':'original'})",
  );
  const result = await evaluate(
    `(${serializedGpuProbe.toString()})(flymsg,${JSON.stringify(protocol)})`,
  );
  writeFileSync(
    join(out, "probe.json"),
    JSON.stringify(
      {
        ...result,
        before,
        source_reference: reference,
        url: target.url,
        recorded_at: new Date().toISOString(),
      },
      null,
      2,
    ) + "\n",
    { flag: "wx" },
  );
  console.log(
    JSON.stringify(
      result.records.map((r) => ({
        size: r.size,
        mode: r.mode,
        wall_ms: r.serialized_wall_ms,
        draws: r.draws,
      })),
    ),
  );
} finally {
  if (saved)
    await evaluate(`flymsg.diagnostic(${JSON.stringify(saved)})`).catch(
      (error) => console.error("RESTORE FAILED", error),
    );
  ws.close();
}
