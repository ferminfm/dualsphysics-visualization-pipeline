#!/usr/bin/env python3
"""Compare Task 01 projection traces with exact keys and hex-float values."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


IDENTITY_COLUMNS = (
    "kind",
    "stage",
    "pressure",
    "cycle",
    "active_level",
)
MANIFEST_VALUE_COLUMNS = (
    "t",
    "i",
    "dt",
    "DT",
    "dtmax",
    "CFL",
    "nrelax",
    "residual",
    "TOLERANCE",
    "NITERMIN",
    "NITERMAX",
    "grid_maxdepth",
    "mgp_i",
    "mgp_resb",
    "mgp_resa",
    "mgp_nrelax",
    "mgpf_i",
    "mgpf_resb",
    "mgpf_resa",
    "mgpf_nrelax",
    "pressure_nodump",
    "pf_nodump",
)
ROW_ID_COLUMNS = (
    "boundary",
    "sequence",
    "x",
    "y",
    "z",
    "level",
    "Delta",
    "is_leaf",
    "field_index",
    "field_role",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_number(text: str) -> float:
    if text.lower().startswith(("0x", "-0x", "+0x")):
        return float.fromhex(text)
    return float(text)


def normalized_delta(a: float, b: float) -> float:
    if math.isnan(a) and math.isnan(b):
        return 0.0
    if a == b:
        return 0.0
    return abs(a - b) / max(1.0, abs(a), abs(b))


def row_identity(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row.get(name, "") for name in ROW_ID_COLUMNS)


def first_file_difference(left: Path, right: Path) -> dict | None:
    with left.open(newline="", encoding="utf-8") as la, right.open(
        newline="", encoding="utf-8"
    ) as rb:
        lreader, rreader = csv.DictReader(la), csv.DictReader(rb)
        if lreader.fieldnames != rreader.fieldnames:
            return {
                "kind": "header",
                "left": lreader.fieldnames,
                "right": rreader.fieldnames,
            }
        for index, (lrow, rrow) in enumerate(zip(lreader, rreader, strict=False)):
            lkey, rkey = row_identity(lrow), row_identity(rrow)
            if lkey != rkey:
                return {
                    "kind": "row_identity_or_traversal_order",
                    "row": index,
                    "left_key": lkey,
                    "right_key": rkey,
                }
            if lrow != rrow:
                differing = [
                    name for name in lrow
                    if lrow.get(name) != rrow.get(name)
                ]
                detail = {
                    "kind": "value",
                    "row": index,
                    "key": lkey,
                    "columns": differing,
                    "left": {name: lrow.get(name) for name in differing},
                    "right": {name: rrow.get(name) for name in differing},
                }
                if differing == ["value"]:
                    a = parse_number(lrow["value"])
                    b = parse_number(rrow["value"])
                    detail["absolute_delta"] = abs(a - b)
                    detail["normalized_delta"] = normalized_delta(a, b)
                return detail
        ltail, rtail = next(lreader, None), next(rreader, None)
        if ltail is not None or rtail is not None:
            return {
                "kind": "row_count",
                "left_has_extra": ltail is not None,
                "right_has_extra": rtail is not None,
            }
    return None


def stage_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[name] for name in IDENTITY_COLUMNS)


def load_manifest(run: Path) -> list[dict[str, str]]:
    rows = read_csv(run / "projection_trace" / "trace_manifest.csv")
    indices = [int(row["trace_index"]) for row in rows]
    if indices != list(range(len(rows))):
        raise ValueError(f"non-contiguous trace indices in {run}")
    return rows


def compare_run_pair(left: Path, right: Path, label: str) -> dict:
    lrows, rrows = load_manifest(left), load_manifest(right)
    stages = []
    first = None
    for index in range(max(len(lrows), len(rrows))):
        if index >= len(lrows) or index >= len(rrows):
            entry = {
                "trace_index": index,
                "stage_present_left": index < len(lrows),
                "stage_present_right": index < len(rrows),
                "exact": False,
            }
            stages.append(entry)
            first = first or entry
            continue
        lrow, rrow = lrows[index], rrows[index]
        lkey, rkey = stage_key(lrow), stage_key(rrow)
        manifest_differences = {
            name: {"left": lrow[name], "right": rrow[name]}
            for name in MANIFEST_VALUE_COLUMNS
            if lrow[name] != rrow[name]
        }
        entry = {
            "trace_index": index,
            "identity": dict(zip(IDENTITY_COLUMNS, lkey)),
            "identity_exact": lkey == rkey,
            "manifest_values_exact": not manifest_differences,
            "manifest_differences": manifest_differences,
            "files": {},
        }
        for field in ("data_file", "boundary_file"):
            lpath, rpath = Path(lrow[field]), Path(rrow[field])
            lsha, rsha = sha256(lpath), sha256(rpath)
            difference = None if lsha == rsha else first_file_difference(lpath, rpath)
            entry["files"][field] = {
                "left": str(lpath),
                "right": str(rpath),
                "left_sha256": lsha,
                "right_sha256": rsha,
                "exact": lsha == rsha,
                "first_difference": difference,
            }
        entry["exact"] = bool(
            entry["identity_exact"]
            and entry["manifest_values_exact"]
            and all(item["exact"] for item in entry["files"].values())
        )
        if not entry["exact"] and first is None:
            first = entry
        stages.append(entry)
    summary_left = left / "projection_trace" / "projection_summaries.csv"
    summary_right = right / "projection_trace" / "projection_summaries.csv"
    result = {
        "label": label,
        "left": str(left),
        "right": str(right),
        "left_stage_count": len(lrows),
        "right_stage_count": len(rrows),
        "stage_identity_sequence_exact": [stage_key(row) for row in lrows]
        == [stage_key(row) for row in rrows],
        "all_exact": first is None,
        "first_difference": first,
        "projection_summaries": {
            "left_sha256": sha256(summary_left),
            "right_sha256": sha256(summary_right),
            "exact": sha256(summary_left) == sha256(summary_right),
        },
        "stages": stages,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-a", type=Path, required=True)
    parser.add_argument("--fresh-b", type=Path, required=True)
    parser.add_argument("--restart-a", type=Path, required=True)
    parser.add_argument("--restart-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = {
        "schema": "internal_nozzle_projection_trace_comparison_v1",
        "fresh_fresh": compare_run_pair(args.fresh_a, args.fresh_b, "fresh_fresh"),
        "restart_restart": compare_run_pair(
            args.restart_a, args.restart_b, "restart_restart"
        ),
        "fresh_restart": compare_run_pair(
            args.fresh_a, args.restart_a, "fresh_restart"
        ),
    }
    payload["controls_exact"] = bool(
        payload["fresh_fresh"]["all_exact"]
        and payload["restart_restart"]["all_exact"]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"INTERNAL_NOZZLE_PROJECTION_TRACE_COMPARISON={args.output}")
    return 0 if payload["controls_exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
