"""Static figures for the docs, as SVG written with the standard library only.

Each function takes the numbers a run already wrote and returns an SVG string; it computes
nothing scientific, so a figure is a drawing of a result, never a new one.
`scripts/build_figures.py` reads the run outputs and writes `docs/img/*.svg`.
"""

from __future__ import annotations

import math
import xml.sax.saxutils as xml
from collections.abc import Sequence

import numpy as np
import pandas as pd

BLUE, RED, GREEN, GOLD, GREY = "#2b6cb0", "#d1495b", "#3d9970", "#b8860b", "#888888"


def ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    """Round tick values covering [lo, hi], about `n` of them (steps of 1, 2 or 5 × 10^k)."""
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    first = math.ceil(lo / step - 1e-9) * step
    return [
        round(first + k * step, 12) for k in range(int((hi - first) / step + 1e-9) + 1)
    ]


def _fmt(v: float) -> str:
    return f"{v:g}"


class Panel:
    """One set of axes at (x0, y0) of size w × h, mapping data limits to pixels."""

    def __init__(self, x0, y0, w, h, xlim, ylim, title="", xlabel="", ylabel=""):
        self.x0, self.y0, self.w, self.h = x0, y0, w, h
        self.xlim, self.ylim = xlim, ylim
        self.title, self.xlabel, self.ylabel = title, xlabel, ylabel
        self.out: list[str] = []

    def X(self, v: float) -> float:
        a, b = self.xlim
        return self.x0 + (v - a) / (b - a) * self.w

    def Y(self, v: float) -> float:
        a, b = self.ylim
        return self.y0 + self.h - (v - a) / (b - a) * self.h

    def frame(
        self, xticks: Sequence[float] | None = None, xticklabels=None, rotate: int = 0
    ) -> Panel:
        x0, y0, w, h = self.x0, self.y0, self.w, self.h
        self.out.append(
            f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="none" stroke="#999"/>'
        )
        if self.title:
            self.out.append(
                f'<text x="{x0}" y="{y0 - 6}" font-size="11">{xml.escape(self.title)}</text>'
            )
        for v in ticks(*self.ylim):
            y = self.Y(v)
            self.out.append(
                f'<line x1="{x0 - 3}" x2="{x0}" y1="{y:.1f}" y2="{y:.1f}" stroke="#999"/>'
                f'<text x="{x0 - 5}" y="{y + 3:.1f}" text-anchor="end">{_fmt(v)}</text>'
            )
        xs = ticks(*self.xlim) if xticks is None else list(xticks)
        labels = [_fmt(v) for v in xs] if xticklabels is None else list(xticklabels)
        for v, label in zip(xs, labels, strict=True):
            x, ty = self.X(v), y0 + h + 14
            turn = (
                f' text-anchor="end" transform="rotate({rotate} {x:.1f} {ty})"'
                if rotate
                else ' text-anchor="middle"'
            )
            self.out.append(
                f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y0 + h}" y2="{y0 + h + 3}" '
                f'stroke="#999"/><text x="{x:.1f}" y="{ty}"{turn}>{xml.escape(label)}</text>'
            )
        if self.xlabel:
            self.out.append(
                f'<text x="{x0 + w / 2}" y="{y0 + h + 28}" text-anchor="middle">'
                f"{xml.escape(self.xlabel)}</text>"
            )
        if self.ylabel:
            cx, cy = x0 - 34, y0 + h / 2
            self.out.append(
                f'<text x="{cx}" y="{cy}" text-anchor="middle" '
                f'transform="rotate(-90 {cx} {cy})">{xml.escape(self.ylabel)}</text>'
            )
        return self

    def line(self, xs, ys, colour, width=1.5, dash="", step=False) -> Panel:
        pts = []
        for i, (x, y) in enumerate(zip(xs, ys, strict=True)):
            if step and i:
                pts.append(f"{self.X(x):.1f},{self.Y(ys[i - 1]):.1f}")
            pts.append(f"{self.X(x):.1f},{self.Y(y):.1f}")
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.out.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{colour}" '
            f'stroke-width="{width}"{d}/>'
        )
        return self

    def band(self, xs, lo, hi, colour, opacity=0.15) -> Panel:
        pts = [f"{self.X(x):.1f},{self.Y(v):.1f}" for x, v in zip(xs, hi, strict=True)]
        pts += [
            f"{self.X(x):.1f},{self.Y(v):.1f}"
            for x, v in zip(reversed(xs), reversed(lo), strict=True)
        ]
        self.out.append(
            f'<polygon points="{" ".join(pts)}" fill="{colour}" fill-opacity="{opacity}"/>'
        )
        return self

    def hline(self, y, colour=GREY, dash="4 3", label="") -> Panel:
        self.out.append(
            f'<line x1="{self.x0}" x2="{self.x0 + self.w}" y1="{self.Y(y):.1f}" '
            f'y2="{self.Y(y):.1f}" stroke="{colour}" stroke-dasharray="{dash}"/>'
        )
        if label:
            self.text(self.x0 + self.w - 3, self.Y(y) - 3, label, colour, "end")
        return self

    def vspan(self, a, b, colour="#000", opacity=0.05) -> Panel:
        self.out.append(
            f'<rect x="{self.X(a):.1f}" y="{self.y0}" width="{self.X(b) - self.X(a):.1f}" '
            f'height="{self.h}" fill="{colour}" fill-opacity="{opacity}"/>'
        )
        return self

    def bar(self, x, width, y0, y1, colour, opacity=1.0) -> Panel:
        top, bottom = sorted((self.Y(y0), self.Y(y1)))
        self.out.append(
            f'<rect x="{self.X(x - width / 2):.1f}" y="{top:.1f}" '
            f'width="{self.X(x + width / 2) - self.X(x - width / 2):.1f}" '
            f'height="{bottom - top:.1f}" fill="{colour}" fill-opacity="{opacity}"/>'
        )
        return self

    def dot(self, x, y, colour, r=2.5) -> Panel:
        self.out.append(
            f'<circle cx="{self.X(x):.1f}" cy="{self.Y(y):.1f}" r="{r}" fill="{colour}"/>'
        )
        return self

    def text(self, x, y, s, colour="#222", anchor="start") -> Panel:
        """Text at pixel position (x, y)."""
        self.out.append(
            f'<text x="{x:.1f}" y="{y:.1f}" fill="{colour}" text-anchor="{anchor}">'
            f"{xml.escape(s)}</text>"
        )
        return self

    def legend(self, items: Sequence[tuple[str, str]], x=None, y=None) -> Panel:
        x = self.x0 + 6 if x is None else x
        y = self.y0 + 12 if y is None else y
        for k, (label, colour) in enumerate(items):
            yy = y + 12 * k
            self.out.append(
                f'<line x1="{x}" x2="{x + 14}" y1="{yy - 3}" y2="{yy - 3}" '
                f'stroke="{colour}" stroke-width="2"/>'
            )
            self.text(x + 18, yy, label, colour)
        return self


