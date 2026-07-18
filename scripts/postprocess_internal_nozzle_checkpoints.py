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
from collections import Counter
from pathlib import Path

from validate_internal_nozzle_checkpoint_v4 import validate as validate_checkpoint_v4


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

CHECKPOINT_COMMON_COLUMNS = (
    "case_id",
    "domain_mode",
    "checkpoint_index",
    "t",
    "i",
    "maxlevel",
    "filename",
    "parent_checkpoint",
    "source_sha256",
    "schedule_version",
    "schedule_sha256",
    "master_tick",
    "target_time",
    "actual_time",
    "metadata_file",
)
CHECKPOINT_STATE_COLUMN = {
    "legacy_face_state": "face_velocity_state_file",
    "v4": "prediction_closure_state_file",
}
CHECKPOINT_METADATA_SCHEMA = {
    "legacy_face_state": (
        "internal_nozzle_checkpoint_metadata_v1",
        "internal_nozzle_checkpoint_metadata_v2",
        "internal_nozzle_checkpoint_metadata_v3",
    ),
    "v4": "internal_nozzle_checkpoint_metadata_v4",
}
LEGACY_BASIC_COLUMNS = CHECKPOINT_COMMON_COLUMNS[:8]
LEGACY_PROFILE_COLUMNS = (
    "case_id",
    "profile_mode",
    "checkpoint_index",
    "t",
    "i",
    "maxlevel",
    "filename",
    "parent_checkpoint",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_checkpoint_index(path: Path) -> tuple[str, list[dict[str, str]]]:
    """Read a checkpoint index by unique field name and fail closed on schema drift."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("empty checkpoint index") from exc
        duplicates = [name for name, count in Counter(header).items() if count > 1]
        if duplicates:
            raise ValueError(f"duplicate checkpoint-index column: {duplicates[0]}")
        state_columns = [name for name in CHECKPOINT_STATE_COLUMN.values() if name in header]
        if len(state_columns) > 1:
            raise ValueError("mixed checkpoint-index schema state columns")
        if state_columns:
            schema_version = next(
                version
                for version, name in CHECKPOINT_STATE_COLUMN.items()
                if name == state_columns[0]
            )
            expected_columns = (*CHECKPOINT_COMMON_COLUMNS, CHECKPOINT_STATE_COLUMN[schema_version])
        elif set(header) == set(LEGACY_BASIC_COLUMNS):
            schema_version = "legacy_basic"
            expected_columns = LEGACY_BASIC_COLUMNS
        elif set(header) == set(LEGACY_PROFILE_COLUMNS):
            schema_version = "legacy_profile"
            expected_columns = LEGACY_PROFILE_COLUMNS
        elif set(header) == set(CHECKPOINT_COMMON_COLUMNS):
            schema_version = "metadata_declared_without_state"
            expected_columns = CHECKPOINT_COMMON_COLUMNS
        else:
            raise ValueError("missing checkpoint-index schema state column")
        expected = set(expected_columns)
        unknown = [name for name in header if name not in expected]
        if unknown:
            raise ValueError(f"unknown checkpoint-index column: {unknown[0]}")
        missing = [
            name
            for name in expected_columns
            if name not in header
        ]
        if missing:
            raise ValueError(f"missing checkpoint-index column: {missing[0]}")
        rows: list[dict[str, str]] = []
        for line_number, values in enumerate(reader, start=2):
            if len(values) != len(header):
                raise ValueError(f"checkpoint-index row width mismatch at line {line_number}")
            rows.append(dict(zip(header, values, strict=True)))
    if schema_version == "metadata_declared_without_state":
        declared = {
            read_checkpoint_metadata(Path(row["metadata_file"])).get("schema") for row in rows
        }
        if "internal_nozzle_checkpoint_metadata_v4" in declared:
            if len(declared) != 1:
                raise ValueError("mixed declared checkpoint metadata schemas")
            raise ValueError("missing checkpoint-index schema state column")
        allowed_legacy = {
            "internal_nozzle_checkpoint_metadata_v1",
            "internal_nozzle_checkpoint_metadata_v2",
            "internal_nozzle_checkpoint_metadata_v3",
        }
        if not declared or not declared <= allowed_legacy:
            raise ValueError("unknown declared checkpoint metadata schema")
        schema_version = "legacy_metadata_only"
    return schema_version, rows


def read_checkpoint_metadata(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if "=" not in line:
            raise ValueError(f"malformed checkpoint metadata line {line_number}: {path}")
        key, value = line.split("=", 1)
        if not key or key in values:
            raise ValueError(f"duplicate or empty checkpoint metadata key at line {line_number}: {path}")
        values[key] = value
    return values


def require_absolute_nonzero(path_value: str, label: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        raise ValueError(f"{label} is not an absolute checkpoint identity: {path_value}")
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"{label} is missing or empty: {path_value}")
    return path


def require_metadata_identity(
    row: dict[str, str], metadata: dict[str, str], schema_version: str
) -> None:
    expected = {
        "case_id": row["case_id"],
        "source_sha256": row["source_sha256"],
        "schedule_version": row["schedule_version"],
        "schedule_sha256": row["schedule_sha256"],
        "master_tick": row["master_tick"],
        "iteration": row["i"],
        "maxlevel": row["maxlevel"],
        "restored_from": row["parent_checkpoint"],
    }
    state_column = CHECKPOINT_STATE_COLUMN[schema_version]
    allowed_schema = CHECKPOINT_METADATA_SCHEMA[schema_version]
    schema_valid = (
        metadata.get("schema") in allowed_schema
        if isinstance(allowed_schema, tuple)
        else metadata.get("schema") == allowed_schema
    )
    if not schema_valid:
        raise ValueError(
            f"checkpoint metadata schema mismatch: schema expected {allowed_schema!r}, got {metadata.get('schema')!r}"
        )
    state_key = (
        "face_velocity_state"
        if schema_version == "legacy_face_state"
        else "prediction_closure_state"
    )
    expected[state_key] = row[state_column]
    if schema_version == "v4":
        expected["prediction_closure_schema"] = "internal_nozzle_prediction_closure_v4"
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(
                f"checkpoint metadata schema mismatch: {key} expected {value!r}, got {metadata.get(key)!r}"
            )
    for key in ("target_time", "actual_time"):
        if not math.isclose(float(metadata[key]), float(row[key]), rel_tol=0.0, abs_tol=1e-15):
            raise ValueError(f"checkpoint metadata identity mismatch: {key}")


def validate_parent_identity(row: dict[str, str], schema_version: str) -> dict[str, object]:
    parent_value = row["parent_checkpoint"]
    if parent_value == "fresh":
        return {"kind": "fresh", "exact_identity": True}
    parent = require_absolute_nonzero(parent_value, "parent checkpoint")
    parent_run_dir = parent.parent.parent
    parent_schema, parent_rows = read_checkpoint_index(parent_run_dir / "checkpoint_index.csv")
    if parent_schema != schema_version:
        raise ValueError("parent checkpoint schema version mismatch")
    matches = [item for item in parent_rows if item["filename"] == parent_value]
    if len(matches) != 1:
        raise ValueError("parent checkpoint exact identity is absent or ambiguous")
    parent_row = matches[0]
    parent_metadata_path = require_absolute_nonzero(parent_row["metadata_file"], "parent metadata")
    parent_metadata = read_checkpoint_metadata(parent_metadata_path)
    require_metadata_identity(parent_row, parent_metadata, parent_schema)
    state_column = CHECKPOINT_STATE_COLUMN[parent_schema]
    parent_state = require_absolute_nonzero(parent_row[state_column], "parent checkpoint state")
    if parent_schema == "v4":
        validate_checkpoint_v4(parent_state)
    return {
        "kind": "checkpoint",
        "exact_identity": True,
        "checkpoint_index": int(parent_row["checkpoint_index"]),
        "filename": parent_value,
        "metadata_file": str(parent_metadata_path),
        "state_file": str(parent_state),
    }


def validate_checkpoint_records(
    rows: list[dict[str, str]], schema_version: str
) -> list[dict[str, object]]:
    validations: list[dict[str, object]] = []
    for row in rows:
        dump = require_absolute_nonzero(row["filename"], "checkpoint dump")
        metadata_path = require_absolute_nonzero(row["metadata_file"], "checkpoint metadata")
        state_column = CHECKPOINT_STATE_COLUMN[schema_version]
        state = require_absolute_nonzero(row[state_column], "checkpoint state")
        metadata = read_checkpoint_metadata(metadata_path)
        require_metadata_identity(row, metadata, schema_version)
        parent = validate_parent_identity(row, schema_version)
        container: dict[str, object] | None = None
        if schema_version == "v4":
            container = validate_checkpoint_v4(state)
            expected_container = {
                "source_sha256": row["source_sha256"],
                "schedule_version": row["schedule_version"],
                "schedule_sha256": row["schedule_sha256"],
                "iteration": int(row["i"]),
                "grid_maxdepth": int(row["maxlevel"]),
            }
            for key, value in expected_container.items():
                if container.get(key) != value:
                    raise ValueError(f"v4 checkpoint container provenance mismatch: {key}")
            if not math.isclose(
                float(container["checkpoint_t"]), float(row["actual_time"]), rel_tol=0.0, abs_tol=1e-15
            ):
                raise ValueError("v4 checkpoint container provenance mismatch: checkpoint_t")
        item: dict[str, object] = {
            "dump": str(dump),
            "metadata": str(metadata_path),
            "schema_version": schema_version,
            "state_file": str(state),
            "parent_checkpoint": parent,
            "valid": True,
        }
        if container is not None:
            item["prediction_closure_validation"] = container
        validations.append(item)
    return validations


def reconstruct_checkpoint_manifest(
    rows: list[dict[str, str]], schema_version: str, validations: list[dict[str, object]]
) -> dict[str, object]:
    if not rows:
        raise ValueError("cannot reconstruct checkpoint manifest from an empty index")
    indexed = [
        (int(row["checkpoint_index"]), row, validation)
        for row, validation in zip(rows, validations, strict=True)
    ]
    if len({item[0] for item in indexed}) != len(indexed):
        raise ValueError("duplicate checkpoint identity")
    latest_index, latest_row, latest_validation = max(indexed, key=lambda item: item[0])
    chain = []
    for index, row, validation in indexed:
        chain.append(
            {
                "checkpoint_index": index,
                "time": float(row["t"]),
                "iteration": int(row["i"]),
                "maxlevel": int(row["maxlevel"]),
                "domain_mode": row["domain_mode"],
                "filename": row["filename"],
                "metadata_file": row["metadata_file"],
                "state_file": row[CHECKPOINT_STATE_COLUMN[schema_version]],
                "parent_checkpoint": validation["parent_checkpoint"],
                "verified_nonzero": True,
            }
        )
    return {
        "schema": f"internal_nozzle_checkpoint_manifest_{schema_version}_validation_v1",
        "case_id": latest_row["case_id"],
        "checkpoint_restore_supported": True,
        "latest_valid_checkpoint": {
            "checkpoint_index": latest_index,
            "filename": latest_row["filename"],
            "metadata_file": latest_row["metadata_file"],
            "state_file": latest_row[CHECKPOINT_STATE_COLUMN[schema_version]],
            "exact_identity": bool(latest_validation["valid"]),
        },
        "provenance_chain": chain,
        "checkpoint_count": len(chain),
        "latest_checkpoint_file": latest_row["filename"],
    }


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
    checkpoint_schema, checkpoints = read_checkpoint_index(run_dir / "checkpoint_index.csv")
    checkpoint_validations = (
        validate_checkpoint_records(checkpoints, checkpoint_schema)
        if checkpoint_schema in ("legacy_face_state", "v4")
        else []
    )
    checkpoint_files = [checkpoint_path(run_dir, row["filename"]) for row in checkpoints if row.get("filename")]
    surface_files = [run_dir / row["filename"] for row in surfaces if row.get("filename")]
    result: dict[str, object] = {
        "run_dir": str(run_dir),
        "visual_frames": validate_sequence(visual, "frame_index"),
        "surfaces": validate_sequence(surfaces, "surface_index"),
        "checkpoints": validate_sequence(checkpoints, "checkpoint_index"),
        "checkpoint_files_nonzero": all(path.exists() and path.stat().st_size > 0 for path in checkpoint_files),
        "surface_files_nonzero": all(path.exists() and path.stat().st_size > 0 for path in surface_files),
        "surface_facet_cells_positive": all(int(float(row.get("facet_cell_count", "0"))) > 0 for row in surfaces) if surfaces else False,
    }
    if checkpoint_schema == "v4":
        result["checkpoint_schema"] = "internal_nozzle_checkpoint_metadata_v4"
        result["checkpoint_contract_valid"] = all(item["valid"] for item in checkpoint_validations)
        result["reconstructed_checkpoint_manifest"] = reconstruct_checkpoint_manifest(
            checkpoints, checkpoint_schema, checkpoint_validations
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, action="append", default=[], help="Run directory to validate.")
    parser.add_argument("--reference", type=Path, help="Uninterrupted reference run directory.")
    parser.add_argument("--restart", type=Path, help="Restart/continuation run directory.")
    parser.add_argument("--tolerance", type=float, default=1e-10)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest-output",
        type=Path,
        help="Write the reconstructed named-column manifest for one v4 run.",
    )
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
        and item.get("checkpoint_contract_valid", True)
        for item in result["run_validations"]
    )
    if result["comparison"] is not None:
        result["passed"] = bool(result["passed"] and result["comparison"]["passed"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.manifest_output:
        if len(result["run_validations"]) != 1:
            raise ValueError("--manifest-output requires exactly one --run-dir")
        manifest = result["run_validations"][0].get("reconstructed_checkpoint_manifest")
        if manifest is None:
            raise ValueError("--manifest-output is supported only for a v4 checkpoint index")
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"CHECKPOINT_POSTPROCESS_SUMMARY={args.output}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
