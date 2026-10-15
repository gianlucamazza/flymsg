// Keep the current complete raster while its bin and static inputs are unchanged.
import { binAt } from "./raster.js";

function paintBackground(ctx, state, width) {
  const { rows } = state;
  const rasterX = (ms, w) =>
    120 + (ms / (state.bins * state.binMs)) * (w - 124);
  const plotH = rows.length * 9;
  ctx.fillStyle = "rgba(76, 201, 240, 0.12)"; // stimulus window
  ctx.fillRect(
    rasterX(0, width),
    0,
    rasterX(state.stimMs, width) - rasterX(0, width),
    plotH,
  );
  ctx.font = "10px system-ui, sans-serif";
  ctx.textBaseline = "middle";
  const cellW = Math.max(
    1,
    rasterX(state.binMs, width) - rasterX(0, width) - 0.5,
  );
  rows.forEach(({ k, counts, total }, i) => {
    const y = i * 9;
    const { label, colour } = rows[i];
    ctx.fillStyle = colour;
    ctx.fillText(label, 2, y + 9 / 2);
    if (!total) {
      ctx.fillStyle = "#7b8494";
      ctx.fillText("no spikes in this replay", 120, y + 9 / 2);
      return;
    }
    for (let b = 0; b < counts.length; b++) {
      if (!counts[b]) continue;
      ctx.globalAlpha = Math.min(1, 0.35 + counts[b] / 3);
      ctx.fillStyle = colour;
      ctx.fillRect(rasterX(b * state.binMs, width), y + 1, cellW, 9 - 2);
    }
    ctx.globalAlpha = 1;
  });
  // axis every 100 ms
  ctx.fillStyle = "#7b8494";
  ctx.textBaseline = "top";
  for (let ms = 0; ms <= state.bins * state.binMs; ms += 100)
    ctx.fillText(`${ms}`, rasterX(ms, width) - 6, plotH + 4);
}

export class RasterPainter {
  constructor(canvas) {
    this.canvas = canvas;
    this.state = null;
    this.draws = this.skips = 0;
  }

  draw(state, { width, ratio, time }) {
    const height = state.rows.length * 9 + 18;
    const changed =
      this.state !== state || this.width !== width || this.ratio !== ratio;
    const bin = binAt(time, state.binMs, state.bins);
    if (!changed && bin === this.bin) {
      this.skips++;
      return false;
    }
    this.state = state;
    this.width = width;
    this.ratio = ratio;
    // Preserve the original reset and drawing order on every changed raster frame.
    this.canvas.width = width * ratio;
    this.canvas.height = height * ratio;
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    const ctx = this.canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    paintBackground(ctx, state, width);
    const x = (ms) => 120 + (ms / (state.bins * state.binMs)) * (width - 124);
    const cellW = Math.max(1, x(state.binMs) - x(0) - 0.5);
    ctx.strokeStyle = "#ffffff";
    ctx.strokeRect(x(bin * state.binMs), 0, cellW, state.rows.length * 9);
    this.bin = bin;
    this.draws++;
    return true;
  }

  clear() {
    this.state = null;
  }

  report() {
    return { draws: this.draws, skips: this.skips, cache_bytes: 0 };
  }
}
