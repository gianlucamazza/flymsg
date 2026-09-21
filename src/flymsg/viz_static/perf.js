// Frame and loading measurements for the HUD and the `?bench=<s>` summary.
//
// GPU time comes from EXT_disjoint_timer_query_webgl2 when the browser exposes it (queries
// are read back a few frames later); otherwise only CPU time and frame intervals are known.

const KEEP = 600; // frames kept for percentiles

export function percentile(values, p) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor((p / 100) * s.length))];
}

export class Perf {
  constructor(renderer) {
    this.renderer = renderer;
    renderer.info.autoReset = false; // the composer renders several passes per frame
    this.gl = renderer.getContext();
    this.timer = this.gl.getExtension("EXT_disjoint_timer_query_webgl2");
    this.pending = [];
    this.cpu = [];
    this.gpu = [];
    this.intervals = [];
    this.t0 = performance.now();
    this.last = null;
    this.loaded = {
      manifests: 0,
      fragments: 0,
      skeletons: 0,
      neuropils: 0,
      bytes: 0,
    };
    this.marks = {};
    this.selectMs = [];
    this.frame = { calls: 0, triangles: 0, lines: 0 };
  }

  begin() {
    this.renderer.info.reset();
    this.cpuStart = performance.now();
    if (this.timer && !this.query) {
      this.query = this.gl.createQuery();
      this.gl.beginQuery(this.timer.TIME_ELAPSED_EXT, this.query);
    }
  }

  end() {
    const now = performance.now();
    const push = (a, v) => {
      a.push(v);
      if (a.length > KEEP) a.shift();
    };
    push(this.cpu, now - this.cpuStart);
    // only consecutive frames count: renders on demand leave long idle gaps
    if (this.last !== null && now - this.last < 100) push(this.intervals, now - this.last);
    this.last = now;
    const r = this.renderer.info.render;
    this.frame = { calls: r.calls, triangles: r.triangles, lines: r.lines };
    if (this.query) {
      this.gl.endQuery(this.timer.TIME_ELAPSED_EXT);
      this.pending.push(this.query);
      this.query = null;
    }
    this.poll(push);
  }

  poll(push) {
    const gl = this.gl;
    const disjoint = this.timer && gl.getParameter(this.timer.GPU_DISJOINT_EXT);
    while (this.pending.length) {
      const q = this.pending[0];
      if (!gl.getQueryParameter(q, gl.QUERY_RESULT_AVAILABLE)) break;
      const ns = gl.getQueryParameter(q, gl.QUERY_RESULT);
      if (!disjoint) push(this.gpu, ns / 1e6);
      gl.deleteQuery(q);
      this.pending.shift();
    }
  }

  /** Recent GPU frame time (ms), or null when the timer extension is missing. */
  get gpuMs() {
    return this.gpu.length ? percentile(this.gpu.slice(-30), 50) : null;
  }

  /** Median GPU time of the last `n` measured frames, or null. */
  recentGpuMs(n) {
    return this.gpu.length >= n ? percentile(this.gpu.slice(-n), 50) : null;
  }

  get fps() {
    const i = percentile(this.intervals.slice(-60), 50);
    return i ? 1000 / i : 0;
  }

  count(kind, bytes = 0) {
    this.loaded[kind]++;
    this.loaded.bytes += bytes;
  }

  /** Seconds since start at which `name` first happened. */
  mark(name) {
    if (!(name in this.marks))
      this.marks[name] = +((performance.now() - this.t0) / 1000).toFixed(2);
  }

  line(pixelRatio, samples) {
    const gpu = this.gpuMs;
    const sel = percentile(this.selectMs.slice(-20), 50);
    return (
      `${this.fps.toFixed(0)} fps · cpu ${(percentile(this.cpu.slice(-30), 50) ?? 0).toFixed(1)} ms` +
      ` · gpu ${gpu === null ? "n/a" : gpu.toFixed(1) + " ms"} · ${this.frame.calls} draws` +
      ` · ${(this.frame.triangles / 1e6).toFixed(1)} M tris · ${(this.frame.lines / 1e6).toFixed(1)} M lines` +
      ` · ×${pixelRatio.toFixed(2)} px · MSAA ${samples || "off"} · select ${sel === null ? "–" : sel.toFixed(1) + " ms"}`
    );
  }

  summary(extra = {}) {
    const elapsed = (performance.now() - this.t0) / 1000;
    const ms = (a) => ({ p50: percentile(a, 50), p95: percentile(a, 95) });
    const fps = (p) => {
      const i = percentile(this.intervals, p);
      return i ? +(1000 / i).toFixed(1) : null;
    };
    return {
      elapsed_s: +elapsed.toFixed(1),
      fps: { p50: fps(50), p5: fps(95) },
      cpu_ms: ms(this.cpu),
      gpu_ms: this.timer ? ms(this.gpu) : null,
      select_ms: ms(this.selectMs),
      frame: this.frame,
      loaded: {
        ...this.loaded,
        mb_per_s: +(this.loaded.bytes / 1e6 / elapsed).toFixed(2),
      },
      marks: this.marks,
      ...extra,
    };
  }
}
