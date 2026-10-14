// Optional, read-only immersive observation of exported FlyMSG scenes.
// WebXR is a display transport, never a sensory or motor input to the neural engine.
// This module owns session/UI lifecycle; three.js owns stereo rendering.
export function xrRequested(search) {
  return new URLSearchParams(search).get("xr") === "1";
}

export function xrScaleForExtent(extentUm, displayWidthM = 1.2) {
  if (!Number.isFinite(extentUm) || extentUm <= 0)
    throw new RangeError(
      "XR requires a finite, positive scene extent in micrometres",
    );
  if (!Number.isFinite(displayWidthM) || displayWidthM <= 0)
    throw new RangeError(
      "XR requires a finite, positive display width in metres",
    );
  return displayWidthM / extentUm;
}

/**
 * Install a user-activated immersive-VR observer. Ordinary pages never call this.
 * No independent render loop, duplicate renderer, or simulation coupling is created.
 *
 * The scene origin is the centre of the exported anatomy (in micrometres).
 * During XR only, the root is displayed ~1.2 m wide, 2 m in front of the
 * viewer's initial `local` reference space origin. On session end the root, the
 * desktop camera (three.js writes the headset pose and field of view into it) and
 * the orbit controls are restored to their state when the session started.
 *
 * The caller must render with renderer.render(world, camera) when presenting,
 * not the desktop-only postprocessing composer.
 */
export async function installXrObserver({
  search,
  renderer,
  root,
  camera,
  controls,
  extentUm,
  documentRef = document,
  xrSystem = navigator.xr,
  onTransition = () => {},
}) {
  if (!xrRequested(search))
    return { available: false, reason: "not-requested" };

  const container = documentRef.createElement("aside");
  container.id = "xr-observer";
  container.setAttribute("aria-label", "Optional immersive anatomy viewer");
  const button = documentRef.createElement("button");
  button.type = "button";
  button.textContent = "Enter VR";
  button.hidden = true;
  const status = documentRef.createElement("span");
  status.setAttribute("role", "status");
  status.textContent = "Checking immersive VR support…";
  container.append(button, status);
  documentRef.body.appendChild(container);

  const unavailable = (reason) => {
    status.textContent = reason;
    button.hidden = true;
    return { available: false, reason };
  };
  if (
    !xrSystem ||
    typeof xrSystem.isSessionSupported !== "function" ||
    typeof xrSystem.requestSession !== "function"
  )
    return unavailable("Immersive VR is not available in this browser.");

  let supported;
  try {
    supported = await xrSystem.isSessionSupported("immersive-vr");
  } catch {
    return unavailable("Cannot check immersive VR support in this browser.");
  }
  if (!supported)
    return unavailable("Immersive VR is unsupported on this device.");

  const scale = xrScaleForExtent(extentUm);
  renderer.xr.enabled = true;
  renderer.xr.setReferenceSpaceType("local");

  let original = null;
  let presenting = false;
  const enter = () => {
    if (presenting) return;
    presenting = true;
    original = {
      position: root.position.clone(),
      scale: root.scale.clone(),
      cameraPosition: camera.position.clone(),
      cameraQuaternion: camera.quaternion.clone(),
      cameraScale: camera.scale.clone(),
      fov: camera.fov,
      zoom: camera.zoom,
      near: camera.near,
      far: camera.far,
      target: controls.target.clone(),
      controlsEnabled: controls.enabled,
    };
    root.position.set(0, 0, -2);
    root.scale.setScalar(scale);
    controls.enabled = false;
    camera.near = 0.05; // metres in the WebXR scene
    camera.far = 20;
    camera.updateProjectionMatrix();
    button.textContent = "Exit VR";
    status.textContent =
      "Immersive replay observer · no live neural simulation";
    onTransition();
  };
  const exit = () => {
    if (!presenting) return;
    presenting = false;
    root.position.copy(original.position);
    root.scale.copy(original.scale);
    camera.position.copy(original.cameraPosition);
    camera.quaternion.copy(original.cameraQuaternion);
    camera.scale.copy(original.cameraScale);
    camera.fov = original.fov;
    camera.zoom = original.zoom;
    camera.near = original.near;
    camera.far = original.far;
    camera.updateProjectionMatrix();
    controls.target.copy(original.target);
    controls.enabled = original.controlsEnabled;
    controls.update();
    button.textContent = "Enter VR";
    status.textContent = "Immersive observation available";
    onTransition();
  };
  renderer.xr.addEventListener("sessionstart", enter);
  renderer.xr.addEventListener("sessionend", exit);
  button.hidden = false;
  status.textContent = "Immersive observation available";

  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      const current = renderer.xr.getSession();
      if (current) {
        await current.end();
      } else {
        // requestSession needs the click's user activation: it is the first await on
        // this path
        const session = await xrSystem.requestSession("immersive-vr");
        try {
          await renderer.xr.setSession(session);
        } catch (error) {
          await session.end().catch(() => {});
          throw error;
        }
      }
    } catch {
      status.textContent =
        "VR session failed; the desktop viewer is unchanged.";
    } finally {
      button.disabled = false;
    }
  });
  return { available: true, button, status };
}