def document(width: int, height: int, title: str, panels: Sequence[Panel]) -> str:
    body = [p for panel in panels for p in panel.out]
    return "\n".join(
        [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
                f'height="{height}" viewBox="0 0 {width} {height}" '
                'font-family="system-ui, sans-serif" font-size="10">'
            ),
            f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
            f'<text x="12" y="18" font-size="12">{xml.escape(title)}</text>',
            *body,
            "</svg>",
        ]
    )


def _counts(cell) -> list[float]:
    return [float(v) for v in str(cell).strip("[]").split(",")]


def silence_scan(
    screen: pd.DataFrame,
    confirm: pd.DataFrame,
    base_screen: Sequence[float],
    base_confirm: Sequence[float],
) -> str:
    """Screen: TTMn_R spikes per silenced unit (bar = mean, dots = seeds) against the base
    arm and the half-of-base bar. Confirm: the screen passes on fresh seeds against the
    base arm and the null mean."""
    screen = screen.sort_values("mean").reset_index(drop=True)
    top = max(8.0, max(base_screen) + 1, max(max(_counts(c)) for c in screen["counts"]))
    a = Panel(60, 40, 560, 220, (-0.7, len(screen) - 0.3), (0, top),
              "Screen, seeds 0–2: DNp01 and one unit silenced",
              ylabel="TTMn_R spikes in 300 ms")  # fmt: skip
    a.frame(range(len(screen)), [str(u) for u in screen["unit"]], rotate=-35)
    base = float(np.mean(base_screen))
    a.hline(base, GREY, "4 3", f"base arm (DNp01 only) {base:.1f}")
    a.hline(base / 2, RED, "2 3", f"screen bar: half of base {base / 2:.1f}")
    for i, row in screen.iterrows():
        colour = RED if row["passes"] else BLUE
        a.bar(i, 0.6, 0, row["mean"], colour, 0.35)
        for s in _counts(row["counts"]):
            a.dot(i, s, colour, 2)
    b = Panel(700, 40, 250, 220, (-0.6, len(confirm) - 0.4), (0, top),
              "Confirmation, fresh seeds 20–22")  # fmt: skip
    b.frame(range(len(confirm)), [str(u) for u in confirm["unit"]])
    base_c = float(np.mean(base_confirm))
    b.hline(base_c, GREY, "4 3", f"base arm {base_c:.1f}")
    for i, row in confirm.reset_index(drop=True).iterrows():
        b.bar(i, 0.5, 0, row["null_mean"], GREY, 0.35)
        for s in _counts(row["counts"]):
            b.dot(i, s, RED, 2.5)
        b.text(b.X(i), b.Y(row["null_mean"]) - 4, f"null mean {row['null_mean']:.2f}",
               GREY, "middle")  # fmt: skip
        b.text(b.X(i), b.Y(0) - 8, f"p {row['p']:.3f}", RED, "middle")
    b.text(b.x0, b.y0 + b.h + 30, "red dots: observed per seed; grey bar: matched null",
           GREY)  # fmt: skip
    return document(980, 340, "Residual TTMn_R partner scan v2 (model, LC4_R 100 Hz, "
                    "both DNp01 silenced): verdict names_partner DNp02, DNp06", [a, b])  # fmt: skip


