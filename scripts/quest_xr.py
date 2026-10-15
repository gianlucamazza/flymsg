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
        "battery": ("shell", "dumpsys", "battery"),
        "thermal": ("shell", "dumpsys", "thermalservice"),
        "browser_memory": ("shell", "dumpsys", "meminfo", "com.oculus.browser"),
    }.items():
        try:
            out[key] = adb(serial, *args)
        except (OSError, subprocess.SubprocessError) as exc:
            out[key] = {"unavailable": str(exc)}
    return out


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
    p.add_argument("--out", type=Path)
    a = p.parse_args()
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
                adb(a.serial, "reverse", reverse, reverse)
                owned_reverse = True
                url = (
                    f"http://localhost:{a.port}/live/{a.scene}/?xr=1&xrcollect=1&paused"
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
                while time.monotonic() < until:
                    with (out / "device-samples.jsonl").open("ab") as stream:
                        stream.write(runstore.canonical(snapshot(a.serial)) + b"\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    time.sleep(min(30, max(0, until - time.monotonic())))
            except KeyboardInterrupt:
                print("Stopped; collected evidence is retained.")
            finally:
                server.shutdown()
                if owned_reverse:
                    adb(a.serial, "reverse", "--remove", reverse)
                runstore.atomic_json(out / "after.json", snapshot(a.serial))
    print(f"Hardware qualification still requires the checklist: {out}")


if __name__ == "__main__":
    main()
