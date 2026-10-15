// Independent original canvas implementation, compared in the same browser/font environment.
import { RasterPainter } from "./raster-painter.js";
import { rasterReference } from "./raster-reference.js";

export async function rasterOracle({ timingSamples = 200, cpu = false } = {}) {
  if (
    !Number.isInteger(timingSamples) ||
    timingSamples < 0 ||
    timingSamples > 1000
  )
    throw new RangeError("Invalid raster timing sample count");
  await document.fonts.ready;
  const create = () => {
    const canvas = document.createElement("canvas");
    if (cpu) canvas.getContext("2d", { willReadFrequently: true });
    return canvas;
  };
  const colours = {
    context: "#7b8494",
    selected: "#4cc9f0",
    upstream: "#f72585",
  };
  const neurons = Array.from({ length: 40 }, (_, k) => ({
    type: `neuron-${k}-long-name`,
  }));
  const focus = new Map(
    neurons.map((_, k) => [k, k % 2 ? "upstream" : "selected"]),
  );
  const rows = neurons.map((_, k) => {
    const counts = Uint8Array.from({ length: 60 }, (_, b) =>
      k % 7 && (b + k) % 3 ? (b * 7 + k) % 6 : 0,
    );
    return { k, counts, total: counts.reduce((a, b) => a + b, 0) };
  });
  const A = { bins: 60, bin_ms: 10, stim_ms: 300 };
  const state = (rs) => ({
    rows: rs.map((row) => ({
      ...row,
      label: neurons[row.k].type.slice(0, 18),
      colour: colours[focus.get(row.k)],
    })),
    bins: A.bins,
    binMs: A.bin_ms,
    stimMs: A.stim_ms,
  });
  const original = create(),
    candidate = create();
  const painter = new RasterPainter(candidate);
  // Read separate sinks so repeated verification cannot migrate only one source
  // canvas from GPU to CPU rasterization through Chromium's readback heuristic.
  const sinks = [create(), create()];
  const capture = (source, sink) => {
    sink.width = source.width;
    sink.height = source.height;
    const ctx = sink.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(source, 0, 0);
    return ctx.getImageData(0, 0, sink.width, sink.height).data;
  };
  let comparisons = 0;
  const cases = [];
  for (const ratio of [1, 1.25, 2, 3]) {
    for (const width of [272, 560]) {
      for (const n of [1, 40]) {
        const rs = rows.slice(0, n),
          s = state(rs);
        for (const time of [0, 0.5, 10, 310, 599, 0]) {
          rasterReference(
            original,
            { rows: rs },
            {
              innerWidth: width + 48,
              devicePixelRatio: ratio,
              A,
              neurons,
              FOCUS_COLORS: colours,
              view: { focus },
              clock: { t: time },
            },
          );
          painter.draw(s, { width, ratio, time });
          const a = capture(original, sinks[0]);
          const b = capture(candidate, sinks[1]);
          if (a.length !== b.length) throw Error("Raster size differs");
          const mismatch = a.findIndex((v, i) => v !== b[i]);
          if (mismatch >= 0)
            throw Error(
              `Raster mismatch ratio=${ratio} width=${width} rows=${n} t=${time} byte=${mismatch} ${a[mismatch]} != ${b[mismatch]}`,
            );
          comparisons++;
        }
        cases.push({ ratio, width, rows: n });
      }
    }
  }
  const timings = [],
    s = state(rows);
  for (const workload of ["same-bin-replay", "every-bin-changes"]) {
    for (const [order, mode] of (timingSamples
      ? ["original", "cached", "cached", "original"]
      : []
    ).entries()) {
      const times = [];
      for (let j = 0; j < timingSamples + 5; j++) {
        const time =
          workload === "same-bin-replay"
            ? (j * (1000 / 90) * 0.04) % 600
            : (j % 60) * 10;
        const start = performance.now();
        if (mode === "original")
          rasterReference(
            original,
            { rows },
            {
              innerWidth: 608,
              devicePixelRatio: 2,
              A,
              neurons,
              FOCUS_COLORS: colours,
              view: { focus },
              clock: { t: time },
            },
          );
        else painter.draw(s, { width: 560, ratio: 2, time });
        // Force completion of the complete bitmap for BOTH implementations.
        capture(mode === "original" ? original : candidate, sinks[0]);
        if (j >= 5) times.push(performance.now() - start);
      }
      timings.push({ workload, order, mode, serialized_wall_ms: times });
    }
  }
  painter.clear();
  if (painter.report().cache_bytes !== 0)
    throw Error("Raster cache not released");
  return {
    status: "pass",
    comparisons,
    canvas_backend: cpu ? "CPU 2D correctness only" : "browser default",
    cases,
    timings,
    rule: "Every RGBA byte must match the independent frozen original; timings include full readback, not frame rate.",
    cache_released: true,
    browser: navigator.userAgent,
  };
}