def embodiment(intact: dict, silenced: dict, loop: dict) -> str:
    """M1 height with and without DNp01; M2 input rate, height and motor spikes per mode."""
    m_to_um = 1e6
    t1 = float(max(intact["time_ms"][-1], silenced["time_ms"][-1]))
    heights = [intact["height_m"], silenced["height_m"],
               *(loop[f"{m}_height_m"] for m in ("closed", "shuffled"))]  # fmt: skip
    # an axis needs a span: 1 µm when no body leaves the ground
    hmax = max(1.0, max(float(np.max(h)) for h in heights) * m_to_um * 1.1)
    a = Panel(70, 40, 380, 150, (0, t1), (0, hmax),
              "M1: jump body driven by TTMn_R (LC4_R 100 Hz)",
              "time (ms)", "height (µm)")  # fmt: skip
    a.frame()
    a.line(intact["time_ms"], [h * m_to_um for h in intact["height_m"]], BLUE)
    a.line(silenced["time_ms"], [h * m_to_um for h in silenced["height_m"]], RED)
    a.legend([(f"intact, takeoff {intact['takeoff_ms']:g} ms", BLUE),
              (f"DNp01 silenced, takeoff {silenced['takeoff_ms']:g} ms", RED)],
             x=a.X(330), y=a.Y(hmax * 0.6))  # fmt: skip
    t = loop["closed_t_ms"]
    modes = (("closed", BLUE, ""), ("disconnected", GOLD, "5 3"),
             ("replay", GREEN, "1 3"), ("shuffled", RED, ""))  # fmt: skip
    rmax = max(1.0, max(float(np.max(loop[f"{m}_rate_hz"])) for m, _, _ in modes) * 1.1)
    b = Panel(540, 40, 380, 150, (0, float(t[-1])), (0, rmax),
              "M2: input rate (engineered transducer)", "time (ms)", "Hz")  # fmt: skip
    b.frame()
    c = Panel(70, 250, 380, 150, (0, float(t[-1])), (0, hmax),
              "M2: body height", "time (ms)", "height (µm)")  # fmt: skip
    c.frame()
    smax = max(int(np.sum(loop[f"{m}_motor_spikes"])) for m, _, _ in modes) + 1
    d = Panel(540, 250, 380, 150, (0, float(t[-1])), (0, smax),
              "M2: cumulative TTMn_R spikes", "time (ms)", "spikes")  # fmt: skip
    d.frame()
    for m, colour, dash in modes:
        b.line(t, loop[f"{m}_rate_hz"], colour, 1.2, dash)
        c.line(t, loop[f"{m}_height_m"] * m_to_um, colour, 1.5, dash)
        d.line(t, np.cumsum(loop[f"{m}_motor_spikes"]), colour, 1.5, dash, step=True)
    d.legend([(m, colour) for m, colour, _ in modes], x=d.x0 + 8)
    c.text(c.x0, c.y0 + c.h + 44,
           "closed, disconnected and replay coincide: the disc is centimetres away, so a "
           "body moving microns does not change the input", GREY)  # fmt: skip
    return document(960, 470, "Embodiment M1/M2 (engineered decoder and transducer; "
                    "not a behaviour of the fly)", [a, b, c, d])  # fmt: skip


