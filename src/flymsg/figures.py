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
        self,
        xticks: Sequence[float] | None = None,
        xticklabels=None,
        rotate: int = 0,
        yticks: Sequence[float] | None = None,
    ) -> Panel:
        x0, y0, w, h = self.x0, self.y0, self.w, self.h
        self.out.append(
            f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="none" stroke="#999"/>'
        )
        if self.title:
            self.out.append(
                f'<text x="{x0}" y="{y0 - 6}" font-size="11">{xml.escape(self.title)}</text>'
            )
        for v in ticks(*sorted(self.ylim)) if yticks is None else yticks:
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

    def hbar(self, y, height, x0, x1, colour, opacity=1.0) -> Panel:
        left, right = sorted((self.X(x0), self.X(x1)))
        top, bottom = sorted((self.Y(y - height / 2), self.Y(y + height / 2)))
        self.out.append(
            f'<rect x="{left:.1f}" y="{top:.1f}" width="{right - left:.1f}" '
            f'height="{bottom - top:.1f}" fill="{colour}" fill-opacity="{opacity}"/>'
        )
        return self

    def dot(self, x, y, colour, r=2.5) -> Panel:
        self.out.append(
            f'<circle cx="{self.X(x):.1f}" cy="{self.Y(y):.1f}" r="{r}" fill="{colour}"/>'
        )
        return self

    def ring(self, x, y, colour, r=3.2) -> Panel:
        self.out.append(
            f'<circle cx="{self.X(x):.1f}" cy="{self.Y(y):.1f}" r="{r}" fill="none" '
            f'stroke="{colour}" stroke-width="1.2"/>'
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
    confirm_seeds: str = "20–22",
    version: int = 2,
) -> str:
    """Screen: TTMn_R spikes per silenced unit (bar = mean, dots = seeds) against the base
    arm and the half-of-base bar. Confirm: the screen passes on fresh seeds against the
    base arm and the null mean."""
    screen = screen.sort_values("mean").reset_index(drop=True)
    top = max(8.0, max(base_screen) + 1, max(max(_counts(c)) for c in screen["counts"]))
    a = Panel(
        60,
        40,
        560,
        220,
        (-0.7, len(screen) - 0.3),
        (0, top),
        "Screen, seeds 0–2: DNp01 and one unit silenced",
        ylabel="TTMn_R spikes in 300 ms",
    )
    a.frame(range(len(screen)), [str(u) for u in screen["unit"]], rotate=-35)
    base = float(np.mean(base_screen))
    a.hline(base, GREY, "4 3", f"base arm (DNp01 only) {base:.1f}")
    a.hline(base / 2, RED, "2 3", f"screen bar: half of base {base / 2:.1f}")
    for i, row in screen.iterrows():
        colour = RED if row["passes"] else BLUE
        a.bar(i, 0.6, 0, row["mean"], colour, 0.35)
        for s in _counts(row["counts"]):
            a.dot(i, s, colour, 2)
    b = Panel(
        700,
        40,
        250,
        220,
        (-0.6, len(confirm) - 0.4),
        (0, top),
        f"Confirmation, fresh seeds {confirm_seeds}",
    )
    b.frame(range(len(confirm)), [str(u) for u in confirm["unit"]])
    base_c = float(np.mean(base_confirm))
    b.hline(base_c, GREY, "4 3", f"base arm {base_c:.1f}")
    for i, row in confirm.reset_index(drop=True).iterrows():
        b.bar(i, 0.5, 0, row["null_mean"], GREY, 0.35)
        for s in _counts(row["counts"]):
            b.dot(i, s, RED, 2.5)
        b.text(
            b.X(i),
            b.Y(row["null_mean"]) - 4,
            f"null mean {row['null_mean']:.2f}",
            GREY,
            "middle",
        )
        b.text(b.X(i), b.Y(0) - 8, f"p {row['p']:.3f}", RED, "middle")
    b.text(
        b.x0,
        b.y0 + b.h + 30,
        "red dots: observed per seed; grey bar: matched null",
        GREY,
    )
    named = (
        list(confirm.loc[confirm["names_partner"], "unit"])
        if "names_partner" in confirm
        else []
    )
    verdict = f"names_partner {', '.join(named)}" if named else "none"
    return document(
        980,
        340,
        f"Residual TTMn_R partner scan v{version} (model, LC4_R 100 Hz, "
        f"both DNp01 silenced): verdict {verdict}",
        [a, b],
    )


