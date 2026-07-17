#!/usr/bin/env python3
"""Check restartable internal-nozzle visual-output manifests.

This helper does not run a solver. It validates monotone frame/checkpoint
manifests and, when given uninterrupted and restarted run directories, compares
common scalar diagnostics at matched times.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


METRIC_FIELDS = [
    "mean_exit_velocity",
    "exit_flow",
    "exit_liquid_area",
    "liquid_volume",
    "liquid_mass_balance_relative_error",
    "active_front",
    "interface_proxy",
    "interface_growth",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in ("", None) else math.nan


def validate_sequence(rows: list[dict[str, str]], index_key: str, time_key: str = "t") -> dict[str, object]:
    indices = [int(float(row[index_key])) for row in rows if row.get(index_key, "") != ""]
    times = [as_float(row, time_key) for row in rows if row.get(time_key, "") != ""]
    return {
        "count": len(indices),
        "unique_indices": len(indices) == len(set(indices)),
        "monotone_indices": all(b > a for a, b in zip(indices, indices[1:])),
        "monotone_times": all(b + 1e-15 >= a for a, b in zip(times, times[1:])),
        "first_index": indices[0] if indices else None,
        "last_index": indices[-1] if indices else None,
    }


def diagnostics_by_time(run_dir: Path) -> dict[float, dict[str, str]]:
    rows = read_csv(run_dir / "raw_frame_summary.csv")
    out: dict[float, dict[str, str]] = {}
    for row in rows:
        if row.get("t", ""):
            out[round(float(row["t"]), 12)] = row
    return out


def compare_runs(reference: Path, restart: Path, tolerance: float) -> dict[str, object]:
    ref = diagnostics_by_time(reference)
    rst = diagnostics_by_time(restart)
    common = sorted(set(ref) & set(rst))
    comparisons: list[dict[str, object]] = []
    max_abs_delta = 0.0
    passed = bool(common)
    for tt in common:
        item: dict[str, object] = {"time": tt, "metrics": {}}
        for field in METRIC_FIELDS:
            a = as_float(ref[tt], field)
            b = as_float(rst[tt], field)
            delta = abs(a - b)
            if math.isfinite(delta):
                max_abs_delta = max(max_abs_delta, delta)
            ok = bool(math.isfinite(delta) and delta <= tolerance)
            if not ok:
                passed = False
            item["metrics"][field] = {
                "reference": a,
                "restart": b,
                "abs_delta": delta,
                "within_tolerance": ok,
            }
        comparisons.append(item)
    return {
        "matched_times": common,
        "comparison_count": len(comparisons),
        "tolerance": tolerance,
        "max_abs_delta": max_abs_delta,
        "passed": passed,
        "comparisons": comparisons,
    }


def checkpoint_path(run_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path
    return run_dir / "checkpoints" / path.name


def validate_run_dir(run_dir: Path) -> dict[str, object]:
    visual = read_csv(run_dir / "visual_frame_manifest.csv")
    surfaces = read_csv(run_dir / "surface_manifest.csv")
    checkpoints = read_csv(run_dir / "checkpoint_index.csv")
    checkpoint_files = [checkpoint_path(run_dir, row["filename"]) for row in checkpoints if row.get("filename")]
    surface_files = [run_dir / row["filename"] for row in surfaces if row.get("filename")]
    return {
        "run_dir": str(run_dir),
        "visual_frames": validate_sequence(visual, "frame_index"),
        "surfaces": validate_sequence(surfaces, "surface_index"),
        "checkpoints": validate_sequence(checkpoints, "checkpoint_index"),
        "checkpoint_files_nonzero": all(path.exists() and path.stat().st_size > 0 for path in checkpoint_files),
        "surface_files_nonzero": all(path.exists() and path.stat().st_size > 0 for path in surface_files),
        "surface_facet_cells_positive": all(int(float(row.get("facet_cell_count", "0"))) > 0 for row in surfaces) if surfaces else False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, action="append", default=[], help="Run directory to validate.")
    parser.add_argument("--reference", type=Path, help="Uninterrupted reference run directory.")
    parser.add_argument("--restart", type=Path, help="Restart/continuation run directory.")
    parser.add_argument("--tolerance", type=float, default=1e-10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result: dict[str, object] = {
        "run_validations": [validate_run_dir(path) for path in args.run_dir],
        "comparison": None,
    }
    if args.reference and args.restart:
        result["comparison"] = compare_runs(args.reference, args.restart, args.tolerance)

    result["passed"] = all(
        item["visual_frames"]["unique_indices"]
        and item["visual_frames"]["monotone_indices"]
        and item["visual_frames"]["monotone_times"]
        and item["checkpoint_files_nonzero"]
        for item in result["run_validations"]
    )
    if result["comparison"] is not None:
        result["passed"] = bool(result["passed"] and result["comparison"]["passed"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"CHECKPOINT_POSTPROCESS_SUMMARY={args.output}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