def kc_persistence(
    t_ms: np.ndarray, groups: dict[str, np.ndarray], stim_ms: float, note: str
) -> str:
    """Population rate over time per group, with the stimulus window shaded."""
    colours = [BLUE, RED, GREEN, GOLD, GREY]
    top = max(1.0, max(float(np.max(v)) for v in groups.values()) * 1.1)
    a = Panel(70, 40, 560, 220, (0, float(t_ms[-1])), (0, top),
              "Mean rate per neuron of each group (10 ms bins)", "time (ms)",
              "Hz")  # fmt: skip
    a.frame().vspan(0, stim_ms)
    a.text(a.X(stim_ms / 2), a.y0 + 12, "stimulus", GREY, "middle")
    for (label, v), colour in zip(groups.items(), colours, strict=False):
        a.line(t_ms, v, colour, 1.5, step=True)
    a.legend([(k, c) for k, c in zip(groups, colours, strict=False)],
             x=a.x0 + a.w + 14, y=a.y0 + 12)  # fmt: skip
    for k, part in enumerate(note.split("\n")):
        a.text(a.x0, a.y0 + a.h + 44 + 13 * k, part, GREY)
    return document(900, 350, "Held-out ORN_DM1 case (exploratory diagnosis): activity "
                    "outlasts the stimulus in the Kenyon cells", [a])  # fmt: skip


def homology_pilot(pilot: pd.DataFrame) -> str:
    """LC4 share of each giant fiber's input and raw LC4 synapses, male against female."""
    rows = pilot.reset_index(drop=True)
    labels = [f"{r.dataset} {str(r.DNp01)[-1]}" for r in rows.itertuples()]
    colours = [BLUE if r.dataset == "male" else RED for r in rows.itertuples()]
    smax = float(rows["share_of_input"].max()) * 100 * 1.25
    a = Panel(70, 40, 360, 200, (-0.6, len(rows) - 0.4), (0, smax),
              "LC4 share of the giant fiber's input", ylabel="% of input synapses")  # fmt: skip
    a.frame(range(len(rows)), labels)
    synmax = float(rows["LC4_synapses"].max()) * 1.15
    b = Panel(520, 40, 360, 200, (-0.6, len(rows) - 0.4), (0, synmax),
              "LC4 → DNp01 synapses: raw (bar), divided by density ratio (dot)",
              ylabel="synapses")  # fmt: skip
    b.frame(range(len(rows)), labels)
    for i, r in rows.iterrows():
        a.bar(i, 0.6, 0, r["share_of_input"] * 100, colours[i], 0.6)
        a.text(a.X(i), a.Y(r["share_of_input"] * 100) - 4,
               f"{100 * r['share_of_input']:.1f}%", colours[i], "middle")  # fmt: skip
        b.bar(i, 0.6, 0, r["LC4_synapses"], colours[i], 0.6)
        b.dot(i, r["density_scaled"], "#222", 3)
    ratio = float(rows["density_ratio"].iat[0])
    b.text(b.x0, b.y0 + b.h + 30,
           f"male/female synapse density ratio {ratio:.2f} (median over "
           f"{int(rows['ratio_types'].iat[0])} matched types)", GREY)  # fmt: skip
    a.text(a.x0, a.y0 + a.h + 30,
           "a difference between reconstructions, not attributed to sex", GREY)  # fmt: skip
    return document(920, 300, "Homology pilot (#29): LC4 → DNp01 in MaleCNS and FAFB",
                    [a, b])  # fmt: skip
