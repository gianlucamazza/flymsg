// Freeze the input pose before capture; never tolerate a changed output pose.
export function frozenCameraProfile(observed, frozen, identity) {
  const matrix = (profile, name) => {
    const values = profile?.[name];
    if (
      !Array.isArray(values) ||
      values.length !== 16 ||
      !values.every(Number.isFinite)
    )
      throw Error("Invalid oracle camera matrix");
    return [...values];
  };
  matrix(observed, "camera_world");
  matrix(observed, "projection");
  const viewport = Object.fromEntries(
    ["width", "height", "pixel_ratio", "samples"].map((k) => [
      k,
      identity?.[k],
    ]),
  );
  if (
    !Number.isInteger(viewport.width) ||
    viewport.width <= 0 ||
    !Number.isInteger(viewport.height) ||
    viewport.height <= 0 ||
    !Number.isFinite(viewport.pixel_ratio) ||
    viewport.pixel_ratio <= 0 ||
    !Number.isInteger(viewport.samples) ||
    viewport.samples < 0
  )
    throw Error("Invalid oracle viewport");
  if (
    frozen?.viewport &&
    Object.keys(viewport).some((k) => frozen.viewport[k] !== viewport[k])
  )
    throw Error("Frozen oracle viewport or quality changed");
  const selected = frozen ?? observed;
  return {
    camera_world: matrix(selected, "camera_world"),
    projection: matrix(selected, "projection"),
    viewport,
  };
}
