#!/usr/bin/env python3
"""Validate Task 04 internal-nozzle field, frame, and restart contracts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path


PRESSURE_PROVENANCE = "runtime_cell_centered_p_after_centered_projection"
EVENT_PROVENANCE = "post_projection_fields_i_plus_plus_last_after_centered_projection"
FIELD_COLUMNS = {
    "f",
    "ux",
    "uy",
    "uz",
    "velocity_magnitude",
    "vorticity_magnitude",
    "p",
    "pressure_provenance",
    "event_provenance",
    "gravity_enabled",
}
FIELD_NAME = re.compile(r"^field_t\d+\.\d{6}_i\d{7}_f\d{4}\.csv$")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def finite(row: dict[str, str], key: str) -> bool:
    try:
        return math.isfinite(float(row.get(key, "")))
    except (TypeError, ValueError):
        return False


def sequence_ok(rows: list[dict[str, str]], key: str) -> bool:
    try:
        values = [int(row[key]) for row in rows]
    except (KeyError, TypeError, ValueError):
        return False
    return values == list(range(values[0], values[0] + len(values))) if values else False


def checkpoint_path(run_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path
    return run_dir / "checkpoints" / path.name


def validate_run(run_dir: Path, require_checkpoints: bool, require_facets: bool) -> dict[str, object]:
    contract_path = run_dir / "field_export_contract.json"
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        contract = {}
    manifest = read_csv(run_dir / "field_frame_manifest.csv")
    raw = read_csv(run_dir / "raw_frame_summary.csv")
    raw_keys = {(round(float(row["t"]), 12), int(row["i"])) for row in raw if row.get("t") and row.get("i")}

    frame_checks: list[dict[str, object]] = []
    for row in manifest:
        field_path = run_dir / row.get("filename", "")
        records = read_csv(field_path)
        headers = set(records[0]) if records else set()
        matched_raw = False
        if finite(row, "t") and row.get("i", ""):
            matched_raw = (round(float(row["t"]), 12), int(row["i"])) in raw_keys
        frame_checks.append(
            {
                "filename": row.get("filename"),
                "filename_valid": bool(FIELD_NAME.match(field_path.name)),
                "exists_nonzero": field_path.exists() and field_path.stat().st_size > 0,
                "sample_count_matches": len(records) == int(row.get("sample_count", "-1")),
                "required_columns_present": FIELD_COLUMNS <= headers,
                "pressure_range_finite_positive": finite(row, "p_range") and float(row["p_range"]) > 1e-12,
                "pressure_nonzero": row.get("pressure_nonzero") == "1",
                "pressure_provenance_valid": row.get("pressure_provenance") == PRESSURE_PROVENANCE,
                "event_provenance_valid": row.get("event_provenance") == EVENT_PROVENANCE,
                "gravity_off": row.get("gravity_enabled") == "0",
                "matched_station_frame": matched_raw,
            }
        )

    checkpoints = read_csv(run_dir / "checkpoint_index.csv")
    checkpoint_files = [checkpoint_path(run_dir, row["filename"]) for row in checkpoints if row.get("filename")]
    surfaces = read_csv(run_dir / "surface_manifest.csv")
    surface_files = [run_dir / row["filename"] for row in surfaces if row.get("filename")]
    all_frame_checks = bool(frame_checks) and all(all(item.values()) for item in frame_checks)
    checkpoint_ok = bool(checkpoint_files) and all(path.exists() and path.stat().st_size > 0 for path in checkpoint_files)
    facets_ok = bool(surface_files) and all(path.exists() and path.stat().st_size > 0 for path in surface_files)
    facets_ok = facets_ok and all(int(row.get("facet_cell_count", "0")) > 0 for row in surfaces)

    result = {
        "run_dir": str(run_dir),
        "contract_valid": (
            contract.get("schema") == "internal_nozzle_post_projection_fields_v1"
            and contract.get("pressure_provenance") == PRESSURE_PROVENANCE
            and contract.get("event_provenance") == EVENT_PROVENANCE
            and contract.get("gravity_enabled") is False
            and contract.get("instrumentation_changes_solver_state") is False
        ),
        "field_frame_sequence_valid": sequence_ok(manifest, "field_frame_index"),
        "field_frames": frame_checks,
        "checkpoint_files_nonzero": checkpoint_ok,
        "surface_files_nonzero_and_positive": facets_ok,
        "pressure_decision": "valid_runtime_nonzero" if all_frame_checks else "blocked",
    }
    result["passed"] = bool(
        result["contract_valid"]
        and result["field_frame_sequence_valid"]
        and all_frame_checks
        and (checkpoint_ok or not require_checkpoints)
        and (facets_ok or not require_facets)
    )
    return result


def compare_runs(reference: Path, restart: Path, tolerance: float) -> dict[str, object]:
    ref_rows = read_csv(reference / "field_frame_manifest.csv")
    rst_rows = read_csv(restart / "field_frame_manifest.csv")
    ref = {round(float(row["t"]), 12): row for row in ref_rows}
    rst = {round(float(row["t"]), 12): row for row in rst_rows}
    common = sorted(set(ref) & set(rst))
    checks: list[dict[str, object]] = []
    for key in common:
        pressure_scale = max(1.0, abs(float(ref[key]["p_range"])))
        deltas = {
            field: {
                "absolute": abs(float(ref[key][field]) - float(rst[key][field])),
                "normalized": abs(float(ref[key][field]) - float(rst[key][field]))
                / (pressure_scale if field in {"p_min", "p_max", "p_range"} else max(1.0, abs(float(ref[key][field])))),
            }
            for field in ("p_min", "p_max", "p_range", "velocity_magnitude_max", "vorticity_magnitude_max")
        }
        checks.append({"time": key, "deltas": deltas, "passed": all(value["normalized"] <= tolerance for value in deltas.values())})
    return {"matched_frames": len(common), "checks": checks, "passed": bool(common) and all(item["passed"] for item in checks)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, action="append", default=[])
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--restart", type=Path)
    parser.add_argument("--tolerance", type=float, default=1e-10)
    parser.add_argument("--require-checkpoints", action="store_true")
    parser.add_argument("--require-facets", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result: dict[str, object] = {
        "run_validations": [validate_run(path, args.require_checkpoints, args.require_facets) for path in args.run_dir],
        "restart_comparison": None,
    }
    if args.reference and args.restart:
        result["restart_comparison"] = compare_runs(args.reference, args.restart, args.tolerance)
    result["passed"] = all(item["passed"] for item in result["run_validations"])
    if result["restart_comparison"] is not None:
        result["passed"] = bool(result["passed"] and result["restart_comparison"]["passed"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"INTERNAL_NOZZLE_INSTRUMENTATION_VALIDATION={args.output}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
