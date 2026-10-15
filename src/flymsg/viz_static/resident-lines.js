// Original-order index residency using public BufferGeometry groups. Bridging
// conservatively culled gaps trades GPU work for a bounded number of draws;
// hidden neurons are hard barriers and can NEVER be bridged.
export class ResidentLineIndex {
  constructor(maxDraws = 8) {
    if (!Number.isInteger(maxDraws) || maxDraws < 1)
      throw new RangeError("Positive draw limit required");
    this.maxDraws = maxDraws;
    this.entries = [];
    this.index = new Uint32Array(0);
    this.count = 0;
    this.starts = this.ends = this.blocks = new Uint32Array(0);
    this.builds = 0;
    this.ranges = [];
  }

  sync(neurons, target = null) {
    const ready = neurons.filter((n) => n.skelLod);
    if (
      ready.length === this.entries.length &&
      ready.every((n, i) => {
        const e = this.entries[i];
        return (
          e.neuron === n &&
          e.edges === n.skelLod.levels[0] &&
          e.base === n.skelBase
        );
      })
    ) {
      if (target && target !== this.index) {
        this.writeIndex(target);
        return true;
      }
      return false;
    }
    let count = 0,
      runs = 0;
    this.entries = ready.map((n) => {
      const edges = n.skelLod.levels[0],
        pages = n.skelLod.pages[0];
      const entry = {
        neuron: n,
        edges,
        pages,
        base: n.skelBase,
        start: count,
        visible: new Uint8Array(pages.sizes.length),
      };
      count += edges.length;
      runs += pages.runs.length / 3;
      return entry;
    });
    this.count = count;
    this.writeIndex(target ?? new Uint32Array(count));
    // Persistent scratch; no allocation proportional to edge count on movement.
    this.starts = new Uint32Array(runs);
    this.ends = new Uint32Array(runs);
    this.blocks = new Uint32Array(runs);
    this.builds++;
    return true;
  }

  writeIndex(target) {
    if (target.length < this.count)
      throw new RangeError("Resident index capacity exhausted");
    this.index = target;
    for (const e of this.entries)
      for (let i = 0; i < e.edges.length; i++)
        target[e.start + i] = e.base + e.edges[i];
  }

  releaseArena() {
    this.index = new Uint32Array(0); // the viewer owns arena replacement/disposal
  }

  plan(eyes, wanted, visibility) {
    let count = 0,
      block = 0,
      visibleIndices = 0;
    const append = (start, end) => {
      if (
        count &&
        this.blocks[count - 1] === block &&
        this.ends[count - 1] === start
      )
        this.ends[count - 1] = end;
      else {
        this.starts[count] = start;
        this.ends[count] = end;
        this.blocks[count++] = block;
      }
    };
    for (const e of this.entries) {
      if (!wanted(e.neuron)) {
        if (e.edges.length) block++;
        continue;
      }
      const result = visibility(e.pages, eyes, e.visible);
      visibleIndices += 2 * result.edges;
      if (!result.edges) continue;
      if (result.edges * 2 === e.edges.length) {
        append(e.start, e.start + e.edges.length);
        continue;
      }
      const runs = e.pages.runs;
      for (let i = 0; i < runs.length; i += 3) {
        if (!e.visible[runs[i]]) continue;
        const start = e.start + 2 * runs[i + 1],
          end = start + 2 * runs[i + 2];
        append(start, end);
      }
    }
    let mandatory = count ? 1 : 0;
    for (let i = 1; i < count; i++)
      if (this.blocks[i] !== this.blocks[i - 1]) mandatory++;
    if (mandatory > this.maxDraws)
      return {
        fallback: "hidden-neuron draw limit",
        visibleIndices,
        ranges: [],
      };
    // Keep the largest optional gaps. All remaining gaps contain ONLY pages
    // rejected by both eye frusta. Source order and depth ties are unchanged.
    const splits = [],
      capacity = this.maxDraws - mandatory;
    for (let i = 1; i < count && capacity; i++) {
      if (this.blocks[i] !== this.blocks[i - 1]) continue;
      const gap = this.starts[i] - this.ends[i - 1];
      let at = 0;
      while (at < splits.length && splits[at].gap >= gap) at++;
      if (at < capacity) {
        splits.splice(at, 0, { i, gap });
        if (splits.length > capacity) splits.pop();
      }
    }
    const cut = new Set(splits.map((s) => s.i));
    const ranges = [];
    let start = count ? this.starts[0] : 0;
    for (let i = 1; i <= count; i++) {
      if (i === count || this.blocks[i] !== this.blocks[i - 1] || cut.has(i)) {
        ranges.push({ start, count: this.ends[i - 1] - start });
        start = this.starts[i];
      }
    }
    const changed =
      ranges.length !== this.ranges.length ||
      ranges.some(
        (r, i) =>
          r.start !== this.ranges[i].start || r.count !== this.ranges[i].count,
      );
    this.ranges = ranges;
    return {
      ranges,
      changed,
      visibleIndices,
      submittedIndices: ranges.reduce((sum, r) => sum + r.count, 0),
      fallback: null,
    };
  }

  arrays() {
    return [
      this.index,
      this.starts,
      this.ends,
      this.blocks,
      ...this.entries.map((e) => e.visible),
    ];
  }
}
