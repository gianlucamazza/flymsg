import assert from "node:assert/strict";
import { test } from "node:test";
import { XrMetrics, xrTiming } from "../../src/flymsg/viz_static/xr-metrics.js";

function session(rate = 72) {
  const s = new EventTarget();
  s.frameRate = rate;
  s.visibilityState = "visible";
  return s;
}

test("resource inventory runs only when sampled, never on every headset frame", () => {
  const m = new XrMetrics({}, () => {});
  m.start(session(), 0);
  let calls = 0;
  const inventory = () => ({ bytes: ++calls });
  for (let i = 0; i <= 10000; i += 10) m.frame(i, 1, [], inventory);
  assert.equal(calls, 2);
  assert.deepEqual(
    m.report().resources.map((r) => r.bytes),
    [1, 2],
  );
});

test("XR budgets use actual refresh and retain long stalls beyond the desktop idle filter", () => {
  const smooth = Array(1000).fill(1000 / 72);
  assert.equal(xrTiming(smooth, 72).verdict, "pass");
  const stalled = [...smooth, 2000];
  assert.equal(xrTiming(stalled, 72).verdict, "fail");
  assert.ok(xrTiming(stalled, 72).estimated_missed_slots >= 143);
  assert.equal(xrTiming(smooth, null).verdict, "indeterminate");
  assert.equal(xrTiming([], 72).verdict, "indeterminate");
});

test("session-wide percentiles keep early bad frames after 600 subsequent frames", () => {
  const emitted = [];
  const m = new XrMetrics({}, (r) => emitted.push(r));
  m.start(session(), 0);
  m.frame(0, 1, []);
  m.frame(2000, 1, [3]);
  for (let i = 1; i <= 700; i++) m.frame(2000 + (i * 1000) / 72, 2, []);
  const r = m.finish("session-end", 12000);
  assert.equal(r.raw_intervals_ms.length, 701);
  assert.equal(r.raw_intervals_ms[0], 2000);
  assert.equal(r.timing.verdict, "fail");
  assert.equal(r.gpu_ms.p50, 3);
  assert.equal(emitted.at(-1).status, "ended");
});

test("hidden segments are explicit and refresh changes invalidate a single-budget score", () => {
  const m = new XrMetrics({}, () => {});
  const s = session();
  m.start(s, 0);
  m.frame(10, 1, []);
  s.visibilityState = "hidden";
  s.dispatchEvent(new Event("visibilitychange"));
  m.frame(10000, 1, []);
  s.visibilityState = "visible";
  s.dispatchEvent(new Event("visibilitychange"));
  m.frame(20000, 1, []);
  m.frame(20014, 1, []);
  assert.deepEqual(m.report().raw_intervals_ms, [14]);
  s.frameRate = 90;
  s.dispatchEvent(new Event("frameratechange"));
  assert.equal(m.report().timing.verdict, "indeterminate");
  assert.equal(
    m.report().events.filter((e) => e.kind.startsWith("visibility:")).length,
    2,
  );
  m.finish("end");
  m.start(session(), 0);
  assert.equal(m.report().frames, 0);
});

test("fast timing cannot hide incomplete GPU resources between inventory samples", () => {
  const metrics = new XrMetrics({}, () => {});
  metrics.start(session(), 0);
  const ready = { status: "ready", gpu_ready: true };
  metrics.frame(0, 1, [], null, ready);
  metrics.frame(1000 / 72, 1, [], null, { status: "ready", gpu_ready: false });
  metrics.frame(2000 / 72, 1, [], null, ready);
  assert.equal(metrics.report().timing.verdict, "pass");
  assert.equal(metrics.report().content.verdict, "fail");
  assert.equal(metrics.report().content.incomplete_frames, 1);
  metrics.start(session(), 0);
  metrics.frame(0, 1, [], null, { status: "ready", gpu_ready: null });
  assert.equal(metrics.report().content.verdict, "indeterminate");
});

test("initial runtime refresh selection before the first frame is a known budget", () => {
  const m = new XrMetrics({}, () => {});
  const s = session();
  m.start(s, 0);
  s.frameRate = 90;
  s.dispatchEvent(new Event("frameratechange"));
  m.frame(0, 1, []);
  m.frame(1000 / 90, 1, []);
  assert.equal(m.report().timing.refresh_hz, 90);
  assert.equal(m.report().timing.verdict, "pass");
});

test("every XR frame keeps the bounded certificate and catches violations between resource samples", () => {
  const emitted = [],
    m = new XrMetrics({}, (r) => emitted.push(r)),
    ready = {
      representation: "skeleton-bounded",
      selected: 1128,
      represented: 1128,
      status: "ready",
      gpu_ready: true,
      bounded: {
        maximum_error_px: 0.4,
        submitted_indices: 20,
        source_indices: 100,
        fallback_pages: 0,
        coarse_pages: 1,
        error: null,
      },
    };
  for (const damage of [
    null,
    { ...ready.bounded, maximum_error_px: 0.51 },
    { ...ready.bounded, submitted_indices: 101 },
    { ...ready.bounded, error: "upload failure" },
  ]) {
    m.start(session(), 0);
    m.frame(0, 1, [], () => ({}), ready);
    m.frame(1000 / 72, 1, [], null, { ...ready, bounded: damage });
    m.frame(2000 / 72, 1, [], null, ready);
    const r = m.finish("end", 100);
    assert.equal(r.timing.verdict, "pass");
    assert.equal(r.bounded.verdict, "fail");
    assert.equal(r.content.incomplete_frames, 1);
    assert.equal(r.raw_bounded_frames.length, 3);
    assert.equal(r.raw_bounded_frames[1][5], 1);
  }
  m.start(session(), 0);
  m.frame(0, 1, [], () => ({}), ready);
  assert.equal(emitted.at(-1).raw_bounded_frames, undefined);
  m.frame(1000 / 72, 1, [], null, {
    ...ready,
    bounded: {
      ...ready.bounded,
      maximum_error_px: 0,
      submitted_indices: 100,
      fallback_pages: 1,
      coarse_pages: 0,
    },
  });
  const r = m.finish("end", 100);
  assert.equal(r.bounded.verdict, "pass");
  assert.equal(r.raw_bounded_frames[1][3], 1);
});
test("ready content cannot conceal an anatomical selection change during XR", () => {
  const m = new XrMetrics({}, () => {});
  m.start(session(), 0);
  m.frame(0, 1, [], null, {
    status: "ready",
    gpu_ready: true,
    representation: "skeleton",
    source_geometry: true,
    selected: 1128,
    represented: 1128,
  });
  m.frame(14, 1, [], null, {
    status: "ready",
    gpu_ready: true,
    representation: "skeleton",
    source_geometry: true,
    selected: 2,
    represented: 2,
  });
  assert.equal(m.report().content.verdict, "fail");
});

test("exact XR content refuses missing or transiently false source geometry", () => {
  for (const source_geometry of [false, undefined]) {
    const m = new XrMetrics({}, () => {});
    m.start(session(), 0);
    const ready = {
      status: "ready",
      gpu_ready: true,
      representation: "surface",
      source_geometry: true,
      selected: 1128,
      represented: 1128,
    };
    m.frame(0, 1, [], null, ready);
    m.frame(14, 1, [], null, { ...ready, source_geometry });
    m.frame(28, 1, [], null, ready);
    assert.equal(m.report().content.verdict, "fail");
  }
});