def partner_followup(
    left: pd.DataFrame,
    left_base: Sequence[float],
    drive: pd.DataFrame,
    null_draws: pd.DataFrame,
    pair_p: float,
    bar: int,
    verdicts: tuple[str, str],
    seeds: str,
) -> str:
    """Left: TTMn_L spikes with DNp01 and each named unit silenced, against the base arm
    and the matched null mean. Drive: TTMn_R spikes per seed with DNp02_R, DNp06_R or the
    pair driven, against the jump bit. Null: the mean count of every matched-pair draw, with
    the observed pair mean."""
    counts = [c for cell in left["counts"] for c in _counts(cell)] if len(left) else []
    top_l = max(4.0, max(left_base) + 1, *(counts or [0]), *left.get("null_mean", []))
    a = Panel(
        60,
        40,
        250,
        220,
        (-0.6, len(left) - 0.4 if len(left) else 0.6),
        (0, top_l),
        f"Left mirror (LC4_L → TTMn_L), seeds {seeds}",
        ylabel="spikes in 300 ms",
    )
    a.frame(range(len(left)), [str(u) for u in left["unit"]])
    base = float(np.mean(left_base))
    a.hline(base, GREY, "4 3", f"base arm {base:.1f}")
    for i, row in left.reset_index(drop=True).iterrows():
        a.bar(i, 0.5, 0, row["null_mean"], GREY, 0.35)
        for c in _counts(row["counts"]):
            a.dot(i, c, RED, 2.5)
        a.text(a.X(i), a.Y(0) - 8, f"p {row['p']:.3f}", RED, "middle")
    a.text(a.x0, a.y0 + a.h + 30, f"verdict: {verdicts[0]}", "#222")

    arm_counts = [c for cell in drive["counts"] for c in _counts(cell)]
    top_d = max(bar + 2.0, *arm_counts)
    b = Panel(
        380,
        40,
        250,
        220,
        (-0.6, len(drive) - 0.4),
        (0, top_d),
        f"Direct drive, 200 Hz, seeds {seeds}",
    )
    b.frame(range(len(drive)), [str(x) for x in drive["arm"]])
    b.hline(bar, RED, "2 3", f"jump bit {bar}")
    for i, row in drive.reset_index(drop=True).iterrows():
        for c in _counts(row["counts"]):
            b.dot(i, c, BLUE, 2.5)
    b.text(b.x0, b.y0 + b.h + 30, f"verdict: {verdicts[1]}", "#222")

    pair = null_draws.loc[null_draws["part"] == "drive", "mean_count"].to_numpy()
    observed = float(
        np.mean(_counts(drive.loc[drive["arm"] == "pair", "counts"].iloc[0]))
    )
    hi = max(float(pair.max()) if pair.size else 0.0, observed) + 1
    edges = np.linspace(0, hi, 21)
    hist, _ = np.histogram(pair, edges)
    c = Panel(
        700,
        40,
        250,
        220,
        (0, hi),
        (0, max(1, int(hist.max()))),
        f"Null: {pair.size} matched DN pairs driven",
        xlabel="mean TTMn_R spikes",
    )
    c.frame()
    width = edges[1] - edges[0]
    for x, h in zip(edges[:-1], hist, strict=True):
        if h:
            c.bar(x + width / 2, width * 0.9, 0, h, GREY, 0.6)
    c.out.append(
        f'<line x1="{c.X(observed):.1f}" x2="{c.X(observed):.1f}" y1="{c.y0}" '
        f'y2="{c.y0 + c.h}" stroke="{RED}" stroke-width="2"/>'
    )
    c.text(
        c.X(observed) - 4, c.y0 + 12, f"pair {observed:.1f}, p {pair_p:.3f}", RED, "end"
    )
    return document(
        980,
        340,
        "Residual partner follow-up v1 (model): left mirror with DNp01 + unit silenced; "
        "drive without LC4, DNp01 silenced",
        [a, b, c],
    )


