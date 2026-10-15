// Fixed-time desktop observer trial, no second renderer or simulation clock.
// node scripts/observer_trial.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY [seconds=15]
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const [endpoint, targetId, out, seconds = "15"] = process.argv.slice(2);
const duration = Number(seconds);
if (
  !endpoint ||
  !targetId ||
  !out ||
  !Number.isFinite(duration) ||
  duration < 5 ||
  duration > 120
)
  throw Error(
    "usage: observer_trial.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY [seconds=15;5..120]",
  );
const host = new URL(endpoint);
if (!["localhost", "127.0.0.1"].includes(host.hostname))
  throw Error("Local CDP endpoint required");
const target = (await (await fetch(new URL("/json/list", host))).json()).find(
  (t) => t.id === targetId,
);
if (
  !target?.url.startsWith("http://localhost:") ||
  !new URL(target.url).searchParams.has("check")
)
  throw Error("Explicit local ?check page required");
mkdirSync(out, { recursive: false });
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
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const request = ++id,
      timeout = setTimeout(
        () => {
          pending.delete(request);
          reject(Error(`CDP timeout: ${method}`));
        },
        (duration + 30) * 1000,
      );
    pending.set(request, (m) => {
      clearTimeout(timeout);
      pending.delete(request);
      if (m.error || m.result?.exceptionDetails)
        reject(Error(JSON.stringify(m)));
      else resolve(m.result);
    });
    ws.send(JSON.stringify({ id: request, method, params }));
  });
const evaluate = async (expression) =>
  (
    await send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
  ).result.value;
let restore;
try {
  await send("Page.bringToFront");
  const before = await evaluate(`(() => {
    if(document.hidden||flymsg.renderer.xr.isPresenting)throw Error('Visible desktop page required');
    if(typeof flymsg.diagnosticState!=='function')throw Error('Trial requires diagnostic state restoration support');
    const stats=document.getElementById('stats').textContent;
    if(!/(?:^| · )0 loading(?: · |$)/.test(stats))throw Error('Geometry is still loading');
    return {fidelity:flymsg.fidelity(),resources:flymsg.resources(),camera:flymsg.camera.matrixWorld.toArray(),stats};
  })()`);
  restore = await evaluate("flymsg.diagnosticState()");
  await evaluate(
    `flymsg.diagnostic(${JSON.stringify({ suspended: false, continuous: true, time: 20, ...(process.env.PAGES === undefined ? {} : { pageCulling: process.env.PAGES === "1" }) })})`,
  );
  await new Promise((r) => setTimeout(r, 3000));
  const sample = await evaluate(`new Promise(resolve=>{
    const intervals=[],visibility=[],tasks=[];let last=null,frame;const started=performance.now();
    const note=()=>visibility.push({at_ms:performance.now()-started,state:document.visibilityState});
    note();document.addEventListener('visibilitychange',note);
    let observer;try{observer=new PerformanceObserver(l=>tasks.push(...l.getEntries().map(e=>({start_ms:e.startTime-started,duration_ms:e.duration}))));observer.observe({type:'longtask',buffered:false})}catch{}
    const tick=t=>{if(last!==null)intervals.push(t-last);last=t;frame=requestAnimationFrame(tick)};frame=requestAnimationFrame(tick);
    setTimeout(()=>{cancelAnimationFrame(frame);observer?.disconnect();note();document.removeEventListener('visibilitychange',note);
      resolve({raw_intervals_ms:intervals,wall_ms:performance.now()-started,visibility,long_tasks:tasks,
        fidelity:flymsg.fidelity(),draws:{...flymsg.renderer.info.render},resources:flymsg.resources(),camera:flymsg.camera.matrixWorld.toArray()})},${duration * 1000});
  })`);
  const provenance =
    await evaluate(`Promise.all(['main.js','geometry-pages.js','page-views.js','fidelity.js','paged-scene.js','gpu-upload.js','primitive-pages.js','source-slots.js'].map(async file=>{
    const b=await(await fetch(file)).arrayBuffer();const h=await crypto.subtle.digest('SHA-256',b);return [file,[...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,'0')).join('')];
  })).then(Object.fromEntries)`);
  const values = [...sample.raw_intervals_ms].sort((a, b) => a - b);
  const percentile = (p) =>
    values.length ? values[Math.ceil(values.length * p) - 1] : null;
  const visible =
    sample.visibility.every((e) => e.state === "visible") &&
    values.length >= 20;
  const cameraUnchanged =
    JSON.stringify(before.camera) === JSON.stringify(sample.camera);
  const record = {
    schema: "flymsg.observer-trial/v1",
    url: target.url,
    recorded_at: new Date().toISOString(),
    time_ms: 20,
    seconds: duration,
    before,
    ...sample,
    source_sha256: provenance,
    intervals_ms: {
      p50: percentile(0.5),
      p95: percentile(0.95),
      p99: percentile(0.99),
    },
    eligibility: {
      visible,
      camera_unchanged: cameraUnchanged,
      full_anatomy:
        sample.fidelity.status === "ready" &&
        before.fidelity.status === "ready" &&
        sample.fidelity.gpu_ready !== false && before.fidelity.gpu_ready !== false,
    },
    qualification: "not-scored; desktop diagnostic, not immersive XR",
  };
  writeFileSync(
    join(out, "trial.json"),
    JSON.stringify(record, null, 2) + "\n",
    { flag: "wx" },
  );
  console.log(
    JSON.stringify({
      out,
      intervals_ms: record.intervals_ms,
      eligibility: record.eligibility,
      lines: sample.draws.lines,
    }),
  );
} finally {
  if (restore)
    await evaluate(`flymsg.diagnostic(${JSON.stringify(restore)})`).catch(
      (error) => console.error("RESTORE FAILED", error),
    );
  ws.close();
}
