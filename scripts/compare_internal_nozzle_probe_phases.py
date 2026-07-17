#!/usr/bin/env python3
"""Compare matched Task 01 forensic probe phases without solver mutation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


CELL_KEYS = ("x", "y", "z", "level", "Delta")
CELL_FIELDS = ("f", "ux", "uy", "uz", "p", "pf", "gx", "gy", "gz", "cs", "cm", "un")
FACE_KEYS = ("axis", "x", "y", "z", "level", "Delta")
FACE_FIELDS = ("uf", "fs", "a")


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normalized_delta(left: float, right: float) -> float:
    return abs(left - right)/max(1.0, abs(left), abs(right))


def compare_files(left: Path, right: Path, keys: tuple[str, ...], fields: tuple[str, ...]) -> dict:
    left_rows, right_rows = rows(left), rows(right)
    left_map = {tuple(row[key] for key in keys): row for row in left_rows}
    right_map = {tuple(row[key] for key in keys): row for row in right_rows}
    left_keys, right_keys = set(left_map), set(right_map)
    maxima = {field: {"normalized_delta": 0.0, "unequal_keys": 0} for field in fields}
    first = None
    for key in sorted(left_keys & right_keys):
        for field in fields:
            left_value = float(left_map[key][field])
            right_value = float(right_map[key][field])
            if left_value == right_value:
                continue
            delta = normalized_delta(left_value, right_value)
            maxima[field]["unequal_keys"] += 1
            if delta > maxima[field]["normalized_delta"]:
                maxima[field].update({
                    "normalized_delta": delta,
                    "left": left_value,
                    "right": right_value,
                    "key": dict(zip(keys, key)),
                })
            if first is None:
                first = {
                    "field": field,
                    "left": left_value,
                    "right": right_value,
                    "normalized_delta": delta,
                    "key": dict(zip(keys, key)),
                }
    return {
        "left_rows": len(left_rows),
        "right_rows": len(right_rows),
        "left_unique_keys": len(left_keys),
        "right_unique_keys": len(right_keys),
        "left_duplicate_keys": len(left_rows) - len(left_map),
        "right_duplicate_keys": len(right_rows) - len(right_map),
        "same_topology": left_keys == right_keys,
        "first_difference": first,
        "maxima": maxima,
        "exact_values": first is None and left_keys == right_keys,
    }


def manifest(run: Path) -> list[dict[str, str]]:
    return rows(run/"forensic_probes"/"probe_manifest.csv")


def phase_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["phase"], row["t"], row["i"]


def compare_runs(left_run: Path, right_run: Path) -> dict:
    right_rows = {phase_key(row): row for row in manifest(right_run)}
    phases = []
    for left in manifest(left_run):
        key = phase_key(left)
        if key not in right_rows:
            continue
        right = right_rows[key]
        cells = compare_files(Path(left["cell_file"]), Path(right["cell_file"]), CELL_KEYS, CELL_FIELDS)
        faces = compare_files(Path(left["face_file"]), Path(right["face_file"]), FACE_KEYS, FACE_FIELDS)
        phases.append({
            "phase": left["phase"],
            "t": left["t"],
            "i": left["i"],
            "cells": cells,
            "faces": faces,
            "exact": cells["exact_values"] and faces["exact_values"],
        })
    first = next((phase for phase in phases if not phase["exact"]), None)
    return {
        "matched_phases": len(phases),
        "all_exact": first is None,
        "first_difference": first,
        "phases": phases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-a", type=Path, required=True)
    parser.add_argument("--fresh-b", type=Path, required=True)
    parser.add_argument("--restart-a", type=Path, required=True)
    parser.add_argument("--restart-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = {
        "schema": "internal_nozzle_probe_phase_comparison_v1",
        "fresh_fresh": compare_runs(args.fresh_a, args.fresh_b),
        "restart_restart": compare_runs(args.restart_a, args.restart_b),
        "fresh_restart": compare_runs(args.fresh_a, args.restart_a),
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"INTERNAL_NOZZLE_PROBE_PHASE_COMPARISON={args.output}")
    return 0 if payload["fresh_fresh"]["all_exact"] and payload["restart_restart"]["all_exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