def embodiment(intact: dict, silenced: dict, loop: dict) -> str:
    """M1 height with and without DNp01; M2 input rate, height and motor spikes per mode."""
    m_to_um = 1e6
    t1 = float(max(intact["time_ms"][-1], silenced["time_ms"][-1]))
    heights = [
        intact["height_m"],
        silenced["height_m"],
        *(loop[f"{m}_height_m"] for m in ("closed", "shuffled")),
    ]
    # an axis needs a span: 1 µm when no body leaves the ground
    hmax = max(1.0, max(float(np.max(h)) for h in heights) * m_to_um * 1.1)
    a = Panel(
        70,
        40,
        380,
        150,
        (0, t1),
        (0, hmax),
        "M1: jump body driven by TTMn_R (LC4_R 100 Hz)",
        "time (ms)",
        "height (µm)",
    )
    a.frame()
    a.line(intact["time_ms"], [h * m_to_um for h in intact["height_m"]], BLUE)
    a.line(silenced["time_ms"], [h * m_to_um for h in silenced["height_m"]], RED)
    a.legend(
        [
            (f"intact, takeoff {intact['takeoff_ms']:g} ms", BLUE),
            (f"DNp01 silenced, takeoff {silenced['takeoff_ms']:g} ms", RED),
        ],
        x=a.X(330),
        y=a.Y(hmax * 0.6),
    )
    t = loop["closed_t_ms"]
    modes = (
        ("closed", BLUE, ""),
        ("disconnected", GOLD, "5 3"),
        ("replay", GREEN, "1 3"),
        ("shuffled", RED, ""),
    )
    rmax = max(1.0, max(float(np.max(loop[f"{m}_rate_hz"])) for m, _, _ in modes) * 1.1)
    b = Panel(
        540,
        40,
        380,
        150,
        (0, float(t[-1])),
        (0, rmax),
        "M2: input rate (engineered transducer)",
        "time (ms)",
        "Hz",
    )
    b.frame()
    c = Panel(
        70,
        250,
        380,
        150,
        (0, float(t[-1])),
        (0, hmax),
        "M2: body height",
        "time (ms)",
        "height (µm)",
    )
    c.frame()
    smax = max(int(np.sum(loop[f"{m}_motor_spikes"])) for m, _, _ in modes) + 1
    d = Panel(
        540,
        250,
        380,
        150,
        (0, float(t[-1])),
        (0, smax),
        "M2: cumulative TTMn_R spikes",
        "time (ms)",
        "spikes",
    )
    d.frame()
    for m, colour, dash in modes:
        b.line(t, loop[f"{m}_rate_hz"], colour, 1.2, dash)
        c.line(t, loop[f"{m}_height_m"] * m_to_um, colour, 1.5, dash)
        d.line(t, np.cumsum(loop[f"{m}_motor_spikes"]), colour, 1.5, dash, step=True)
    d.legend([(m, colour) for m, colour, _ in modes], x=d.x0 + 8)
    c.text(
        c.x0,
        c.y0 + c.h + 44,
        "closed, disconnected and replay coincide: the disc is centimetres away, so a "
        "body moving microns does not change the input",
        GREY,
    )
    return document(
        960,
        470,
        "Embodiment M1/M2 (engineered decoder and transducer; "
        "not a behaviour of the fly)",
        [a, b, c, d],
    )


