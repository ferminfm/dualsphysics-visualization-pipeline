#!/usr/bin/env python3
"""Validate the keyed internal-nozzle prediction-closure-v4 container."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
MASK64 = (1 << 64) - 1
HEADER = struct.Struct("@40sIIIIIIQQQQQQQddddddddii128s128s128s")
CELL = struct.Struct("@iiiiIii6d")
FACE = struct.Struct("@iiiii4d")


def fnv1a(value: int, payload: bytes) -> int:
    for byte in payload:
        value ^= byte
        value = (value * FNV_PRIME) & MASK64
    return value


def c_string(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8")


def validate(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) < HEADER.size:
        raise ValueError("truncated header")
    values = HEADER.unpack_from(raw)
    (
        magic,
        version,
        dimension,
        endian,
        double_size,
        cell_size,
        face_size,
        cell_count,
        face_count,
        payload_bytes,
        topology_expected,
        payload_expected,
        active_hash,
        actual_face_hash,
        checkpoint_t,
        checkpoint_dt,
        checkpoint_dtmax,
        timestep_previous,
        domain_x0,
        domain_y0,
        domain_z0,
        domain_l0,
        iteration,
        maxdepth,
        source_sha,
        schedule_version,
        schedule_sha,
    ) = values
    if c_string(magic) != "internal_nozzle_prediction_closure_v4":
        raise ValueError("bad magic")
    if version != 4 or dimension != 3 or endian != 0x01020304:
        raise ValueError("incompatible version, dimension, or endian marker")
    if double_size != 8 or cell_size != CELL.size or face_size != FACE.size:
        raise ValueError("record size mismatch")
    expected_payload = cell_count * CELL.size + face_count * FACE.size
    if payload_bytes != expected_payload or len(raw) != HEADER.size + expected_payload:
        raise ValueError("count, byte-size, or trailing-data mismatch")

    cell_start = HEADER.size
    face_start = cell_start + cell_count * CELL.size
    cells_raw = raw[cell_start:face_start]
    faces_raw = raw[face_start:]
    cell_rows = [CELL.unpack_from(cells_raw, n * CELL.size) for n in range(cell_count)]
    face_rows = [FACE.unpack_from(faces_raw, n * FACE.size) for n in range(face_count)]
    cell_keys = [row[:4] for row in cell_rows]
    face_keys = [row[:5] for row in face_rows]
    if cell_keys != sorted(cell_keys) or len(cell_keys) != len(set(cell_keys)):
        raise ValueError("unordered or duplicate cell key")
    if face_keys != sorted(face_keys) or len(face_keys) != len(set(face_keys)):
        raise ValueError("unordered or duplicate face key")

    topology = FNV_OFFSET
    for row in cell_rows:
        for value in row[:4]:
            topology = fnv1a(topology, struct.pack("@i", value))
        topology = fnv1a(topology, struct.pack("@I", row[4]))
        topology = fnv1a(topology, struct.pack("@i", row[5]))
        topology = fnv1a(topology, struct.pack("@i", row[6]))
    for row in face_rows:
        for value in row[:5]:
            topology = fnv1a(topology, struct.pack("@i", value))
    if topology != topology_expected:
        raise ValueError("topology hash mismatch")

    payload = FNV_OFFSET
    payload = fnv1a(payload, struct.pack("@I", version))
    payload = fnv1a(payload, struct.pack("@Q", cell_count))
    payload = fnv1a(payload, struct.pack("@Q", face_count))
    payload = fnv1a(payload, struct.pack("@Q", topology_expected))
    for value in (checkpoint_t, checkpoint_dt, checkpoint_dtmax, timestep_previous):
        payload = fnv1a(payload, struct.pack("@d", value))
    payload = fnv1a(payload, source_sha)
    payload = fnv1a(payload, schedule_version)
    payload = fnv1a(payload, schedule_sha)
    payload = fnv1a(payload, cells_raw)
    payload = fnv1a(payload, faces_raw)
    if payload != payload_expected:
        raise ValueError("payload hash mismatch")

    return {
        "schema": "internal_nozzle_prediction_closure_v4_validation_v1",
        "path": str(path),
        "valid": True,
        "version": version,
        "dimension": dimension,
        "cell_count": cell_count,
        "face_count": face_count,
        "payload_bytes": payload_bytes,
        "topology_hash_fnv1a64": f"{topology:016x}",
        "payload_hash_fnv1a64": f"{payload:016x}",
        "active_physical_hash_fnv1a64": f"{active_hash:016x}",
        "actual_face_hash_fnv1a64": f"{actual_face_hash:016x}",
        "checkpoint_t": checkpoint_t,
        "checkpoint_dt": checkpoint_dt,
        "checkpoint_dtmax": checkpoint_dtmax,
        "timestep_previous": timestep_previous,
        "iteration": iteration,
        "grid_maxdepth": maxdepth,
        "domain": [domain_x0, domain_y0, domain_z0, domain_l0],
        "source_sha256": c_string(source_sha),
        "schedule_version": c_string(schedule_version),
        "schedule_sha256": c_string(schedule_sha),
        "sorted_unique_cell_keys": True,
        "sorted_unique_face_keys": True,
        "trailing_bytes": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    report = validate(args.checkpoint)
    if args.compare:
        other = validate(args.compare)
        report["comparison"] = {
            "path": str(args.compare),
            "byte_exact": args.checkpoint.read_bytes() == args.compare.read_bytes(),
            "topology_hash_exact": report["topology_hash_fnv1a64"]
            == other["topology_hash_fnv1a64"],
            "payload_hash_exact": report["payload_hash_fnv1a64"]
            == other["payload_hash_fnv1a64"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
