// Session-wide XR measurements. No desktop idle filter, rolling window or simulator input.
import { percentile } from "./perf.js";

const quantiles = (values) =>
  Object.fromEntries([50, 95, 99].map((p) => [`p${p}`, percentile(values, p)]));

export function xrTiming(intervals, refreshHz) {
  const measured = Number.isFinite(refreshHz) && refreshHz > 0;
  const budget = measured ? 1000 / refreshHz : null;
  const missed = measured
    ? intervals.reduce(
        (n, dt) => n + Math.max(0, Math.round(dt / budget) - 1),
        0,
      )
    : null;
  const fraction =
    measured && intervals.length ? missed / (intervals.length + missed) : null;
  const q = quantiles(intervals);
  return {
    intervals_ms: q,
    intervals: intervals.length,
    refresh_hz: measured ? refreshHz : null,
    budget_ms: budget,
    estimated_missed_slots: missed,
    estimated_missed_fraction: fraction,
    compositor_dropped_frames: null,
    verdict:
      fraction === null
        ? "indeterminate"
        : q.p95 <= 1.1 * budget && q.p99 <= 2 * budget && fraction <= 0.01
          ? "pass"
          : "fail",
  };
}

export class XrMetrics {
  constructor(
    metadata = {},
    emit = (record) => console.log(`XR_BENCH ${JSON.stringify(record)}`),
  ) {
    this.metadata = metadata;
    this.emit = emit;
    this.sessions = [];
    this.active = null;
  }

  start(session, now = performance.now()) {
    if (this.active) this.finish("replaced", now);
    this.active = {
      started_ms: now,
      refresh_hz: session.frameRate ?? null,
      intervals: [],
      cpu: [],
      gpu: [],
      events: [],
      frames: 0,
      last: null,
      visible:
        session.visibilityState === undefined ||
        session.visibilityState === "visible",
      last_emit_ms: now,
      resource_samples: [],
      content_checks: 0,
      incomplete_content_frames: 0,
      content_identity: null,
      bounded_frames: [],
      uncertified_bounded_frames: 0,
    };
    const current = this.active;
    session.addEventListener("visibilitychange", () => {
      if (this.active !== current) return;
      this.event(`visibility:${session.visibilityState}`);
      current.visible = session.visibilityState === "visible";
      current.last = null; // interrupted segments are recorded, not timed as active frames
    });
    session.addEventListener("frameratechange", () => {
      if (this.active !== current) return;
      this.event(`refresh:${session.frameRate}`);
      // The runtime may choose its initial rate just after sessionstart, before the
      // first frame. Only a change during measured frames mixes timing budgets.
      if (current.frames === 0 || current.refresh_hz === session.frameRate)
        current.refresh_hz = session.frameRate;
      else current.refresh_hz = null;
    });
    session.addEventListener(
      "end",
      () => {
        if (this.active === current) this.finish("session-end");
      },
      { once: true },
    );
    this.event("session-start", now);
  }

  event(kind, now = performance.now()) {
    if (!this.active) return;
    this.active.events.push({ kind, elapsed_ms: now - this.active.started_ms });
  }

  frame(timestamp, cpuMs, gpuMs, resources = null, fidelity = null) {
    const a = this.active;
    if (!a || !a.visible) return;
    let incomplete = false;
    if (fidelity) {
      if (typeof fidelity.gpu_ready === "boolean") a.content_checks++;
      const identity = JSON.stringify({
        representation: fidelity.representation,
        source_geometry: fidelity.source_geometry,
        selected: fidelity.selected,
        represented: fidelity.represented,
      });
      a.content_identity ??= identity;
      incomplete =
        fidelity.status !== "ready" ||
        fidelity.gpu_ready === false ||
        (["skeleton", "surface"].includes(fidelity.representation) &&
          fidelity.source_geometry !== true) ||
        identity !== a.content_identity;
    }
    const bounded =
      fidelity?.representation === "skeleton-bounded" ||
      a.bounded_frames.length > 0;
    if (bounded) {
      const b = fidelity?.bounded;
      const valid =
        !!b &&
        !b.error &&
        Number.isFinite(b.maximum_error_px) &&
        b.maximum_error_px >= 0 &&
        b.maximum_error_px <= 0.5 &&
        Number.isInteger(b.submitted_indices) &&
        Number.isInteger(b.source_indices) &&
        b.submitted_indices >= 0 &&
        b.source_indices >= b.submitted_indices &&
        Number.isInteger(b.fallback_pages) &&
        b.fallback_pages >= 0 &&
        Number.isInteger(b.coarse_pages) &&
        b.coarse_pages >= 0;
      if (!valid) {
        a.uncertified_bounded_frames++;
        incomplete = true;
      }
      a.bounded_frames.push([
        b?.maximum_error_px ?? null,
        b?.submitted_indices ?? null,
        b?.source_indices ?? null,
        b?.fallback_pages ?? null,
        b?.coarse_pages ?? null,
        valid ? 0 : 1,
      ]);
    }
    if (incomplete) a.incomplete_content_frames++;
    if (a.last !== null && timestamp > a.last)
      a.intervals.push(timestamp - a.last);
    a.last = timestamp;
    a.cpu.push(cpuMs);
    for (const value of gpuMs ?? [])
      if (Number.isFinite(value)) a.gpu.push(value);
    a.frames++;
    if (resources && (a.frames === 1 || timestamp - a.last_emit_ms >= 10000)) {
      a.resource_samples.push({
        elapsed_ms: timestamp - a.started_ms,
        ...(typeof resources === "function" ? resources() : resources),
      });
      a.last_emit_ms = timestamp;
      const { raw_intervals_ms, raw_bounded_frames, ...summary } =
        this.report(timestamp);
      this.emit(summary);
    }
  }

  report(now = performance.now()) {
    const a = this.active;
    if (!a) return this.sessions.at(-1) ?? null;
    return {
      schema: "flymsg.xr-bench/v1",
      ...this.metadata,
      elapsed_s: (now - a.started_ms) / 1000,
      frames: a.frames,
      timing: xrTiming(a.intervals, a.refresh_hz),
      cpu_ms: quantiles(a.cpu),
      gpu_ms: a.gpu.length ? quantiles(a.gpu) : null,
      events: [...a.events],
      resources: [...a.resource_samples],
      content: {
        identity: a.content_identity ? JSON.parse(a.content_identity) : null,
        checked_frames: a.content_checks,
        incomplete_frames: a.incomplete_content_frames,
        verdict: a.incomplete_content_frames
          ? "fail"
          : a.content_checks === a.frames && a.frames
            ? "pass"
            : "indeterminate",
      },
      // Raw intervals allow independent scoring; every long frame is retained.
      raw_intervals_ms: [...a.intervals],
      bounded: a.bounded_frames.length
        ? {
            checked_frames: a.bounded_frames.length,
            uncertified_frames: a.uncertified_bounded_frames,
            fields: [
              "maximum_error_px",
              "submitted_indices",
              "source_indices",
              "fallback_pages",
              "coarse_pages",
              "invalid",
            ],
            verdict: a.uncertified_bounded_frames
              ? "fail"
              : a.bounded_frames.length === a.frames
                ? "pass"
                : "indeterminate",
          }
        : null,
      raw_bounded_frames: a.bounded_frames.map((row) => [...row]),
      status: "running",
    };
  }

  finish(reason, now = performance.now()) {
    if (!this.active) return;
    this.event(reason, now);
    const record = { ...this.report(now), status: "ended", reason };
    this.sessions.push(record);
    this.active = null;
    this.emit(record);
    return record;
  }
}