def kc_persistence(
    t_ms: np.ndarray, groups: dict[str, np.ndarray], stim_ms: float, note: str
) -> str:
    """Population rate over time per group, with the stimulus window shaded."""
    colours = [BLUE, RED, GREEN, GOLD, GREY]
    top = max(1.0, max(float(np.max(v)) for v in groups.values()) * 1.1)
    a = Panel(
        70,
        40,
        560,
        220,
        (0, float(t_ms[-1])),
        (0, top),
        "Mean rate per neuron of each group (10 ms bins)",
        "time (ms)",
        "Hz",
    )
    a.frame().vspan(0, stim_ms)
    a.text(a.X(stim_ms / 2), a.y0 + 12, "stimulus", GREY, "middle")
    for (label, v), colour in zip(groups.items(), colours, strict=False):
        a.line(t_ms, v, colour, 1.5, step=True)
    a.legend(
        [(k, c) for k, c in zip(groups, colours, strict=False)],
        x=a.x0 + a.w + 14,
        y=a.y0 + 12,
    )
    for k, part in enumerate(note.split("\n")):
        a.text(a.x0, a.y0 + a.h + 44 + 13 * k, part, GREY)
    return document(
        900,
        350,
        "Held-out ORN_DM1 case (exploratory diagnosis): activity "
        "outlasts the stimulus in the Kenyon cells",
        [a],
    )


def homology_pilot(pilot: pd.DataFrame) -> str:
    """LC4 share of each giant fiber's input and raw LC4 synapses, male against female."""
    rows = pilot.reset_index(drop=True)
    labels = [f"{r.dataset} {str(r.DNp01)[-1]}" for r in rows.itertuples()]
    colours = [BLUE if r.dataset == "male" else RED for r in rows.itertuples()]
    smax = float(rows["share_of_input"].max()) * 100 * 1.25
    a = Panel(
        70,
        40,
        360,
        200,
        (-0.6, len(rows) - 0.4),
        (0, smax),
        "LC4 share of the giant fiber's input",
        ylabel="% of input synapses",
    )
    a.frame(range(len(rows)), labels)
    synmax = float(rows["LC4_synapses"].max()) * 1.15
    b = Panel(
        520,
        40,
        360,
        200,
        (-0.6, len(rows) - 0.4),
        (0, synmax),
        "LC4 → DNp01 synapses: raw (bar), divided by density ratio (dot)",
        ylabel="synapses",
    )
    b.frame(range(len(rows)), labels)
    for i, r in rows.iterrows():
        a.bar(i, 0.6, 0, r["share_of_input"] * 100, colours[i], 0.6)
        a.text(
            a.X(i),
            a.Y(r["share_of_input"] * 100) - 4,
            f"{100 * r['share_of_input']:.1f}%",
            colours[i],
            "middle",
        )
        b.bar(i, 0.6, 0, r["LC4_synapses"], colours[i], 0.6)
        b.dot(i, r["density_scaled"], "#222", 3)
    ratio = float(rows["density_ratio"].iat[0])
    b.text(
        b.x0,
        b.y0 + b.h + 30,
        f"male/female synapse density ratio {ratio:.2f} (median over "
        f"{int(rows['ratio_types'].iat[0])} matched types)",
        GREY,
    )
    a.text(
        a.x0,
        a.y0 + a.h + 30,
        "a difference between reconstructions, not attributed to sex",
        GREY,
    )
    return document(
        920, 300, "Homology pilot (#29): LC4 → DNp01 in MaleCNS and FAFB", [a, b]
    )


