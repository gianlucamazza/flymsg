import {
  sourceAnchors,
  compilePageLods,
  composePageLod,
} from "./certified-lods.js";
import { PrimitivePages, pageTransfers } from "./primitive-pages.js";

let builder, pending, sortCenter;
const catalogues = new Map();
let nextPage = 0,
  anchorMs = 0,
  packingMs = 0;
self.onmessage = ({ data }) => {
  try {
    if (data.kind === "bounded-compose") {
      const pages = data.pages.map(({ page, selection }) => {
        const catalogue = catalogues.get(page);
        if (!catalogue) throw Error("Unknown page generation");
        return { page, indices: composePageLod(catalogue, selection) };
      });
      self.postMessage(
        { id: data.id, pages },
        pages.map((p) => p.indices.buffer),
      );
      return;
    }
    if (data.kind === "start") {
      builder = new PrimitivePages(data.options);
      pending = null;
    } else if (data.kind === "source") {
      if (pending) throw new Error("Previous source has not drained");
      sortCenter = null;
      if (data.context) {
        const p = data.source.attributes.position.array;
        const min = [Infinity, Infinity, Infinity],
          max = [-Infinity, -Infinity, -Infinity];
        for (let i = 0; i < p.length; i++) {
          const axis = i % 3;
          min[axis] = Math.min(min[axis], p[i]);
          max[axis] = Math.max(max[axis], p[i]);
        }
        sortCenter = min.map((v, axis) => (v + max[axis]) / 2);
      }
      if (builder.preserveAnchors) {
        const started = performance.now();
        data.source.anchors = sourceAnchors(
          data.source.attributes.position.array.length / 3,
          data.source.index,
        );
        anchorMs += performance.now() - started;
      }
      pending = builder.append(data.source);
    }
    const packingStarted = performance.now();
    let page = null;
    if (data.kind === "finish") page = builder.flush();
    else if (pending) {
      const result = pending.next();
      if (result.done) pending = null;
      else page = result.value;
    }
    packingMs += performance.now() - packingStarted;
    if (page?.boundedSource) {
      const catalogue = compilePageLods(page);
      catalogue.metadata.preparation.source_anchor_ms = anchorMs;
      anchorMs = 0;
      catalogue.metadata.preparation.packing_ms = packingMs;
      packingMs = 0;
      const pageId = nextPage++;
      catalogues.set(pageId, catalogue);
      page.bounded = { ...catalogue.metadata, page: pageId };
    }
    self.postMessage(
      { id: data.id, page, pending: !!pending, sortCenter },
      page ? pageTransfers(page) : [],
    );
  } catch (error) {
    self.postMessage({ id: data.id, error: String(error) });
  }
};
