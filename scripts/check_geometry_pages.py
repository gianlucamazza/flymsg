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

from flymsg import manifest, runstore, viz

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/__raster.html":
            body = b"""<!doctype html><title>Raster pixel oracle</title>
<script type="module">
import {rasterOracle} from "/raster-oracle.js";
window.oracle=rasterOracle({timingSamples:0});
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
    parser.add_argument("--oracle", choices=("geometry", "raster"), default="geometry")
    args = parser.parse_args()
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
    page = "__raster.html" if args.oracle == "raster" else "__oracle.html"
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
                    "EVAL_TIMEOUT_MS": "60000",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=90,
                check=False,
            )
            (args.out / "browser.log").write_text(result.stdout)
            values = [
                json.loads(line[7:])
                for line in result.stdout.splitlines()
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
                },
            )
        finally:
            server.shutdown()
            thread.join()
    print(f"Raster oracle passed: {args.out}")


if __name__ == "__main__":
    main()
