"""Run the independent full-index raster oracle in a real headless WebGL browser.

Software WebGL verifies images, not performance. Output is immutable and contains
the exact source hashes, raw browser log, screenshot and machine-readable checks.
"""

import argparse
import hashlib
import json
import os
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from flymsg import manifest, runstore, viz

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    fixture = None

    def do_GET(self):
        path = urlsplit(self.path).path
        if self.fixture and path in ("/scene.json", "/activity.bin"):
            body = self.fixture[path]
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json"
                if path.endswith("json")
                else "application/octet-stream",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/__viewer.html":
            body = (
                (viz.STATIC / "index.html").read_bytes()
                + b"""
<script type="module">
import {observerPipelineOracle} from "/observer-pipeline-oracle.js";
window.oracle=observerPipelineOracle().catch(error=>({status:'fail',error:String(error),stack:error.stack}));
</script>"""
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/__paged.html":
            body = b"""<!doctype html><title>GPU page oracle</title>
<script type="module">
import * as THREE from "/vendor/three/build/three.module.min.js";
import {pagedSceneOracle} from "/paged-scene-oracle.js";
window.oracle=pagedSceneOracle(THREE).catch(error=>({status:'fail',error:String(error),stack:error.stack}));
</script>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/__raster.html":
            body = b"""<!doctype html><title>Raster pixel oracle</title>
<script type="module">
import {rasterOracle} from "/raster-oracle.js";
window.oracle=rasterOracle({timingSamples:0,cpu:true});
</script>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/__oracle.html":
            body = b"""<!doctype html><title>Geometry page raster oracle</title>
<script type="module">
import * as THREE from "/vendor/three/build/three.module.min.js";
import {geometryPageOracle} from "/geometry-pages-oracle.js";
window.oracle=geometryPageOracle(THREE);
</script>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Total software-oracle time limit, including full-quality readbacks",
    )
    parser.add_argument(
        "--oracle",
        choices=("geometry", "raster", "paged", "viewer-surface", "viewer-skeleton"),
        default="geometry",
    )
    args = parser.parse_args()
    if not 30 <= args.timeout_seconds <= 600:
        parser.error("--timeout-seconds must be 30..600")
    args.out.mkdir(parents=True, exist_ok=False)
    source = manifest.git_info()
    files = (
        "geometry-pages.js",
        "resident-lines.js",
        "geometry-pages-oracle.js",
        "page-views.js",
        "render-reference.js",
        "vendor/three/build/three.module.min.js",
    )
    if args.oracle == "raster":
        files = (
            "raster.js",
            "raster-painter.js",
            "raster-reference.js",
            "raster-oracle.js",
        )
    if args.oracle == "paged":
        files = (
            "primitive-pages.js",
            "page-worker.js",
            "gpu-upload.js",
            "paged-scene.js",
            "paged-scene-oracle.js",
            "render-reference.js",
            "geometry-worker.js",
            "context-geometry.js",
            "geometry.js",
            "geometry-pages.js",
            "precomputed.js",
            "vendor/three/build/three.module.min.js",
        )
    if args.oracle.startswith("viewer-"):
        files = tuple(p.name for p in viz.STATIC.glob("*.js")) + (
            "vendor/three/build/three.module.min.js",
        )
        scene = json.loads((ROOT / "docs/live/looming/scene.json").read_text())
        count = len(scene["neurons"])
        activity = (ROOT / "docs/live/looming/activity.bin").read_bytes()
        scene["neurons"] = scene["neurons"][:2]
        Handler.fixture = {
            "/scene.json": json.dumps(scene).encode(),
            "/activity.bin": b"".join(
                activity[i : i + 2] for i in range(0, len(activity), count)
            ),
        }
    page = {
        "raster": "__raster.html",
        "geometry": "__oracle.html",
        "paged": "__paged.html",
        "viewer-surface": "__viewer.html?check&paused&representation=surface&uploads=1&neuropils=0&somata=0",
        "viewer-skeleton": "__viewer.html?check&paused&representation=skeleton&uploads=1&neuropils=0&somata=0",
    }[args.oracle]
    hashes = {
        name: hashlib.sha256((viz.STATIC / name).read_bytes()).hexdigest()
        for name in files
    }
    with ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(viz.STATIC))
    ) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with (args.out / "browser.log").open("w") as log:
                result = subprocess.run(
                    [
                        "node",
                        str(ROOT / "scripts/shoot.mjs"),
                        f"http://localhost:{server.server_port}/{page}",
                        str(args.out / "browser.png"),
                        "3",
                        "400",
                        "300",
                    ],
                    env={
                        **os.environ,
                        "GL": "swiftshader",
                        "EVAL": "window.oracle",
                        "EVAL_TIMEOUT_MS": str((args.timeout_seconds - 15) * 1000),
                    },
                    text=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=args.timeout_seconds,
                    check=False,
                )
            stdout = (args.out / "browser.log").read_text()
            values = [
                json.loads(line[7:])
                for line in stdout.splitlines()
                if line.startswith("[eval] ")
            ]
            if (
                result.returncode
                or len(values) != 1
                or not isinstance(values[0], dict)
                or values[0].get("status") != "pass"
            ):
                raise RuntimeError(
                    f"Raster oracle failed; inspect {args.out / 'browser.log'}"
                )
            if manifest.git_info() != source or hashes != {
                name: hashlib.sha256((viz.STATIC / name).read_bytes()).hexdigest()
                for name in files
            }:
                raise RuntimeError("Oracle source changed during the test")
            runstore.atomic_json(
                args.out / "oracle.json",
                {
                    **values[0],
                    "source": source,
                    "source_sha256": hashes,
                    "backend": "SwiftShader; correctness only",
                    "timeout_seconds": args.timeout_seconds,
                },
            )
        finally:
            server.shutdown()
            thread.join()
    print(f"Raster oracle passed: {args.out}")


if __name__ == "__main__":
    main()
