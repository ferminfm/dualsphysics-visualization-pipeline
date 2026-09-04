#!/usr/bin/env python3
"""Validate canonical internal-nozzle output and exact restart equivalence."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Iterable

from postprocess_internal_nozzle_checkpoints import (
    reconstruct_checkpoint_manifest,
    read_checkpoint_index,
    validate_checkpoint_records,
)


PRESSURE_PROVENANCE = "runtime_cell_centered_p_after_centered_projection"
EVENT_PROVENANCE = "canonical_master_tick_post_projection_i_plus_plus_last"
FIELD_COLUMNS = ("f", "ux", "uy", "uz", "velocity_magnitude", "vorticity_magnitude", "p", "cs")
SCALAR_COLUMNS = (
    "mean_exit_velocity",
    "exit_flow",
    "exit_liquid_area",
    "liquid_volume",
    "liquid_mass_balance_relative_error",
    "active_front",
    "interface_proxy",
    "interface_growth",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def finite(value: str | float | int) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def normalized_delta(a: float, b: float) -> float:
    return abs(a - b) / max(1.0, abs(a), abs(b))


def tier_selected(tick: int, base: int, dense: int, dense_start: int, dense_end: int) -> bool:
    return tick % base == 0 or (dense_start <= tick <= dense_end and tick % dense == 0)


def load_contract(run_dir: Path) -> dict[str, object]:
    return json.loads((run_dir / "run_schedule_contract.json").read_text(encoding="utf-8"))


def validate_manifest_rows(
    rows: list[dict[str, str]],
    contract: dict[str, object],
    tier: str,
    end_tick: int,
    restart_tick: int | None,
) -> dict[str, object]:
    tick_dt = float(contract["master_tick_dt"])
    tolerance = float(contract["event_time_tolerance"])
    dense = contract["dense_window"]
    if tier == "lightweight":
        policy = contract["lightweight"]
        selected = lambda tick: tier_selected(
            tick, int(policy["base_stride"]), int(policy["dense_stride"]),
            int(dense["start_tick"]), int(dense["end_tick"])
        )
    elif tier == "full_field":
        policy = contract["full_field"]
        selected = lambda tick: tier_selected(
            tick, int(policy["base_stride"]), int(policy["dense_stride"]),
            int(dense["start_tick"]), int(dense["end_tick"])
        )
    elif tier == "checkpoint":
        selected = lambda tick: tick > 0 and tick % int(contract["checkpoint_stride"]) == 0
    else:
        raise ValueError(tier)

    expected = [
        tick for tick in range(end_tick + 1)
        if selected(tick) and (restart_tick is None or tick > restart_tick)
    ]
    actual = [int(row["master_tick"]) for row in rows]
    identity_ok = all(
        row.get("schedule_version") == contract["schedule_version"]
        and row.get("schedule_sha256") == contract["schedule_sha256"]
        and row.get("source_sha256") == contract["source_sha256"]
        for row in rows
    )
    timing_ok = all(
        abs(float(row["target_time"]) - int(row["master_tick"]) * tick_dt) <= tolerance
        and abs(float(row["actual_time"]) - float(row["target_time"])) <= tolerance
        and abs(float(row["t"]) - float(row["target_time"])) <= tolerance
        for row in rows
    )
    return {
        "tier": tier,
        "expected_ticks": expected,
        "actual_ticks": actual,
        "exact_tick_sequence": actual == expected,
        "identity_valid": identity_ok,
        "timing_valid": timing_ok,
        "passed": actual == expected and identity_ok and timing_ok,
    }


def validate_run(run_dir: Path) -> dict[str, object]:
    contract = load_contract(run_dir)
    raw = read_csv(run_dir / "raw_frame_summary.csv")
    fields = read_csv(run_dir / "field_frame_manifest.csv")
    visuals = read_csv(run_dir / "visual_frame_manifest.csv")
    surfaces = read_csv(run_dir / "surface_manifest.csv")
    checkpoint_schema, checkpoints = read_checkpoint_index(run_dir / "checkpoint_index.csv")
    end_tick = max(int(row["master_tick"]) for row in raw)
    restart_tick: int | None = None
    lineage = raw[0].get("restart_lineage", "fresh") if raw else "fresh"
    if lineage and lineage != "fresh":
        meta = Path(lineage + ".meta")
        for line in meta.read_text(encoding="utf-8").splitlines():
            if line.startswith("master_tick="):
                restart_tick = int(line.split("=", 1)[1])
                break

    checks = {
        "raw": validate_manifest_rows(raw, contract, "lightweight", end_tick, restart_tick),
        "visuals": validate_manifest_rows(visuals, contract, "lightweight", end_tick, restart_tick),
        "surfaces": validate_manifest_rows(surfaces, contract, "lightweight", end_tick, restart_tick),
        "fields": validate_manifest_rows(fields, contract, "full_field", end_tick, restart_tick),
        "checkpoints": validate_manifest_rows(checkpoints, contract, "checkpoint", end_tick, restart_tick),
    }
    pressure_ok = all(
        row.get("pressure_nonzero") == "1"
        and finite(row.get("p_range", ""))
        and float(row["p_range"]) > 1e-12
        and row.get("pressure_provenance") == PRESSURE_PROVENANCE
        and row.get("event_provenance") == EVENT_PROVENANCE
        and row.get("gravity_enabled") == "0"
        for row in fields
    )
    field_files_ok = all(
        (run_dir / row["filename"]).is_file()
        and (run_dir / row["filename"]).stat().st_size > 0
        for row in fields
    )
    if checkpoint_schema not in ("legacy_face_state", "v4", "v5"):
        # Preserve the historical schedule-validator requirement and failure for
        # legacy indexes that predate the face-state column.
        checkpoints[0]["face_velocity_state_file"]
    checkpoint_validations = validate_checkpoint_records(checkpoints, checkpoint_schema)
    checkpoint_metadata: list[dict[str, object]] = []
    for item in checkpoint_validations:
        if checkpoint_schema == "legacy_face_state":
            checkpoint_metadata.append(
                {
                    "dump": item["dump"],
                    "metadata": item["metadata"],
                    "face_velocity_state": item["state_file"],
                    "valid": item["valid"],
                }
            )
        else:
            checkpoint_metadata.append(
                {
                    "dump": item["dump"],
                    "metadata": item["metadata"],
                    "prediction_closure_state": item["state_file"],
                    "prediction_closure_validation": item["prediction_closure_validation"],
                    "parent_checkpoint": item["parent_checkpoint"],
                    "valid": item["valid"],
                }
            )
    mass_errors = [float(row["liquid_mass_balance_relative_error"]) for row in raw]
    mass_tolerance = float(json.loads((run_dir / "raw_export_manifest.json").read_text())["mass_balance"]["tolerance"])
    mass_ok = bool(mass_errors) and all(finite(value) and value <= mass_tolerance for value in mass_errors)
    result = {
        "run_dir": str(run_dir),
        "schedule_contract": contract,
        "end_tick": end_tick,
        "restart_tick": restart_tick,
        "manifest_checks": checks,
        "field_pressure_valid": pressure_ok,
        "field_files_nonzero": field_files_ok,
        "checkpoint_metadata": checkpoint_metadata,
        "mass_balance": {
            "maximum_relative_error": max(mass_errors),
            "tolerance": mass_tolerance,
            "passed": mass_ok,
        },
    }
    if checkpoint_schema in ("v4", "v5"):
        result["checkpoint_schema"] = (
            checkpoint_validations[-1]["metadata_schema"]
            if checkpoint_validations else "not_applicable"
        )
        result["reconstructed_checkpoint_manifest"] = reconstruct_checkpoint_manifest(
            checkpoints, checkpoint_schema, checkpoint_validations
        )
    result["passed"] = bool(
        all(check["passed"] for check in checks.values())
        and pressure_ok
        and field_files_ok
        and all(item["valid"] for item in checkpoint_metadata)
        and mass_ok
    )
    return result


def rows_by_tick(path: Path) -> dict[int, dict[str, str]]:
    return {int(row["master_tick"]): row for row in read_csv(path)}


def compare_field_files(reference: Path, restart: Path, ref_row: dict[str, str], rst_row: dict[str, str]) -> dict[str, object]:
    ref_records = read_csv(reference / ref_row["filename"])
    rst_records = read_csv(restart / rst_row["filename"])
    keys = ("x", "y", "z", "Delta")
    ref_map = {tuple(row[key] for key in keys): row for row in ref_records}
    rst_map = {tuple(row[key] for key in keys): row for row in rst_records}
    maxima = {field: 0.0 for field in FIELD_COLUMNS}
    if set(ref_map) != set(rst_map):
        return {"same_grid": False, "max_normalized_delta": maxima, "passed": False}
    for key in ref_map:
        for field in FIELD_COLUMNS:
            delta = normalized_delta(float(ref_map[key][field]), float(rst_map[key][field]))
            maxima[field] = max(maxima[field], delta)
    passed = all(value <= 1e-8 for value in maxima.values())
    return {"same_grid": True, "max_normalized_delta": maxima, "tolerance": 1e-8, "passed": passed}


def compare_runs(reference: Path, restart: Path, minimum_matches: int) -> dict[str, object]:
    ref_fields = rows_by_tick(reference / "field_frame_manifest.csv")
    rst_fields = rows_by_tick(restart / "field_frame_manifest.csv")
    ref_raw = rows_by_tick(reference / "raw_frame_summary.csv")
    rst_raw = rows_by_tick(restart / "raw_frame_summary.csv")
    common = sorted(set(ref_fields) & set(rst_fields))
    comparisons: list[dict[str, object]] = []
    for tick in common:
        scalar_deltas = {
            name: normalized_delta(float(ref_raw[tick][name]), float(rst_raw[tick][name]))
            for name in SCALAR_COLUMNS
        }
        field_comparison = compare_field_files(reference, restart, ref_fields[tick], rst_fields[tick])
        comparisons.append(
            {
                "master_tick": tick,
                "target_time": float(ref_fields[tick]["target_time"]),
                "exact_target_match": ref_fields[tick]["target_time"] == rst_fields[tick]["target_time"],
                "scalar_max_normalized_delta": max(scalar_deltas.values()),
                "scalar_deltas": scalar_deltas,
                "scalar_tolerance": 1e-8,
                "field_comparison": field_comparison,
                "passed": (
                    ref_fields[tick]["target_time"] == rst_fields[tick]["target_time"]
                    and max(scalar_deltas.values()) <= 1e-8
                    and field_comparison["passed"]
                ),
            }
        )
    return {
        "matched_field_targets": len(common),
        "minimum_required": minimum_matches,
        "matched_master_ticks": common,
        "comparisons": comparisons,
        "passed": len(common) >= minimum_matches and all(item["passed"] for item in comparisons),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", action="append", type=Path, default=[])
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--restart", type=Path)
    parser.add_argument("--minimum-matches", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    run_results = [validate_run(path) for path in args.run_dir]
    comparison = None
    if args.reference and args.restart:
        comparison = compare_runs(args.reference, args.restart, args.minimum_matches)
    result = {
        "schema": "internal_nozzle_schedule_validation_v1",
        "predeclared_tolerances": {
            "event_time_absolute": "from schedule contract (1e-12 in Task 02 smoke)",
            "scalar_normalized": 1e-8,
            "field_normalized_Linf": 1e-8,
            "mass_balance_relative": "from run manifest (0.05 in Task 02 smoke)",
        },
        "run_validations": run_results,
        "restart_comparison": comparison,
    }
    result["passed"] = all(item["passed"] for item in run_results) and (
        comparison is None or comparison["passed"]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"INTERNAL_NOZZLE_SCHEDULE_VALIDATION={args.output}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
