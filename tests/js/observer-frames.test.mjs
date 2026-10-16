import assert from "node:assert/strict";
import { test } from "node:test";
import { ObserverFrames } from "../../src/flymsg/viz_static/observer-frames.js";

test("external callbacks cannot advance application telemetry", () => {
  const f = new ObserverFrames("document-a");
  let external = 0;
  for (let i = 0; i < 100; i++) external++;
  assert.equal(external, 100);
  assert.equal(f.status().loop_callbacks, 0);
  f.loop();
  assert.equal(f.status().loop_callbacks, 1);
  assert.equal(f.status().submitted_frames, 0);
});
test("a complete arm retains more than 600 samples and long stalls", () => {
  const f = new ObserverFrames("document-a"),
    id = { generation: 1 };
  f.start(30, id, 0);
  for (let i = 0; i <= 1000; i++) f.frame(i * 30, id, { cpu_ms: 2 });
  f.frame(31500, id, { cpu_ms: 1500 });
  const r = f.finish(31501);
  assert(r.eligible);
  assert.equal(r.raw_intervals_ms.length, 1001);
  assert.equal(r.raw_intervals_ms.at(-1), 1500);
});
test("context, source-generation, hidden and terminal stalls cannot pass", () => {
  const f = new ObserverFrames("document-a");
  f.start(30, { generation: 1 }, 0);
  for (let i = 0; i < 30; i++)
    f.frame(i * 100, { generation: i === 29 ? 2 : 1 });
  f.invalidate("hidden-page");
  f.contextLost();
  const r = f.finish(30000);
  assert.equal(r.eligible, false);
  for (const reason of [
    "render-identity-changed",
    "hidden-page",
    "context-lost",
    "incomplete-terminal-cadence",
  ])
    assert(r.reasons.includes(reason));
});
test("empty and shortened windows fail, parallel capture refuses", () => {
  const f = new ObserverFrames("a");
  f.start(30, {}, 0);
  assert.throws(() => f.start(5, {}, 0), /already active/);
  const r = f.finish(100);
  assert(!r.eligible);
  assert(r.reasons.includes("incomplete-window"));
  assert(r.reasons.includes("insufficient-application-frames"));
});
