"""Serve this checkout to one explicitly selected Quest 2 and persist XR evidence.

uv run python scripts/quest_xr.py --serial SERIAL [--scene looming] [--seconds 1800]
The user enters VR and performs head motion/menu tests. This does not fake user activation
or declare hardware qualified. No adb server restart, package installation or /etc writes.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from flymsg import manifest, pages, runstore


def adb(serial, *args):
    return subprocess.check_output(
        ["adb", "-s", serial, *args], text=True, timeout=20
    ).strip()


def snapshot(serial, *, light=False):
    out = {"at": datetime.now(UTC).isoformat()}
    commands = {
        "power": ("shell", "dumpsys", "power"),
        "battery": ("shell", "dumpsys", "battery"),
        "thermal": ("shell", "dumpsys", "thermalservice"),
        "browser_memory": ("shell", "dumpsys", "meminfo", "com.oculus.browser"),
    }
    if light:
        commands = {
            key: args for key, args in commands.items() if key in ("power", "battery")
        }
    for key, args in commands.items():
        try:
            out[key] = adb(serial, *args)
        except (OSError, subprocess.SubprocessError) as exc:
            out[key] = {"unavailable": str(exc)}
    return out


def wifi_serial(value):
    """An explicit TCP transport, never an automatic USB fallback."""
    host, sep, port = value.rpartition(":")
    try:
        ipaddress.ip_address(host.strip("[]"))
        if not sep or not 1 <= int(port) <= 65535:
            raise ValueError
    except ValueError as exc:
        raise argparse.ArgumentTypeError("explicit Wi-Fi IP:port required") from exc
    return value


def native_focus(serial):
    raw = adb(serial, "shell", "dumpsys", "window")
    components = re.findall(r"mCurrentFocus=Window\{[^}\n]*\s([\w.]+/[^\s}]+)\}", raw)
    return {
        "components": components,
        "browser_focused": bool(components)
        and all(value.startswith("com.oculus.browser/") for value in components),
    }


def bounded_xr_certificate(doc, expected=None):
    """Independently check final per-frame geometric receipts, not timing or comfort."""
    fields = [
        "maximum_error_px",
        "submitted_indices",
        "source_indices",
        "fallback_pages",
        "coarse_pages",
        "invalid",
    ]
    content, bounded = doc.get("content"), doc.get("bounded")
    if not isinstance(content, dict) or not isinstance(bounded, dict):
        return {"status": "fail", "reason": "missing bounded content certificate"}
    if doc.get("status") != "ended":
        return {"status": "pending", "reason": "final raw session required"}
    identity = content.get("identity")
    if (
        not isinstance(identity, dict)
        or identity.get("representation") != "skeleton-bounded"
        or (expected is not None and identity != expected)
    ):
        return {"status": "fail", "reason": "content identity mismatch"}
    frames, rows = doc.get("frames"), doc.get("raw_bounded_frames")
    if (
        type(frames) is not int
        or frames < 1
        or not isinstance(rows, list)
        or len(rows) != frames
        or bounded.get("fields") != fields
    ):
        return {"status": "fail", "reason": "incomplete bounded frame sequence"}
    maximum, fallback = 0.0, 0
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            return {"status": "fail", "reason": "malformed bounded frame"}
        error, submitted, source, fallback_pages, _coarse_pages, invalid = row
        if (
            type(error) not in (int, float)
            or not math.isfinite(error)
            or not 0 <= error <= 0.5
            or any(type(value) is not int or value < 0 for value in row[1:])
            or submitted > source
            or invalid != 0
        ):
            return {"status": "fail", "reason": "uncertified bounded frame"}
        maximum = max(maximum, error)
        fallback += fallback_pages > 0
    if (
        content.get("checked_frames") != frames
        or content.get("incomplete_frames") != 0
        or bounded.get("checked_frames") != frames
        or bounded.get("uncertified_frames") != 0
    ):
        return {"status": "fail", "reason": "frame summary mismatch"}
    return {
        "status": "pass",
        "checked_frames": frames,
        "maximum_error_px": maximum,
        "fallback_frames": fallback,
        "qualification": "geometry only; timing and human acceptance remain separate",
    }


def identity(serial, expected=None):
    model = adb(serial, "shell", "getprop", "ro.product.model")
    if model != "Quest 2":
        raise ValueError(f"selected device is {model!r}, not Quest 2")
    hardware = adb(serial, "shell", "getprop", "ro.serialno")
    if not hardware or (expected is not None and hardware != expected):
        raise ValueError("Quest hardware identity changed or unavailable")
    return {
        "model": model,
        "hardware_serial": hardware,
        "transport": serial,
        "adb_server_port": os.environ.get("ANDROID_ADB_SERVER_PORT", "5037"),
    }


@contextmanager
def browser_endpoint(serial):
    sockets = adb(serial, "shell", "cat", "/proc/net/unix")
    names = {
        line.split()[-1][1:]
        for line in sockets.splitlines()
        if "@chrome_devtools_remote" in line
    }
    if len(names) != 1:
        raise RuntimeError("one Quest Browser diagnostic socket required")
    port = adb(serial, "forward", "tcp:0", f"localabstract:{names.pop()}")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        adb(serial, "forward", "--remove", f"tcp:{port}")


def node_json(script, *args, timeout=45):
    result = subprocess.run(
        ["node", str(Path(__file__).with_name(script)), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if not result.stdout.strip():
        raise RuntimeError(f"{script} unavailable: {result.stderr.strip()[:1000]}")
    return json.loads(result.stdout), result.returncode


def browser_preflight(
    endpoint, url, *, verify_sources=True, target=None, readback_only=False
):
    if target is None:
        with urllib.request.urlopen(endpoint + "/json/list", timeout=10) as response:
            targets = json.load(response)
        matches = [item for item in targets if item.get("url") == url]
        if len(matches) != 1:
            raise RuntimeError("expected page URL is not the unique loaded target")
        target = matches[0]["id"]
    result, _ = node_json(
        "observer_preflight.mjs",
        endpoint,
        target,
        url,
        *([] if verify_sources else ["--health"]),
        *(["--readback-only"] if readback_only else []),
    )
    return result


def preflight(serial, url, *, verify_sources=True):
    state = snapshot(serial)
    result = {"device": state, "eligible": False, "reasons": []}
    if "mWakefulness=Awake" not in str(state["power"]):
        result["reasons"].append("headset-not-awake")
        return result
    try:
        state["native_focus"] = native_focus(serial)
        if not state["native_focus"]["browser_focused"]:
            result["reasons"].append("native-browser-not-focused")
            return result
        with browser_endpoint(serial) as endpoint:
            check = browser_preflight(endpoint, url, verify_sources=verify_sources)
            result.update(
                browser=check, eligible=check["eligible"], reasons=check["reasons"]
            )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result["eligible"] = False
        result["reasons"].append(str(exc))
    return result


def restore_keep_awake(serial, original, expected_hardware):
    identity(serial, expected_hardware)
    key = "stay_on_while_plugged_in"
    if original == "null":
        adb(serial, "shell", "settings", "delete", "global", key)
    else:
        adb(serial, "shell", "settings", "put", "global", key, original)
    if adb(serial, "shell", "settings", "get", "global", key) != original:
        raise RuntimeError("keep-awake restoration readback mismatch")


def cleanup_resources(serial, out, operations):
    """Every owned resource gets a cleanup attempt, even after another fails."""
    results = []
    for name, operation in operations:
        try:
            operation()
            results.append({"phase": name, "ok": True})
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
            KeyboardInterrupt,
        ) as exc:
            results.append({"phase": name, "ok": False, "error": str(exc)})
    report = {"ok": all(row["ok"] for row in results), "operations": results}
    runstore.atomic_json(out / "cleanup.json", report)
    return report


class EvidenceHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory, evidence, **kwargs):
        self.evidence = evidence
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path != "/__xr_evidence":
            return self.send_error(404)
        # Only this local server's same-origin viewer may append evidence.
        if self.headers.get("Origin") != f"http://localhost:{self.server.server_port}":
            return self.send_error(403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            # Final bounded sessions include every geometric receipt and raw interval.
            if not 0 < length <= 16_000_000:
                return self.send_error(413)
            doc = json.loads(self.rfile.read(length))
            if not isinstance(doc, dict) or doc.get("schema") != "flymsg.xr-bench/v1":
                return self.send_error(400)
            entry = {
                "received_at": datetime.now(UTC).isoformat(),
                "report": doc,
                "eligible_document": bool(
                    getattr(self.server, "ready_document_id", None)
                )
                and doc.get("observer_document_id") == self.server.ready_document_id
                and not getattr(self.server, "unattended", False),
            }
            if getattr(self.server, "representation", None) == "skeleton-bounded":
                entry["bounded_geometry"] = bounded_xr_certificate(
                    doc, getattr(self.server, "ready_content", None)
                )
            with self.server.evidence_lock, self.evidence.open("ab") as stream:
                stream.write(runstore.canonical(entry) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        except (ValueError, TypeError):
            return self.send_error(400)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args):
        pass


def proximity_state(serial):
    raw = adb(serial, "shell", "dumpsys", "vrpowermanager")
    state = re.search(r"Virtual proximity state: (\w+)", raw)
    locks = re.findall(
        r"^(?:Mount|Unmounted|ForceUnmounted)WakeLock count: (\d+)$", raw, re.MULTILINE
    )
    if state is None or len(locks) != 3:
        raise RuntimeError("unrecognized Quest proximity state")
    return {"state": state[1], "locks": list(map(int, locks)), "raw": raw}


def restore_proximity(serial, hardware):
    identity(serial, hardware)
    adb(
        serial,
        "shell",
        "am",
        "broadcast",
        "-a",
        "com.oculus.vrpowermanager.automation_disable",
    )
    for _ in range(20):
        result = proximity_state(serial)
        if result["state"] == "DISABLED" and result["locks"] == [0, 0, 0]:
            return result
        time.sleep(0.25)
    raise RuntimeError("physical proximity restoration readback mismatch")


class QuestSite:
    """One clean frozen site and its owned Wi-Fi resources; no shared ADB restart."""

    def __init__(
        self,
        serial,
        out,
        *,
        port=8892,
        keep_awake=False,
        wifi_only=False,
        unattended=False,
    ):
        if wifi_only:
            wifi_serial(serial)
        self.serial, self.out, self.port = serial, Path(out), port
        self.keep_awake = keep_awake
        self.unattended = unattended
        self.operations = []
        self.target = None
        self.endpoint = None
        self.cleanup = None

    def record(self, name, value):
        runstore.atomic_json(self.out / name, value)

    def __enter__(self):
        self.device = identity(self.serial)
        self.source = manifest.git_info()
        if self.source["dirty"] is not False:
            raise ValueError("hardware evidence requires clean committed source")
        if not 1024 <= self.port <= 65535:
            raise ValueError("port must be between 1024 and 65535")
        self.out.mkdir(parents=True, exist_ok=False)
        try:
            self.record(
                "progress.json", {"phase": "build", "qualification": "not-scored"}
            )
            reverse = f"tcp:{self.port}"
            mappings = adb(self.serial, "reverse", "--list")
            if any(reverse in line.split() for line in mappings.splitlines()):
                raise RuntimeError("reverse port already mapped; choose another port")
            self.tmp = tempfile.TemporaryDirectory(prefix="flymsg-quest-")
            self.operations.append(("temporary-site", self.tmp.cleanup))
            site = Path(self.tmp.name) / "site"
            pages.build(site)
            if manifest.git_info() != self.source:
                raise ValueError("source changed while building the headset site")
            original = adb(
                self.serial,
                "shell",
                "settings",
                "get",
                "global",
                "stay_on_while_plugged_in",
            )
            self.device.update(
                source=self.source,
                site_sha256=runstore.digest(runstore.inventory(site)),
                original_stay_on=original,
                before=snapshot(self.serial),
                fingerprint=adb(
                    self.serial, "shell", "getprop", "ro.build.fingerprint"
                ),
                browser=adb(
                    self.serial, "shell", "dumpsys", "package", "com.oculus.browser"
                ),
            )
            self.record("device.json", self.device)
            self.device["measurement_profile"] = (
                "unattended-desktop-diagnostic"
                if self.unattended
                else "physical-presence"
            )
            self.device["normal_xr_qualification"] = False
            self.device["normal_xr_profile_eligible"] = not self.unattended
            if self.unattended:
                wifi_serial(self.serial)
                original_proximity = proximity_state(self.serial)
                self.record("proximity-before.json", original_proximity)
                if original_proximity["state"] != "DISABLED" or original_proximity[
                    "locks"
                ] != [0, 0, 0]:
                    raise RuntimeError(
                        "existing proximity override or wake lease; refusing to replace it"
                    )

                def restore():
                    self.record(
                        "proximity-restored.json",
                        restore_proximity(self.serial, self.device["hardware_serial"]),
                    )

                self.operations.append(("restore-proximity", restore))
                adb(
                    self.serial,
                    "shell",
                    "am",
                    "broadcast",
                    "-a",
                    "com.oculus.vrpowermanager.prox_close",
                )
                for _ in range(20):
                    active = proximity_state(self.serial)
                    if active["state"] == "CLOSE" and "mWakefulness=Awake" in adb(
                        self.serial, "shell", "dumpsys", "power"
                    ):
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError("virtual proximity did not wake headset")
                self.record("proximity-active.json", active)
            self.record("device.json", self.device)
            if self.keep_awake:
                if original != "null" and not original.isdigit():
                    raise ValueError("invalid original keep-awake setting")
                self.operations.append(
                    (
                        "restore-keep-awake",
                        lambda: restore_keep_awake(
                            self.serial, original, self.device["hardware_serial"]
                        ),
                    )
                )
                adb(self.serial, "shell", "svc", "power", "stayon", "true")
            handler = partial(
                EvidenceHandler,
                directory=str(site),
                evidence=self.out / "sessions.jsonl",
            )
            self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
            self.server.evidence_lock = threading.Lock()
            self.server.ready_document_id = None
            self.server.unattended = self.unattended
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            self.operations.append(("http-server", self.stop_server))
            adb(self.serial, "reverse", reverse, reverse)
            self.operations.append(
                (
                    "remove-owned-reverse",
                    lambda: adb(self.serial, "reverse", "--remove", reverse),
                )
            )
            self.operations.append(
                (
                    "final-device-snapshot",
                    lambda: self.record("after.json", snapshot(self.serial)),
                )
            )
            return self
        except BaseException as exc:
            self.record(
                "failure.json",
                {"phase": "setup", "error": str(exc), "qualification": "not-scored"},
            )
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()

    def close_page(self):
        targets = [self.target] if self.target else []
        if not targets and self.endpoint and getattr(self, "url", None):
            # Target creation can succeed even if bringing it forward fails or times out.
            # Recover ownership through our exact temporary site URL before removing CDP.
            with urllib.request.urlopen(
                self.endpoint + "/json/list", timeout=10
            ) as response:
                targets = [
                    page["id"]
                    for page in json.load(response)
                    if page.get("url") == self.url
                ]
        for target in targets:
            result, code = node_json(
                "observer_open.mjs", self.endpoint, self.url, target
            )
            if code or not (result.get("success") or result.get("already_absent")):
                raise RuntimeError("owned observer tab did not close")
        self.target = None

    def open(
        self,
        scene="looming",
        *,
        representation="skeleton",
        page_mib=4,
        uploads=True,
        culling=True,
    ):
        identity(self.serial, self.device["hardware_serial"])
        if (
            scene not in ("looming", "anatomy")
            or representation
            not in ("surface", "skeleton", "skeleton-bounded", "mixed")
            or page_mib not in (4, 16, 64)
        ):
            raise ValueError("invalid observer configuration")
        if representation == "skeleton-bounded" and not uploads:
            raise ValueError("bounded skeleton requires paged GPU uploads")
        if uploads and representation == "mixed":
            raise ValueError("paged mixed representation is unavailable")
        if self.unattended and proximity_state(self.serial)["state"] != "CLOSE":
            raise RuntimeError("unattended proximity lease lost")
        self.close_page()
        self.server.ready_document_id = None
        self.server.ready_content = None
        self.server.representation = representation
        self.url = f"http://localhost:{self.port}/live/{scene}/?" + urlencode(
            {
                **({} if self.unattended else {"xr": 1, "xrcollect": 1}),
                "paused": "",
                "representation": representation,
                "pages": int(culling),
                "adaptive": 0,
                "uploads": int(uploads),
                "gpuPageMiB": page_mib,
                "check": "",
            }
        )
        self.record(
            "viewer.json",
            {
                "scene": scene,
                "representation": representation,
                "uploads": uploads,
                "gpu_page_mib": page_mib,
                "page_culling": culling,
                "check": True,
                "url": self.url,
            },
        )
        adb(
            self.serial,
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            "-p",
            "com.oculus.browser",
        )
        if self.endpoint is None:
            # Chromium can take a few seconds to create its diagnostic socket.
            deadline = time.monotonic() + 30
            while True:
                try:
                    self.connection = browser_endpoint(self.serial)
                    self.endpoint = self.connection.__enter__()
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(1)
            self.operations.append(
                (
                    "remove-owned-forward",
                    lambda: self.connection.__exit__(None, None, None),
                )
            )
            self.operations.append(("close-owned-tab", self.close_page))
            with urllib.request.urlopen(
                self.endpoint + "/json/list", timeout=10
            ) as response:
                prior_targets = json.load(response)
            for previous in prior_targets:
                old_url = previous.get("url", "")
                if (
                    old_url.startswith(f"http://localhost:{self.port}/live/")
                    and "check" in old_url
                ):
                    node_json(
                        "observer_open.mjs", self.endpoint, old_url, previous["id"]
                    )
        created, _ = node_json("observer_open.mjs", self.endpoint, self.url)
        self.target = created["targetId"]
        return self.url

    def wait_ready(self, *, timeout=600, evidence=None, readback_only=False):
        deadline = time.monotonic() + timeout
        path = evidence or self.out / "preflight.jsonl"
        while True:
            state = snapshot(self.serial, light=True)
            try:
                state["native_focus"] = native_focus(self.serial)
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                state["native_focus"] = {
                    "components": [],
                    "browser_focused": False,
                    "error": str(exc),
                }
            check = {"eligible": False, "reasons": ["headset-not-awake"]}
            if "mWakefulness=Awake" in str(state["power"]):
                try:
                    check = browser_preflight(
                        self.endpoint,
                        self.url,
                        verify_sources=False,
                        target=self.target,
                        **({"readback_only": True} if readback_only else {}),
                    )
                    if check["eligible"]:
                        check = browser_preflight(
                            self.endpoint,
                            self.url,
                            verify_sources=True,
                            target=self.target,
                            **({"readback_only": True} if readback_only else {}),
                        )
                except (
                    OSError,
                    ValueError,
                    RuntimeError,
                    subprocess.SubprocessError,
                ) as exc:
                    check = {
                        "eligible": False,
                        "reasons": ["browser-unavailable"],
                        "error": str(exc),
                    }
            entry = {
                "at": datetime.now(UTC).isoformat(),
                "device": state,
                "browser": check,
            }
            with path.open("ab") as stream:
                stream.write(runstore.canonical(entry) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            if not readback_only and not state["native_focus"]["browser_focused"]:
                check = {
                    **check,
                    "eligible": False,
                    "reasons": [*check["reasons"], "native-browser-not-focused"],
                }
            if check["eligible"]:
                fidelity = check.get("state", {}).get("fidelity", {})
                self.server.ready_content = {
                    key: fidelity.get(key)
                    for key in ("representation", "selected", "represented")
                }
                self.server.ready_document_id = (
                    None if readback_only else check["state"]["after"]["document_id"]
                )
                self.record(
                    "progress.json",
                    {
                        "phase": "ready",
                        "readback_only": readback_only,
                        "document_id": self.server.ready_document_id,
                        "url": self.url,
                        "qualification": "not-scored",
                    },
                )
                return check
            browser_state = check.get("state", {})
            if (
                browser_state.get("fidelity", {}).get("status") == "unsupported"
                or browser_state.get("resources", {})
                .get("gpu_resources", {})
                .get("state")
                == "unsupported"
            ):
                return {**check, "unsupported": True}
            if "source-verification-requires-idle-desktop" in check["reasons"] or any(
                reason.startswith("source-mismatch:") for reason in check["reasons"]
            ):
                return check
            if time.monotonic() >= deadline:
                return {**check, "reasons": [*check["reasons"], "startup-timeout"]}
            time.sleep(min(2, max(0, deadline - time.monotonic())))

    def __exit__(self, exc_type, exc, traceback):
        # Close tab/forward before stopping the site; restoration and snapshots are independent.
        priority = {
            "close-owned-tab": 0,
            "remove-owned-forward": 1,
            "restore-keep-awake": 2,
            "restore-proximity": 2,
            "remove-owned-reverse": 3,
            "final-device-snapshot": 4,
            "http-server": 5,
            "temporary-site": 6,
        }
        self.cleanup = cleanup_resources(
            self.serial,
            self.out,
            sorted(self.operations, key=lambda item: priority[item[0]]),
        )
        self.operations = []


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial", required=True)
    p.add_argument(
        "--wifi-only",
        action="store_true",
        help="require an explicit TCP transport; no USB fallback",
    )
    p.add_argument("--scene", choices=("looming", "anatomy"), default="looming")
    p.add_argument(
        "--representation",
        choices=("surface", "skeleton", "skeleton-bounded", "mixed"),
        default="surface",
    )
    p.add_argument("--pages", action="store_true")
    p.add_argument("--uploads", action="store_true")
    p.add_argument("--gpu-page-mib", type=int, choices=(4, 16, 64), default=4)
    p.add_argument(
        "--check",
        action="store_true",
        help="compatibility flag; collection always enables diagnostic hooks",
    )
    p.add_argument("--seconds", type=int, default=1800)
    p.add_argument("--startup-timeout", type=int, default=600)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--keep-awake", action="store_true")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if a.seconds <= 0 or not 1 <= a.startup_timeout <= 600:
        p.error("positive duration and startup timeout 1..600 required")
    if a.uploads and a.representation == "mixed":
        p.error("paged uploads require explicit original surfaces or skeletons")
    if a.wifi_only:
        try:
            wifi_serial(a.serial)
        except argparse.ArgumentTypeError as exc:
            p.error(str(exc))
    out = a.out or Path("runs/quest-xr") / datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )
    try:
        session = QuestSite(
            a.serial, out, port=a.port, keep_awake=a.keep_awake, wifi_only=a.wifi_only
        )
        with session:
            session.open(
                a.scene,
                representation=a.representation,
                page_mib=a.gpu_page_mib,
                uploads=a.uploads,
                culling=a.pages,
            )
            ready = session.wait_ready(timeout=a.startup_timeout)
            if not ready["eligible"]:
                session.record(
                    "exclusion.json",
                    {
                        "qualification": "not-scored",
                        "reasons": ready["reasons"],
                        "unsupported": ready.get("unsupported", False),
                    },
                )
                return 1
            print(
                f"READY: {session.url}\nEnter VR in the headset. Evidence: {out}",
                flush=True,
            )
            deadline = time.monotonic() + a.seconds
            invalid = 0
            while time.monotonic() < deadline:
                # Passive sampling only. Never enable Debugger during an XR timing window.
                state = snapshot(a.serial, light=True)
                with (out / "device-samples.jsonl").open("ab") as stream:
                    stream.write(runstore.canonical(state) + b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                invalid = (
                    invalid + 1
                    if "mWakefulness=Awake" not in str(state["power"])
                    else 0
                )
                if invalid >= 3:
                    session.record(
                        "exclusion.json",
                        {
                            "qualification": "not-scored",
                            "reasons": ["headset-not-awake"],
                            "consecutive_invalid_samples": invalid,
                        },
                    )
                    break
                time.sleep(min(30, max(0, deadline - time.monotonic())))
        return 0 if session.cleanup["ok"] and invalid < 3 else 1
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as exc:
        if not out.exists() and isinstance(exc, ValueError):
            p.error(str(exc))
        if out.exists():
            runstore.atomic_json(
                out / "failure.json",
                {
                    "qualification": "not-scored",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        print(
            f"Collector incomplete: {type(exc).__name__}; retained evidence: {out}",
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
