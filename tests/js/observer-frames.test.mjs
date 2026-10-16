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
test("context, source-generation, hidden and incomplete windows cannot pass", () => {
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
    "incomplete-window",
  ])
    assert(r.reasons.includes(reason));
});
test("completion requires a submitted frame beyond the deadline, including slow submissions", async () => {
  const f = new ObserverFrames("a");
  f.start(5, {}, 0);
  let completed = false;
  const completion = f.wait().then(() => {
    completed = true;
  });
  for (let i = 0; i < 100; i++) f.frame(i * 50, {});
  await Promise.resolve();
  assert.equal(completed, false);
  f.frame(6000, {}, { cpu_ms: 1200 });
  await completion;
  assert.equal(completed, true);
  const result = f.finish(7200);
  assert(result.eligible);
  assert.equal(result.raw_intervals_ms.at(-1), 1050);
  assert.equal(result.terminal_gap_ms, 1200);
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

test("every bounded submitted frame requires a finite certified error and counts", () => {
  const id = { representation: "skeleton-bounded" };
  for (const bad of [
    null,
    { maximum_error_px: 0.50001, submitted_indices: 2, source_indices: 4 },
    { maximum_error_px: NaN, submitted_indices: 2, source_indices: 4 },
    { maximum_error_px: 0, submitted_indices: 5, source_indices: 4 },
    {
      maximum_error_px: 0,
      submitted_indices: 2,
      source_indices: 4,
      error: "allocation",
    },
  ]) {
    const f = new ObserverFrames("a");
    f.start(5, id, 0);
    for (let i = 0; i <= 100; i++)
      f.frame(i * 50, id, {
        bounded:
          i === 50
            ? bad
            : { maximum_error_px: 0, submitted_indices: 4, source_indices: 4 },
      });
    assert(f.finish(5001).reasons.includes("uncertified-bounded-frame"));
  }
  const f = new ObserverFrames("b");
  f.start(5, id, 0);
  for (let i = 0; i <= 100; i++)
    f.frame(i * 50, id, {
      bounded: {
        maximum_error_px: i % 2 ? 0.4 : 0,
        submitted_indices: i % 2 ? 2 : 4,
        source_indices: 4,
      },
    });
  const report = f.finish(5001);
  assert(report.eligible);
  assert.equal(report.bounded_frames.length, 101);
});