def looming_jump(
    replay: dict, seeds: Sequence[int], dt_ms: float, drive_ms: float
) -> str:
    """TTMn_R spike raster of the one-bit loop per seed: closed loop up to the third spike,
    the open loop after it, and the DNp01-silenced arm. Times are neural steps × `dt_ms`."""
    rows = len(seeds) * 2
    a = Panel(
        110,
        84,
        760,
        30 * rows + 30,
        (0, drive_ms * 1.07),
        (rows + 0.3, -0.7),
        xlabel="time (ms)",
    )
    a.frame(yticks=())
    a.out.append(
        f'<line x1="{a.X(drive_ms):.1f}" x2="{a.X(drive_ms):.1f}" y1="{a.y0}" '
        f'y2="{a.y0 + a.h}" stroke="{GREY}" stroke-dasharray="4 3"/>'
    )
    a.text(a.X(drive_ms) - 4, a.y0 + a.h - 6, "drive ends", GREY, "end")

    def ticks_at(times, row, colour, width):
        y = a.Y(row)
        for t in times:
            x = a.X(t)
            a.out.append(
                f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y - 9:.1f}" y2="{y + 9:.1f}" '
                f'stroke="{colour}" stroke-width="{width}"/>'
            )

    for k, seed in enumerate(seeds):
        top, low = 2 * k + 0.4, 2 * k + 1.2
        closed = np.asarray(replay[f"seed{seed}_ttmn_closed"]) * dt_ms
        open_ = np.asarray(replay[f"seed{seed}_ttmn_open"]) * dt_ms
        silence = np.asarray(replay[f"seed{seed}_ttmn_silence"]) * dt_ms
        ticks_at(closed, top, "#111827", 2.5)
        ticks_at(open_[open_ > closed[-1]], top, "#4b5563", 1.2)
        ticks_at(silence, low, BLUE, 2.5)
        x = a.X(closed[-1])
        a.out.append(
            f'<path d="M{x - 5:.1f},{a.Y(top) - 18:.1f} h10 l-5,7 z" fill="#111827"/>'
        )
        a.text(a.x0 - 8, a.Y(top) + 4, f"seed {seed} open", "#222", "end")
        a.text(a.x0 - 8, a.Y(low) + 4, f"seed {seed} silence", "#222", "end")
    a.legend(
        [
            ("open loop, after the jump", "#4b5563"),
            ("closed loop, stops at the third spike (▼ jump)", "#111827"),
            ("both DNp01 silenced", BLUE),
        ],
        x=a.x0 + 20,
        y=40,
    )
    return document(
        900,
        a.y0 + a.h + 50,
        "TTMn_R spikes in the one-bit looming loop (behavior v1, LC4_R 100 Hz)",
        [a],
    )


def _pct(fraction: float) -> str:
    return f"{100 * float(fraction):.1f}%"


def kc_sparseness(rows: pd.DataFrame, silent_below: float) -> str:
    """Responding share and shared share for arms the results already name.

    `rows` is in display order and has version, arm, fraction_1 and shared_of_1.
    Both panels draw those columns for odor 1. The two odors are not averaged.
    A bar is grey when fraction_1 is below `silent_below` (the lock's sparse
    floor) and blue otherwise: the dense-or-silent split the text already states.
    """
    rows = rows.reset_index(drop=True)
    n = len(rows)
    labels = [f"{r.version} {r.arm}" for r in rows.itertuples()]
    height = 22 * n
    ylim = (n - 0.45, -0.55)
    a = Panel(
        108,
        36,
        280,
        height,
        (0, 118),
        ylim,
        "Responding, odor 1",
        xlabel="% of Kenyon cells",
    )
    b = Panel(
        468,
        36,
        280,
        height,
        (0, 118),
        ylim,
        "Shared by both odors, of odor 1",
        xlabel="% of odor-1 responders",
    )
    a.frame(xticks=[0, 25, 50, 75, 100], yticks=())
    b.frame(xticks=[0, 25, 50, 75, 100], yticks=())
    for i, r in rows.iterrows():
        respond = 100 * float(r["fraction_1"])
        shared = 100 * float(r["shared_of_1"])
        colour = GREY if float(r["fraction_1"]) < silent_below else BLUE
        a.hbar(i, 0.62, 0, respond, colour, 0.85)
        b.hbar(i, 0.62, 0, shared, colour, 0.85)
        a.text(a.X(respond) + 4, a.Y(i) + 3, _pct(r["fraction_1"]), colour)
        b.text(b.X(shared) + 4, b.Y(i) + 3, _pct(r["shared_of_1"]), colour)
        a.text(a.x0 - 8, a.Y(i) + 3, labels[i], "#222", "end")
    floor = f"{100 * silent_below:.0f}"
    a.text(
        a.x0,
        a.y0 + a.h + 48,
        f"Grey is below {floor}% of Kenyon cells, the lock's sparse floor: silent. "
        "Blue is dense.",
        GREY,
    )
    a.text(
        a.x0,
        a.y0 + a.h + 62,
        "Shared is the share of odor 1's responders. On a silent arm that is a "
        "handful of cells. Odor 2 is not averaged in.",
        GREY,
    )
    return document(
        780,
        a.y0 + a.h + 80,
        "Kenyon cell sparseness: dense, or silent",
        [a, b],
    )


