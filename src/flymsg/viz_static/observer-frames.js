// Opt-in observer telemetry. Only the existing application loop supplies frames.
export class ObserverFrames {
  constructor(documentId = globalThis.crypto.randomUUID()) {
    this.documentId = documentId;
    this.loops = 0;
    this.submitted = 0;
    this.generation = 0;
    this.capture = null;
  }

  loop() {
    this.loops++;
  }

  invalidate(reason) {
    if (this.capture && !this.capture.reasons.includes(reason))
      this.capture.reasons.push(reason);
  }

  contextLost() {
    this.generation++;
    this.invalidate("context-lost");
  }

  status() {
    return {
      document_id: this.documentId,
      loop_callbacks: this.loops,
      submitted_frames: this.submitted,
      context_generation: this.generation,
      capture_running: !!this.capture,
    };
  }

  start(seconds, identity, now = performance.now()) {
    if (this.capture) throw Error("An observer capture is already active");
    if (!Number.isFinite(seconds) || seconds < 5 || seconds > 120)
      throw RangeError("Observer capture requires 5..120 seconds");
    this.capture = {
      seconds,
      started_ms: now,
      identity: structuredClone(identity),
      last: null,
      raw_intervals_ms: [],
      cpu_ms: [],
      gpu_ms: [],
      reasons: [],
      frames: 0,
    };
  }

  frame(timestamp, identity, measured = {}) {
    this.submitted++;
    const c = this.capture;
    if (!c) return;
    if (JSON.stringify(identity) !== JSON.stringify(c.identity))
      this.invalidate("render-identity-changed");
    // Keep all samples, including long stalls and an overrun of the requested window.
    if (c.frames >= 28801) {
      this.invalidate("sample-capacity-exceeded");
      return;
    }
    if (c.last !== null) {
      const interval = timestamp - c.last;
      if (!(interval > 0)) this.invalidate("non-monotonic-frame-clock");
      c.raw_intervals_ms.push(interval);
    }
    c.last = timestamp;
    c.frames++;
    if (Number.isFinite(measured.cpu_ms)) c.cpu_ms.push(measured.cpu_ms);
    if (Array.isArray(measured.gpu_ms))
      c.gpu_ms.push(...measured.gpu_ms.filter(Number.isFinite));
  }

  finish(now = performance.now()) {
    const c = this.capture;
    if (!c) throw Error("No observer capture is active");
    this.capture = null;
    const wall_ms = now - c.started_ms;
    if (wall_ms < c.seconds * 1000) c.reasons.push("incomplete-window");
    if (c.raw_intervals_ms.length < 20)
      c.reasons.push("insufficient-application-frames");
    const sorted = [...c.raw_intervals_ms].sort((a, b) => a - b);
    const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : null;
    const terminal_gap_ms =
      c.last === null ? wall_ms : Math.max(0, now - c.last);
    if (terminal_gap_ms > Math.max(100, 2 * (median ?? 0)))
      c.reasons.push("incomplete-terminal-cadence");
    return {
      ...c,
      wall_ms,
      terminal_gap_ms,
      document_id: this.documentId,
      eligible: c.reasons.length === 0,
      metric: "application submitted-frame intervals; not compositor drops",
    };
  }
}
