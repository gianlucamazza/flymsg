// Resource admission cannot change anatomical representation. Full-resolution
// surfaces are admitted as a whole; compressed-size estimates are provisional.
export function selectFidelity(
  neurons,
  representation,
  budgetTris,
  trisPerByte,
) {
  if (!["surface", "skeleton"].includes(representation))
    throw new RangeError(
      "Explicit surface or skeleton representation required",
    );
  const result = {
    meshes: new Map(),
    skeletons: [],
    tris: 0,
    status: "ready",
    reasons: [],
  };
  if (representation === "skeleton") {
    result.skeletons = neurons.map((n) => n.key);
    return result;
  }
  for (const n of neurons) {
    if (!n.manifest) {
      result.reasons.push({
        neuron: n.key,
        reason: n.missing ? "source surface unavailable" : "loading manifest",
      });
      result.status = n.missing
        ? "unsupported"
        : result.status === "unsupported"
          ? "unsupported"
          : "loading";
      continue;
    }
    const fragments = [];
    n.manifest.lods[0].forEach((f, i) => {
      if (f.size > 0) {
        fragments.push({ lod: 0, i });
        result.tris += f.size * trisPerByte;
      }
    });
    if (!fragments.length) {
      result.status = "unsupported";
      result.reasons.push({
        neuron: n.key,
        reason: "no full-resolution surface fragments",
      });
    }
    result.meshes.set(n.key, fragments);
  }
  if (result.tris > budgetTris) {
    result.status = "unsupported";
    result.reasons.push({
      reason: "full-resolution surface estimate exceeds capacity",
      estimated_tris: result.tris,
      capacity_tris: budgetTris,
    });
  }
  if (result.status !== "ready") result.meshes.clear();
  return result;
}
