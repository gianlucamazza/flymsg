"""Apply/check the isolated indexed-line multi-draw extension to pinned Three r170.

The inverse transform MUST recover the exact upstream asset hash. No other vendor
changes, shader changes, build tools or runtime monkey-patches are involved.
"""

import argparse
import hashlib
from pathlib import Path

UPSTREAM = "08fd7545d13d2c7fb65ab691530a802dafefd638596501854f267d0fb13c39e7"
OLD = b"if(r.isBatchedMesh)if(null!==r._multiDrawInstances)"
NEW = (
    b"if(r.isMultiDrawLineSegments===true){if(!r.isLineSegments||null===l||"
    b'!J.get("WEBGL_multi_draw"))throw new Error("FlyMSG indexed line multi-draw unavailable");'
    b"g.renderMultiDraw(r.lineStarts,r.lineCounts,r.lineDrawCount)}else " + OLD
)
SUFFIX = b"\n// FlyMSG r170 indexed-line range extension; see ../FLYMSG-LINE-RANGES.md.\nexport const FLYMSG_LINE_RANGES=1;\n"
TARGET = (
    Path(__file__).resolve().parents[1]
    / "src/flymsg/viz_static/vendor/three/build/three.module.min.js"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    check = parser.parse_args().check
    data = TARGET.read_bytes()
    if data.endswith(SUFFIX):
        if data.count(NEW) != 1:
            raise ValueError("Unexpected renderer extension count")
        original = data[: -len(SUFFIX)].replace(NEW, OLD)
        if hashlib.sha256(original).hexdigest() != UPSTREAM:
            raise ValueError("Vendor differs beyond the declared extension")
        print("Verified: inverse patch recovers exact upstream Three r170")
    elif check:
        raise ValueError("Indexed-line extension not applied")
    else:
        if hashlib.sha256(data).hexdigest() != UPSTREAM or data.count(OLD) != 1:
            raise ValueError(
                "Unexpected upstream renderer; review patch before upgrading"
            )
        TARGET.write_bytes(data.replace(OLD, NEW) + SUFFIX)
        print("Applied isolated indexed-line multi-draw extension")


if __name__ == "__main__":
    main()
