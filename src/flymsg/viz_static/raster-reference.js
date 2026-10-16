// Frozen original drawRaster from 63c63d6. Diagnostic oracle only; no candidate helpers.
import { binAt } from "./raster.js";
export function rasterReference(
  rasterCanvas,
  rasterState,
  { innerWidth, devicePixelRatio, A, neurons, FOCUS_COLORS, view, clock },
) {
  const RASTER_LABEL_PX = 120,
    RASTER_ROW_PX = 9,
    RASTER_AXIS_PX = 18;
  const rasterSpanMs = () => A.bins * A.bin_ms;
  const rasterX = (ms, width) =>
    RASTER_LABEL_PX + (ms / rasterSpanMs()) * (width - RASTER_LABEL_PX - 4);
  const { rows } = rasterState;
  const width = Math.min(560, innerWidth - 48);
  const height = rows.length * RASTER_ROW_PX + RASTER_AXIS_PX;
  const ratio = devicePixelRatio || 1;
  rasterCanvas.width = width * ratio;
  rasterCanvas.height = height * ratio;
  rasterCanvas.style.width = `${width}px`;
  rasterCanvas.style.height = `${height}px`;
  const ctx = rasterCanvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const plotH = rows.length * RASTER_ROW_PX;
  ctx.fillStyle = "rgba(76, 201, 240, 0.12)"; // stimulus window
  ctx.fillRect(
    rasterX(0, width),
    0,
    rasterX(A.stim_ms, width) - rasterX(0, width),
    plotH,
  );
  ctx.font = "10px system-ui, sans-serif";
  ctx.textBaseline = "middle";
  const cellW = Math.max(1, rasterX(A.bin_ms, width) - rasterX(0, width) - 0.5);
  rows.forEach(({ k, counts, total }, i) => {
    const y = i * RASTER_ROW_PX;
    const n = neurons[k];
    const colour = FOCUS_COLORS[view.focus?.get(k) ?? "context"];
    ctx.fillStyle = colour;
    ctx.fillText((n.instance || n.type).slice(0, 18), 2, y + RASTER_ROW_PX / 2);
    if (!total) {
      ctx.fillStyle = "#7b8494";
      ctx.fillText(
        "no spikes in this replay",
        RASTER_LABEL_PX,
        y + RASTER_ROW_PX / 2,
      );
      return;
    }
    for (let b = 0; b < counts.length; b++) {
      if (!counts[b]) continue;
      ctx.globalAlpha = Math.min(1, 0.35 + counts[b] / 3);
      ctx.fillStyle = colour;
      ctx.fillRect(
        rasterX(b * A.bin_ms, width),
        y + 1,
        cellW,
        RASTER_ROW_PX - 2,
      );
    }
    ctx.globalAlpha = 1;
  });
  // axis every 100 ms
  ctx.fillStyle = "#7b8494";
  ctx.textBaseline = "top";
  for (let ms = 0; ms <= rasterSpanMs(); ms += 100)
    ctx.fillText(`${ms}`, rasterX(ms, width) - 6, plotH + 4);
  // cursor on the bin the glow is showing
  const b = binAt(clock.t, A.bin_ms, A.bins);
  ctx.strokeStyle = "#ffffff";
  ctx.strokeRect(rasterX(b * A.bin_ms, width), 0, cellW, plotH);
}
