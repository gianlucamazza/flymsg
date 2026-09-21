// Level-of-detail selection for multi-resolution meshes, Neuroglancer style.
//
// Each LOD tiles the neuron with fragments on an octree: a fragment at lod l covers the eight
// fragments at lod l-1 whose position >> 1 equals its own. Starting from the coarsest LOD, a
// fragment is replaced by its children when its chunk looks larger than `detailPx` on screen.
// Neurons are then served in priority order until the triangle budget is spent; a neuron that
// no longer fits even at its coarsest LOD is drawn as its skeleton instead.

import { fragmentBounds } from "./precomputed.js";

/** Apparent size in pixels of an axis-aligned box seen from `view.eye`. */
export function projectedPx(box, view) {
  let d2 = 0,
    diag2 = 0;
  for (let a = 0; a < 3; a++) {
    const e = view.eye[a];
    const gap =
      e < box.min[a] ? box.min[a] - e : e > box.max[a] ? e - box.max[a] : 0;
    d2 += gap * gap;
    diag2 += (box.max[a] - box.min[a]) ** 2;
  }
  return d2 === 0
    ? Infinity
    : (Math.sqrt(diag2) / Math.sqrt(d2)) * view.pxPerUnit;
}

/** Fragments to draw for one manifest at a given detail threshold: [{lod, i}]. */
export function refine(manifest, view, detailPx, transform) {
  const index = manifest.lods.map(
    (lod) => new Map(lod.map((f, i) => [f.pos.join(","), i])),
  );
  const out = [];
  const visit = (l, i) => {
    const f = manifest.lods[l][i];
    if (
      l > 0 &&
      projectedPx(fragmentBounds(manifest, l, f.pos, transform), view) >
        detailPx
    ) {
      const kids = [];
      for (let dx = 0; dx < 2; dx++)
        for (let dy = 0; dy < 2; dy++)
          for (let dz = 0; dz < 2; dz++) {
            const k = index[l - 1].get(
              `${2 * f.pos[0] + dx},${2 * f.pos[1] + dy},${2 * f.pos[2] + dz}`,
            );
            if (k !== undefined) kids.push(k);
          }
      if (kids.length) {
        for (const k of kids) visit(l - 1, k);
        return;
      }
    }
    if (f.size > 0) out.push({ lod: l, i });
  };
  const top = manifest.lods.length - 1;
  manifest.lods[top].forEach((_, i) => visit(top, i));
  return out;
}

const bytesOf = (manifest, frags) =>
  frags.reduce((s, { lod, i }) => s + manifest.lods[lod][i].size, 0);

/**
 * Choose what to draw.
 * neurons: [{key, priority, manifest}] (manifest null while not yet loaded -> skeleton)
 * view: {eye: [x, y, z] in the mesh output space (nm), pxPerUnit: screenHeight / (2 tan(fov/2))}
 * opts: {detailPx, budgetTris, trisPerByte, transform}
 * Returns {meshes: Map(key -> [{lod, i}]), skeletons: [key], tris}.
 */
export function select(neurons, view, opts) {
  const meshes = new Map(),
    skeletons = [];
  let spent = 0;
  for (const n of [...neurons].sort((a, b) => b.priority - a.priority)) {
    if (!n.manifest) {
      skeletons.push(n.key);
      continue;
    }
    const levels = n.manifest.lods.length;
    let chosen = null;
    // coarsen step by step (x2 threshold per LOD) until the neuron fits; the last try is the
    // coarsest LOD everywhere
    for (let k = 0; k <= levels && !chosen; k++) {
      const px = k === levels ? Infinity : opts.detailPx * 2 ** k;
      const frags = refine(n.manifest, view, px, opts.transform);
      const tris = bytesOf(n.manifest, frags) * opts.trisPerByte;
      if (spent + tris <= opts.budgetTris) chosen = { frags, tris };
    }
    if (chosen) {
      meshes.set(n.key, chosen.frags);
      spent += chosen.tris;
    } else skeletons.push(n.key);
  }
  return { meshes, skeletons, tris: spent };
}
