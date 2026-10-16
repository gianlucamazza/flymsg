import {
  projectionErrorBound,
  certifiedPixelError,
} from "./projection-error-bound.js";

// Own only alternate index buffers. Full geometry is always resident and drawable.
export class BoundedSelections {
  constructor(THREE, uploads, compose, precision) {
    Object.assign(this, { THREE, uploads, compose, precision });
    this.pages = [];
    this.epoch = 0;
    this.current = null;
    this.pending = null;
    this.inflight = false;
    this.error = null;
    this.initialized = false;
    this.desired = null;
    this.fallbackFrames = 0;
    this.coarseFrames = 0;
    this.discarded = 0;
    this.composedPages = this.reusedPages = this.installedSelections = 0;
  }
  add(page, metadata) {
    if (metadata.encoding !== "anchored-path-u32/v1")
      throw Error("Unknown bounded worker encoding");
    page.bounded = metadata;
    page.fullIndex = page.object.geometry.index;
    this.pages.push(page);
    this.preparation ??= {};
    for (const [name, value] of Object.entries(metadata.preparation ?? {}))
      this.preparation[name] = (this.preparation[name] ?? 0) + value;
    this.cachedEyeKey = null;
  }
  bounds(eyes) {
    return this.pages.map((page) =>
      Object.fromEntries(
        Object.entries(page.bounded.boxes).map(([owner, box]) => {
          const values = eyes?.length
            ? eyes.map((eye) => projectionErrorBound(box, eye, this.precision))
            : [];
          return [owner, values];
        }),
      ),
    );
  }
  errorFor(page, owner, level, bounds = []) {
    if (level === 0) return 0;
    const variant = page.bounded.levels.find((v) => v.id === level),
      error = variant?.errors[owner];
    if (error === undefined || !bounds.length) return Infinity;
    return Math.max(...bounds.map((b) => certifiedPixelError(error, b)));
  }
  valid(selection, bounds) {
    return this.pages.every((page, i) =>
      Object.keys(page.bounded.boxes).every((owner) => {
        const level = selection[page.bounded.page]?.[owner];
        return (
          Number.isInteger(level) &&
          this.errorFor(page, owner, level, bounds[i][owner]) <= 0.5
        );
      }),
    );
  }
  choose(bounds) {
    const selection = {};
    this.pages.forEach((page, i) => {
      const owners = {};
      selection[page.bounded.page] = owners;
      for (const owner of Object.keys(page.bounded.boxes)) {
        const full = page.bounded.levels[0].ranges
          .filter((r) => r.owner === Number(owner))
          .reduce((n, r) => n + r.count, 0);
        let best = 0,
          count = full;
        for (const variant of page.bounded.levels) {
          const size = variant.ranges
            .filter((r) => r.owner === Number(owner))
            .reduce((n, r) => n + r.count, 0);
          if (
            size < count &&
            this.errorFor(page, owner, variant.id, bounds[i][owner]) <= 0.4
          ) {
            best = variant.id;
            count = size;
          }
        }
        // Prefer fewer indices, but do not refine a still-certified current
        // path merely because it crossed the 0.4-pixel preparation threshold.
        const retained = this.current?.records.has(page.bounded.page)
          ? this.current.selection[page.bounded.page]?.[owner]
          : undefined;
        if (
          Number.isInteger(retained) &&
          this.errorFor(page, owner, retained, bounds[i][owner]) <= 0.5
        ) {
          const retainedCount = page.bounded.levels
            .find((v) => v.id === retained)
            .ranges.filter((r) => r.owner === Number(owner))
            .reduce((n, r) => n + r.count, 0);
          if (retainedCount <= count) best = retained;
        }
        owners[owner] = best;
      }
    });
    return selection;
  }
  release(candidate, retained = null) {
    const shared = new Set(retained?.records.values());
    if (candidate)
      for (const record of candidate.records.values())
        if (!shared.has(record)) this.uploads.release(record);
  }
  reset() {
    this.epoch++;
    this.release(this.current, this.pending);
    this.release(this.pending);
    this.current = this.pending = this.desired = null;
    this.inflight = false;
    this.pages = [];
    this.preparation = {};
    this.workerComposeMs = null;
    this.error = null;
    this.initialized = false;
    this.cachedEyeKey = null;
    this.cachedBounds = null;
    this.selectionEyeKey = null;
    this.cachedSelection = null;
  }
  update(eyes) {
    const eyeKey = JSON.stringify(eyes);
    const bounds =
      eyeKey === this.cachedEyeKey ? this.cachedBounds : this.bounds(eyes);
    this.cachedEyeKey = eyeKey;
    this.cachedBounds = bounds;
    if (this.uploads.error) this.error = this.uploads.error;
    if (this.pending) {
      // A changed preference is not a failed proof. Keep uploading while the
      // actual pose still certifies the complete pending selection.
      if (this.uploads.error || !this.valid(this.pending.selection, bounds)) {
        this.release(this.pending, this.current);
        this.pending = null;
        this.discarded++;
      } else if (
        [...this.pending.records.values()].every((r) => r.state === "ready")
      ) {
        for (const record of this.pending.records.values()) record.arrays = [];
        this.release(this.current, this.pending);
        this.current = this.pending;
        this.pending = null;
        this.installedSelections++;
        this.initialized = true;
        this.selectionEyeKey = null;
      }
    }
    const selection =
        eyeKey === this.selectionEyeKey
          ? this.cachedSelection
          : this.choose(bounds),
      key = JSON.stringify(selection);
    this.selectionEyeKey = eyeKey;
    this.cachedSelection = selection;
    this.desired = { key, selection };
    const coarse = Object.values(selection).some((owners) =>
      Object.values(owners).some((level) => level !== 0),
    );
    if (!coarse) {
      this.release(this.current, this.pending);
      if (this.current) this.selectionEyeKey = null;
      this.current = null;
      this.initialized = true;
      return;
    }
    if (
      this.error ||
      this.inflight ||
      this.pending ||
      this.current?.key === key
    )
      return;
    const epoch = this.epoch;
    this.inflight = true;
    const pages = this.pages
      .filter((page) =>
        Object.values(selection[page.bounded.page]).some((n) => n !== 0),
      )
      .map((page) => ({
        page: page.bounded.page,
        selection: selection[page.bounded.page],
      }));
    this.compose(pages)
      .then((response) => {
        if (epoch !== this.epoch) return;
        this.inflight = false;
        this.workerComposeMs = response.compose_ms ?? null;
        if (!this.valid(selection, this.cachedBounds)) {
          this.discarded++;
          return;
        }
        const records = new Map();
        try {
          if (
            response.pages.length !== pages.length ||
            new Set(response.pages.map((p) => p.page)).size !== pages.length
          )
            throw Error("Incomplete bounded composition");
          this.composedPages += response.pages.length;
          for (const page of response.pages) {
            const source = this.pages.find((p) => p.bounded.page === page.page);
            if (
              !source ||
              !pages.some((p) => p.page === page.page) ||
              !(page.indices instanceof Uint32Array) ||
              page.indices.length > source.fullIndex.count
            )
              throw Error("Invalid bounded index result");
            const expected = Object.entries(selection[page.page]).reduce(
              (sum, [owner, level]) =>
                sum +
                source.bounded.levels
                  .find((v) => v.id === level)
                  .ranges.filter((r) => r.owner === Number(owner))
                  .reduce((n, r) => n + r.count, 0),
              0,
            );
            if (page.indices.length !== expected)
              throw Error(
                "Bounded composition count differs from certified selection",
              );
            if (!page.indices.length)
              throw Error("Empty bounded source composition");
            // Reuse only ready indices for the identical certified page
            // selection. Re-evaluate ownership after the asynchronous reply;
            // no current GPU record is captured across worker execution.
            const current = this.current?.records.get(page.page),
              reused =
                current?.state === "ready" &&
                JSON.stringify(this.current.selection[page.page]) ===
                  JSON.stringify(selection[page.page]);
            if (reused) this.reusedPages++;
            records.set(
              page.page,
              reused
                ? current
                : this.uploads.enqueue([page.indices], { indexSlot: 0 }),
            );
          }
          this.pending = { key, selection, records };
        } catch (error) {
          this.release({ records }, this.current);
          this.error = String(error);
        }
      })
      .catch((error) => {
        if (epoch === this.epoch) {
          this.inflight = false;
          this.error = String(error);
        }
      });
  }
  apply(eyes) {
    const eyeKey = JSON.stringify(eyes);
    const bounds =
      eyeKey === this.cachedEyeKey ? this.cachedBounds : this.bounds(eyes);
    let maximum = 0,
      submitted = 0,
      full = 0,
      coarse = 0,
      fallback = 0;
    this.pages.forEach((page, i) => {
      const selection = this.current?.selection[page.bounded.page],
        record = this.current?.records.get(page.bounded.page);
      let valid = !!record && !this.error,
        error = 0;
      if (valid)
        for (const [owner, level] of Object.entries(selection)) {
          const bound = this.errorFor(page, owner, level, bounds[i][owner]);
          error = Math.max(error, bound);
          if (!(bound <= 0.5)) valid = false;
        }
      if (valid) {
        record.attribute ??= new this.THREE.GLBufferAttribute(
          record.buffers[0].buffer,
          this.uploads.gl.UNSIGNED_INT,
          1,
          4,
          record.buffers[0].bytes / 4,
        );
        page.object.geometry.setIndex(record.attribute);
        maximum = Math.max(maximum, error);
        if (page.object.visible) coarse++;
      } else {
        page.object.geometry.setIndex(page.fullIndex);
        if (record) fallback++;
      }
      if (page.object.visible) {
        submitted += page.object.geometry.index.count;
        full += page.fullIndex.count;
      }
    });
    if (fallback) this.fallbackFrames++;
    if (coarse) this.coarseFrames++;
    this.last = {
      maximum_error_px: maximum,
      submitted_indices: submitted,
      source_indices: full,
      fallback_pages: fallback,
      coarse_pages: coarse,
    };
  }
  restore() {
    for (const page of this.pages)
      page.object.geometry.setIndex(page.fullIndex);
  }
  settled() {
    return !this.inflight && !this.pending && this.initialized;
  }
  report() {
    return {
      initialized: this.initialized,
      worker_preparation_ms: this.preparation,
      worker_compose_ms: this.workerComposeMs ?? null,
      state: this.error
        ? "fallback-full"
        : this.inflight || this.pending
          ? "preparing"
          : this.current
            ? "ready"
            : "fallback-full",
      error: this.error,
      ...this.last,
      coarse_frames: this.coarseFrames,
      fallback_frames: this.fallbackFrames,
      discarded_requests: this.discarded,
      composed_pages: this.composedPages,
      reused_pages: this.reusedPages,
      installed_selections: this.installedSelections,
      source_provenance_cpu_bytes: this.pages.reduce(
        (n, p) =>
          n +
          (p.boundedSource?.anchors.byteLength ?? 0) +
          (p.boundedSource?.origins.byteLength ?? 0),
        0,
      ),
      worker_index_bytes: this.pages.reduce(
        (n, p) => n + p.bounded.cpu_index_bytes,
        0,
      ),
    };
  }
}