def jump_range(seeds: Sequence[dict], lo_mm: float, hi_mm: float) -> str:
    """Drag-free range of each seed, on the axis of the published interval.

    `lo_mm` and `hi_mm` are the bounds the lock names (Zumstein et al.), not a
    number computed from the seeds. A short jump stays short on that axis, and
    each bar is labelled with its archived range. The times in the caption are
    the model's clock from stimulus onset, not a measured takeoff latency.
    """
    seeds = list(seeds)
    n = len(seeds)
    a = Panel(
        58,
        40,
        400,
        210,
        (-0.55, n - 0.45),
        (0, hi_mm * 1.08),
        "Drag-free range at takeoff",
        xlabel="seed",
        ylabel="mm",
    )
    band_top, band_bottom = sorted((a.Y(lo_mm), a.Y(hi_mm)))
    a.out.append(
        f'<rect x="{a.x0}" y="{band_top:.1f}" width="{a.w}" height="{band_bottom - band_top:.1f}" '
        f'fill="{GOLD}" fill-opacity="0.18"/>'
    )
    a.frame(range(n), [str(int(s["seed"])) for s in seeds])
    a.hline(lo_mm, GOLD, "4 3")
    a.hline(hi_mm, GOLD, "4 3")
    a.text(
        a.x0 + a.w - 4,
        a.Y((lo_mm + hi_mm) / 2) + 3,
        f"Zumstein et al. {lo_mm:g}-{hi_mm:g} mm",
        GOLD,
        "end",
    )
    for i, s in enumerate(seeds):
        mm = float(s["range_mm"])
        a.bar(i, 0.5, 0, mm, BLUE, 0.9)
        a.text(a.X(i), a.Y(mm) - 10, f"{mm:.2f}", BLUE, "middle")
    times = ", ".join(
        f"{int(s['seed'])} at {float(s['takeoff_ms']):.1f} ms" for s in seeds
    )
    a.text(
        a.x0,
        a.y0 + a.h + 46,
        "Model clock from stimulus onset, not a measured takeoff latency.",
        GREY,
    )
    a.text(a.x0, a.y0 + a.h + 60, f"{times}.", GREY)
    return document(
        520,
        a.y0 + a.h + 78,
        "NeuroMechFly jump v1: the drag-free range is short",
        [a],
    )


def t4_spikes(rows: pd.DataFrame) -> str:
    """T4 spikes per T4/T5 version 4 configuration, on a log axis.

    `rows` has lamina_medulla_gain, lmc_rate_hz, medulla_rate_hz and t4_spikes (the
    sum over T4a-d, every direction and polarity) in the lock's configuration order.
    Blue marks the configurations with LMC and medulla release at 200 Hz, the ones
    DN arena version 2 uses; a zero is drawn at the axis origin and labelled 0.
    """
    rows = rows.reset_index(drop=True)
    n = len(rows)
    top = float(np.ceil(np.log10(max(1.0, float(rows["t4_spikes"].max())))))
    a = Panel(
        260,
        52,
        420,
        20 * n,
        (0, top + 0.4),
        (n - 0.45, -0.55),
        "T4 spikes per configuration (all directions and polarities)",
        xlabel="spikes, log scale (0 at the origin)",
    )
    marks = list(range(int(top) + 1))
    a.frame(xticks=marks, xticklabels=[f"{10**m:,}" for m in marks], yticks=())
    for i, r in rows.iterrows():
        spikes = int(r["t4_spikes"])
        chosen = r["lmc_rate_hz"] == 200.0 and r["medulla_rate_hz"] == 200.0
        colour = BLUE if chosen else GREY
        x = float(np.log10(spikes)) if spikes else 0.0
        if spikes:
            a.hbar(i, 0.62, 0, x, colour, 0.85)
        a.text(a.X(x) + 4, a.Y(i) + 3, f"{spikes:,}", colour)
        label = (
            f"gain {r['lamina_medulla_gain']:g} · LMC {r['lmc_rate_hz']:g} Hz · "
            f"medulla {r['medulla_rate_hz']:g} Hz"
        )
        a.text(a.x0 - 8, a.Y(i) + 3, label, "#222", "end")
    a.text(
        a.x0,
        a.y0 + a.h + 48,
        "Blue: LMC and medulla release 200 Hz, the three configurations of DN arena "
        "version 2.",
        GREY,
    )
    a.text(
        a.x0,
        a.y0 + a.h + 62,
        "T4 is silent at every configuration with medulla release 50 Hz.",
        GREY,
    )
    return document(
        780,
        a.y0 + a.h + 80,
        "T4/T5 version 4: T4 fires only with medulla release at 200 Hz",
        [a],
    )


