// Shared admission policy for the original observer and immutable GPU pages.
// An optional absent export differs from an explicitly requested missing asset.
export function contextReadiness({
  catalogs,
  catalogErrors,
  shells,
  allNeuropils,
  somata,
}) {
  const selected = shells.filter((s) => s.visible);
  const required = new Set(
    allNeuropils ? Object.keys(catalogs) : selected.map((s) => s.region),
  );
  const somaSelected = somata.points ? somata.points.visible : somata.visible;
  const somaAbsent = somata.state === "absent" && !somata.requested;
  const somaReady = !somaSelected || somata.state === "ready" || somaAbsent;
  let error =
    [...required]
      .filter((region) => catalogs[region] === "error")
      .map(
        (region) => catalogErrors[region] ?? "Neuropil catalog unavailable",
      )[0] ??
    selected.find((s) => s.state === "error")?.error ??
    null;
  if (
    !error &&
    somaSelected &&
    (somata.state === "error" ||
      (somata.state === "absent" && somata.requested))
  )
    error = somata.error ?? "Requested soma context unavailable";
  return {
    ready:
      !error &&
      somaReady &&
      [...required].every((region) => catalogs[region] === "ready") &&
      selected.every((s) => s.state === "ready"),
    error,
    catalogs: { ...catalogs },
    somata: somata.state,
    selected_neuropils: selected.length,
    selected_somata: !!somaSelected,
  };
}
