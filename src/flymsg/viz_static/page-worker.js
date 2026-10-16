import { PrimitivePages, pageTransfers } from "./primitive-pages.js";

let builder, pending, sortCenter;
self.onmessage = ({ data }) => {
  try {
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
      pending = builder.append(data.source);
    }
    let page = null;
    if (data.kind === "finish") page = builder.flush();
    else if (pending) {
      const result = pending.next();
      if (result.done) pending = null;
      else page = result.value;
    }
    self.postMessage(
      { id: data.id, page, pending: !!pending, sortCenter },
      page ? pageTransfers(page) : [],
    );
  } catch (error) {
    self.postMessage({ id: data.id, error: String(error) });
  }
};
