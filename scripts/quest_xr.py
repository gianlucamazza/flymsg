"""Serve this checkout to one explicitly selected Quest 2 and persist XR evidence.

uv run python scripts/quest_xr.py --serial SERIAL [--scene looming] [--seconds 1800]
The user enters VR and performs head motion/menu tests. This does not fake user activation
or declare hardware qualified. No adb server restart, package installation or /etc writes.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import tempfile
import threading
import time
import urllib.request
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from flymsg import manifest, pages, runstore


def adb(serial, *args):
    return subprocess.check_output(
        ["adb", "-s", serial, *args], text=True, timeout=20
    ).strip()


def snapshot(serial):
    out = {"at": datetime.now(UTC).isoformat()}
    for key, args in {
        "power": ("shell", "dumpsys", "power"),
        "battery": ("shell", "dumpsys", "battery"),
        "thermal": ("shell", "dumpsys", "thermalservice"),
        "browser_memory": ("shell", "dumpsys", "meminfo", "com.oculus.browser"),
    }.items():
        try:
            out[key] = adb(serial, *args)
        except (OSError, subprocess.SubprocessError) as exc:
            out[key] = {"unavailable": str(exc)}
    return out


def preflight(serial, url):
    """No rendering measurement is eligible while the headset is asleep."""
    state = snapshot(serial)
    result = {"device": state, "eligible": False, "reasons": []}
    if "mWakefulness=Awake" not in str(state["power"]):
        result["reasons"].append("headset-not-awake")
        return result
    forward = None
    try:
        sockets = adb(serial, "shell", "cat", "/proc/net/unix")
        names = {
            line.split()[-1][1:]
            for line in sockets.splitlines()
            if "@chrome_devtools_remote" in line
        }
        if len(names) != 1:
            raise RuntimeError("one Quest Browser diagnostic socket required")
        port = adb(serial, "forward", "tcp:0", f"localabstract:{names.pop()}")
        forward = f"tcp:{port}"
        endpoint = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(endpoint + "/json/list", timeout=10) as response:
            targets = json.load(response)
        matches = [target for target in targets if target.get("url") == url]
        if len(matches) != 1:
            raise RuntimeError("expected page URL is not the unique loaded target")
        process = subprocess.run(
            [
                "node",
                str(Path(__file__).with_name("observer_preflight.mjs")),
                endpoint,
                matches[0]["id"],
                url,
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if not process.stdout.strip():
            raise RuntimeError("browser preflight unavailable")
        result["browser"] = json.loads(process.stdout)
        result["eligible"] = process.returncode == 0 and result["browser"]["eligible"]
        result["reasons"] = result["browser"]["reasons"]
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result["reasons"].append(str(exc))
    finally:
        if forward:
            adb(serial, "forward", "--remove", forward)
    return result


class EvidenceHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory, evidence, **kwargs):
        self.evidence = evidence
        super().__init__(*args, directory=directory, **kwargs)

    def do_POST(self):
        if self.path != "/__xr_evidence":
            return self.send_error(404)
        # Only this local server's same-origin viewer may append evidence.
        if self.headers.get("Origin") != f"http://localhost:{self.server.server_port}":
            return self.send_error(403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8_000_000:
                return self.send_error(413)
            doc = json.loads(self.rfile.read(length))
            if not isinstance(doc, dict) or doc.get("schema") != "flymsg.xr-bench/v1":
                return self.send_error(400)
            entry = {"received_at": datetime.now(UTC).isoformat(), "report": doc}
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--serial", required=True, help="explicit adb device serial; never selects a TV"
    )
    p.add_argument("--scene", choices=("looming", "anatomy"), default="looming")
    p.add_argument("--seconds", type=int, default=1800)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument(
        "--representation", choices=("surface", "skeleton", "mixed"), default="surface"
    )
    p.add_argument(
        "--pages",
        action="store_true",
        help="enable candidate conservative page culling",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="expose local read-only/observer diagnostic hooks",
    )
    p.add_argument(
        "--uploads",
        action="store_true",
        help="enable candidate immutable GPU pages and bounded uploads",
    )
    p.add_argument("--gpu-page-mib", type=int, choices=(4, 16, 64), default=4)
    p.add_argument("--out", type=Path)
    p.add_argument(
        "--keep-awake",
        action="store_true",
        help="temporarily keep the powered display awake; restore its setting",
    )
    a = p.parse_args()
    if a.uploads and a.representation == "mixed":
        p.error("paged uploads require explicit original surfaces or skeletons")
    if a.seconds <= 0 or not 1024 <= a.port <= 65535:
        p.error("seconds must be positive and port between 1024 and 65535")
    model = adb(a.serial, "shell", "getprop", "ro.product.model")
    if model != "Quest 2":
        p.error(f"selected device is {model!r}, not Quest 2")
    source = manifest.git_info()
    if source["dirty"] is not False:
        p.error("hardware evidence requires clean committed source")
    out = a.out or Path("runs/quest-xr") / datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )
    out.mkdir(parents=True, exist_ok=False)
    device = {
        "model": model,
        "serial": a.serial,
        "source": source,
        "fingerprint": adb(a.serial, "shell", "getprop", "ro.build.fingerprint"),
        "browser": adb(a.serial, "shell", "dumpsys", "package", "com.oculus.browser"),
        "scene": a.scene,
        "viewer": {
            "representation": a.representation,
            "page_culling": a.pages,
            "check": a.check,
            "paged_uploads": a.uploads,
            "gpu_page_mib": a.gpu_page_mib,
        },
        "adb_server_port": os.environ.get("ANDROID_ADB_SERVER_PORT", "5037"),
        "qualification": "not-scored",
        "before": snapshot(a.serial),
    }
    reverse = f"tcp:{a.port}"
    mappings = adb(a.serial, "reverse", "--list")
    if any(reverse in line.split() for line in mappings.splitlines()):
        p.error(f"reverse port {a.port} already mapped; choose another --port")
    owned_reverse = False
    with tempfile.TemporaryDirectory(prefix="flymsg-quest-") as tmp:
        site = Path(tmp) / "site"
        pages.build(site)
        if manifest.git_info() != source:
            raise ValueError("source changed while building the headset site")
        device["site_sha256"] = runstore.digest(runstore.inventory(site))
        device["development"] = {
            key: adb(a.serial, "shell", "settings", "get", "global", key)
            for key in ("adb_enabled", "adb_wifi_enabled", "stay_on_while_plugged_in")
        }
        device["overrides"] = {
            key: adb(a.serial, "shell", "getprop", f"debug.oculus.{key}")
            for key in (
                "refreshRate",
                "foveation.level",
                "textureWidth",
                "textureHeight",
                "cpuLevel",
                "gpuLevel",
            )
        }
        runstore.atomic_json(out / "device.json", device)
        handler = partial(
            EvidenceHandler, directory=str(site), evidence=out / "sessions.jsonl"
        )
        with ThreadingHTTPServer(("127.0.0.1", a.port), handler) as server:
            server.evidence_lock = threading.Lock()
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                if a.keep_awake:
                    adb(a.serial, "shell", "svc", "power", "stayon", "true")
                adb(a.serial, "reverse", reverse, reverse)
                owned_reverse = True
                url = (
                    f"http://localhost:{a.port}/live/{a.scene}/?xr=1&xrcollect=1&paused"
                    f"&representation={a.representation}&pages={int(a.pages)}&adaptive=0"
                    f"&uploads={int(a.uploads)}&gpuPageMiB={a.gpu_page_mib}" + "&check"
                )
                adb(
                    a.serial,
                    "shell",
                    "am",
                    "start",
                    "-a",
                    "android.intent.action.VIEW",
                    "-d",
                    shlex.quote(url),
                    "-p",
                    "com.oculus.browser",
                )
                print(
                    f"Open in Quest Browser: {url}\nEnter VR in the headset. Evidence: {out}",
                    flush=True,
                )
                until = time.monotonic() + a.seconds
                excluded = 0
                while time.monotonic() < until:
                    check = preflight(a.serial, url)
                    with (out / "preflight.jsonl").open("ab") as stream:
                        stream.write(runstore.canonical(check) + b"\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    excluded = 0 if check["eligible"] else excluded + 1
                    if excluded >= 3:
                        runstore.atomic_json(
                            out / "exclusion.json",
                            {
                                "status": "excluded",
                                "qualification": "not-scored",
                                "consecutive_invalid_preflights": excluded,
                                "reasons": check["reasons"],
                            },
                        )
                        break
                    with (out / "device-samples.jsonl").open("ab") as stream:
                        stream.write(runstore.canonical(snapshot(a.serial)) + b"\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    time.sleep(min(30, max(0, until - time.monotonic())))
            except KeyboardInterrupt:
                print("Stopped; collected evidence is retained.")
            finally:
                server.shutdown()
                if a.keep_awake:
                    adb(
                        a.serial,
                        "shell",
                        "settings",
                        "put",
                        "global",
                        "stay_on_while_plugged_in",
                        device["development"]["stay_on_while_plugged_in"],
                    )
                if owned_reverse:
                    adb(a.serial, "reverse", "--remove", reverse)
                runstore.atomic_json(out / "after.json", snapshot(a.serial))
    print(f"Hardware qualification still requires the checklist: {out}")


if __name__ == "__main__":
    main()
