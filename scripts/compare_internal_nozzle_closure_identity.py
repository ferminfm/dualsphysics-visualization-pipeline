#!/usr/bin/env python3
"""Streaming v4 companion comparison; no solver or full-field-equivalence claim."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

HEADER = struct.Struct("@40s6I7Q8d2i128s128s128s")
NAMES = "magic version dimension endian double_size cell_size face_size cell_count face_count payload_bytes topology_hash payload_hash active_hash face_hash t dt dtmax timestep_previous x0 y0 z0 l0 iteration depth source schedule_version schedule_sha".split()


def header(stream):
    values = HEADER.unpack(stream.read(HEADER.size))
    out = dict(zip(NAMES, (x.decode().rstrip(chr(0)) if isinstance(x, bytes) else x for x in values)))
    assert HEADER.size == 576 and out["magic"] == "internal_nozzle_prediction_closure_v4"
    assert (out["version"], out["dimension"], out["endian"], out["double_size"], out["cell_size"], out["face_size"]) == (4, 3, 0x01020304, 8, 80, 56)
    assert out["cell_count"] > 0 and out["face_count"] > 0
    assert out["payload_bytes"] == 80 * out["cell_count"] + 56 * out["face_count"]
    return out


def compare(left, right):
    for p in (left, right):
        assert p.is_file() and not any(q.is_symlink() for q in (p, *p.parents))
    full = [hashlib.sha256(), hashlib.sha256()]
    payload = [hashlib.sha256(), hashlib.sha256()]
    different = 0; first = None; offset = 0
    with left.open("rb") as l, right.open("rb") as r:
        lh, rh = header(l), header(r)
        assert left.stat().st_size == HEADER.size + lh["payload_bytes"]
        assert right.stat().st_size == HEADER.size + rh["payload_bytes"]
        l.seek(0); r.seek(0)
        while True:
            a, b = l.read(65536), r.read(65536)
            if not a and not b: break
            full[0].update(a); full[1].update(b)
            skip = max(0, HEADER.size - offset)
            payload[0].update(a[skip:]); payload[1].update(b[skip:])
            if a != b:
                changed = [i for i in range(max(len(a), len(b))) if a[i:i+1] != b[i:i+1]]
                different += len(changed)
                if first is None: first = offset + changed[0]
            offset += max(len(a), len(b))
    return {"schema": "internal_nozzle_v4_retained_closure_comparison_v1",
            "left": {"path": str(left), "sha256": full[0].hexdigest(), "size_bytes": left.stat().st_size},
            "right": {"path": str(right), "sha256": full[1].hexdigest(), "size_bytes": right.stat().st_size},
            "header_size": HEADER.size, "left_header": lh, "right_header": rh,
            "header_differences": {k: [lh[k], rh[k]] for k in NAMES if lh[k] != rh[k]},
            "payload_sha256": [h.hexdigest() for h in payload],
            "payload_byte_identical": payload[0].digest() == payload[1].digest(),
            "differing_bytes": different, "first_differing_byte": first,
            "scope": "all serialized v4 cell u/g and face uf/fs/a/fm records; active physical/face hashes retained in header",
            "not_covered": "nonserialized ghost/coarse p/pf and derived alpha/mu/rho, subsequent event state or complete evolved equivalence"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--left", type=Path, required=True); p.add_argument("--right", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); result = compare(a.left, a.right)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False); f.write("\n")
    print(json.dumps({"payload_byte_identical": result["payload_byte_identical"], "header_differences": result["header_differences"], "output": str(a.output)}))


if __name__ == "__main__": main()