def dn_arena(rows: pd.DataFrame) -> str:
    """Intact heading change against each row's wiring-null range.

    `rows` draws version 1 cells first, then version 2 configurations. Every row
    has version ("v1" or "v2"), verdict ("uninformative", "null" or "difference"),
    intact, script, wiring_null_minimum, wiring_null_median and wiring_null_maximum
    (radians, 200–1,000 ms). A v1 row also has yaw_gain_deg_s_per_hz and
    forward_gain_mm_s_per_hz; a v2 row has lamina_medulla_gain. The grey bar runs
    from the wiring-null minimum to its maximum, with a tick at the median. The
    blue dot is intact, labelled to three decimal places; the hollow mark is the
    script control.
    """
    v1 = rows[rows["version"] == "v1"]
    v2 = rows[rows["version"] == "v2"]
    if len(v1) + len(v2) != len(rows):
        raise ValueError("version must be v1 or v2")
    rows = pd.concat([v1, v2], ignore_index=True)
    n = len(rows)
    cols = (
        "wiring_null_minimum",
        "wiring_null_median",
        "wiring_null_maximum",
        "intact",
        "script",
    )
    values = rows[list(cols)].to_numpy(dtype=float)
    lo, hi = float(values.min()), float(values.max())
    pad = (hi - lo) * 0.08
    if pad == 0.0:
        pad = 0.05
    x_lo, x_hi = lo - pad, hi + pad
    a = Panel(
        292,
        52,
        440,
        22 * n,
        (x_lo, x_hi),
        (n - 0.45, -0.55),
        xlabel="heading change, 200–1,000 ms (rad)",
    )
    a.frame(yticks=())
    if x_lo <= 0.0 <= x_hi:
        a.line([0.0, 0.0], [a.ylim[0], a.ylim[1]], GREY, 1.0, "4 3")
    for i, r in rows.iterrows():
        if r["version"] == "v1":
            label = (
                f"v1 · yaw {float(r['yaw_gain_deg_s_per_hz']):g} °/s/Hz · "
                f"fwd {float(r['forward_gain_mm_s_per_hz']):g} mm/s/Hz"
            )
        else:
            label = f"v2 · gain {float(r['lamina_medulla_gain']):g}"
        intact = float(r["intact"])
        a.hbar(
            i,
            0.48,
            float(r["wiring_null_minimum"]),
            float(r["wiring_null_maximum"]),
            GREY,
            0.35,
        )
        median = float(r["wiring_null_median"])
        a.line([median, median], [i - 0.34, i + 0.34], "#222", 1.4)
        a.ring(float(r["script"]), i, GREY)
        a.dot(intact, i, BLUE)
        a.text(a.X(intact) + 6, a.Y(i) + 3, f"{intact:.3f}", BLUE)
        a.text(a.x0 - 8, a.Y(i) + 3, label, "#222", "end")
        a.text(a.x0 + a.w + 8, a.Y(i) + 3, str(r["verdict"]), "#222")
    a.text(
        a.x0,
        a.y0 + a.h + 48,
        "Grey bar: 39 wiring-null shuffles (min to max, tick at median). "
        "Blue dot: intact. Hollow circle: script control (no connectome).",
        GREY,
    )
    a.text(
        a.x0,
        a.y0 + a.h + 62,
        "v1: Poisson photoreceptor drive; v2: graded kick-equivalent drive of "
        "T4/T5 version 4.",
        GREY,
    )
    return document(
        960,
        a.y0 + a.h + 80,
        "DN arena: intact heading change against 39 wiring nulls",
        [a],
    )
