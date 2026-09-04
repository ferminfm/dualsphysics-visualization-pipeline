#!/usr/bin/env python3
"""Fail-closed continuous-versus-restored precursor endpoint comparison.

The restored run is accepted only when its predecessor is a complete,
authenticated fresh split segment and that split agrees with the continuous
trajectory at the declared boundary. Merely naming predecessor files is not
enough.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable

from validate_internal_nozzle_checkpoint_v4 import validate as validate_closure_v4


CONTRACT_IDENTITY = (
    "case_id", "geometry_schema", "geometry_fingerprint", "source_commit",
    "source_sha256", "pressure_forcing", "density_liquid",
    "viscosity_liquid", "maxlevel", "baselevel", "delta_min_Dh",
    "accepted_physical_L7_delta_Dh", "dt_cap", "metric_stride",
    "target_template_sha256",
)
CELL_KEY = ("x", "y", "z", "Delta")
CELL_FIELDS = ("cs", "ux", "uy", "uz", "p")
HISTORY_FIELDS = (
    "Q_l", "mdot_l", "J_k", "pressure_drop", "exit_area", "U_bulk",
    "beta", "alpha", "mass_flow_imbalance", "profile_l2_change",
    "max_ux_change", "mgp_residual", "mgu_residual", "cell_count",
)
PLANE_FIELDS = ("area", "Q_l", "mdot_l", "J_k", "pressure_mean", "beta", "alpha")
CHECKPOINT_METADATA_KEYS = {
    "schema", "case_id", "geometry_fingerprint", "source_commit",
    "source_sha256", "maxlevel", "pressure_forcing", "density_liquid",
    "viscosity_liquid", "t", "t_star", "i", "solver_dt",
    "solver_dtmax", "timestep_previous", "previous_profile_available",
    "prediction_closure_schema", "prediction_closure_state",
}
PRECURSOR_SCHEDULE_VERSION = "internal_nozzle_precursor_schedule_v1"
PRECURSOR_SCHEDULE_SHA256 = (
    "3598151fc5833c68d778830532e9c90e5d451f0c08b44e5da95a11b2952dcd11"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"not a nonempty regular non-symlink file: {path}")
    return resolved


def file_record(path: Path) -> dict[str, object]:
    resolved = regular(path)
    return {
        "path": str(path),
        "resolved_path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def reject_duplicate_object_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(
        regular(path).read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_object_pairs,
    )
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def read_metadata(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(
        regular(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if "=" not in line:
            raise ValueError(f"malformed metadata line {line_number}: {path}")
        key, value = line.split("=", 1)
        if not key or key in result:
            raise ValueError(f"duplicate/empty metadata key at line {line_number}: {path}")
        result[key] = value
    return result


def read_csv(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    with regular(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"missing/duplicate CSV header: {path}")
        if any(field not in reader.fieldnames for field in required):
            raise ValueError(f"missing required CSV field: {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"empty CSV: {path}")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"malformed CSV row: {path}")
    return rows


def number(value: object, context: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"non-numeric {context}") from error
    if not math.isfinite(parsed):
        raise ValueError(f"nonfinite {context}")
    return parsed


def integer(value: object, context: str) -> int:
    parsed = number(value, context)
    result = int(parsed)
    if parsed != result:
        raise ValueError(f"non-integer {context}")
    return result


def same_number(left: object, right: object) -> bool:
    return math.isclose(
        number(left, "left"), number(right, "right"),
        rel_tol=64.0 * math.ulp(1.0), abs_tol=1e-15,
    )


def normalized_delta(left: float, right: float) -> float:
    return abs(left - right) / max(1.0, abs(left), abs(right))


def read_contract(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    root = root.resolve(strict=True)
    path = regular(root / "run_contract.json")
    if path.parent != root:
        raise ValueError("run contract must be a direct member of its run directory")
    payload = read_json(path)
    required = {
        "schema", "case_id", "geometry_schema", "geometry_fingerprint",
        "source_commit", "source_sha256", "pressure_forcing",
        "density_liquid", "viscosity_liquid", "maxlevel", "baselevel",
        "delta_min_Dh", "accepted_physical_L7_delta_Dh", "dt_cap",
        "metric_stride", "target_template", "restore_checkpoint",
        "restore_metadata",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"run contract is missing fields: {missing}")
    if payload["schema"] != "internal_nozzle_precursor_run_v1":
        raise ValueError("unsupported precursor run contract schema")
    for key in ("case_id", "geometry_schema", "geometry_fingerprint"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise ValueError(f"invalid run contract {key}")
    for key, length in (("source_commit", 40), ("source_sha256", 64)):
        value = payload[key]
        if not isinstance(value, str) or len(value) != length or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            raise ValueError(f"invalid run contract {key}")
    for key in (
        "pressure_forcing", "density_liquid", "viscosity_liquid",
        "delta_min_Dh", "accepted_physical_L7_delta_Dh", "dt_cap",
    ):
        payload[key] = number(payload[key], f"run contract {key}")
        if payload[key] <= 0.0:
            raise ValueError(f"non-positive run contract {key}")
    for key in ("maxlevel", "baselevel", "metric_stride"):
        payload[key] = integer(payload[key], f"run contract {key}")
        if payload[key] < 1:
            raise ValueError(f"non-positive run contract {key}")
    template_value = payload["target_template"]
    if not isinstance(template_value, str) or template_value == "not_applicable":
        raise ValueError("run contract requires a target template")
    template = regular(Path(template_value))
    payload["target_template"] = str(template)
    payload["target_template_sha256"] = sha256(template)
    for key in ("restore_checkpoint", "restore_metadata"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise ValueError(f"invalid run contract {key}")
    return payload, file_record(path)


def contract_identity(contract: dict[str, object]) -> tuple[object, ...]:
    return tuple(contract[key] for key in CONTRACT_IDENTITY)


def terminal(rows: list[dict[str, str]], context: str) -> dict[str, str]:
    times = [number(row["t"], f"{context}.t") for row in rows]
    terminal_time = max(times)
    selected = [row for row, value in zip(rows, times, strict=True)
                if value == terminal_time]
    if len(selected) != 1:
        raise ValueError(f"ambiguous terminal row: {context}")
    return selected[0]


def read_history(root: Path, expected_state: str) -> list[dict[str, str]]:
    required = ("case_id", "t", "t_star", "i", *HISTORY_FIELDS, "restart_state")
    rows = read_csv(root / "precursor_history.csv", required)
    if any(row["restart_state"] != expected_state for row in rows):
        raise ValueError(f"run history does not consistently declare {expected_state}")
    times = [number(row["t"], "history t") for row in rows]
    iterations = [integer(row["i"], "history i") for row in rows]
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("history times are not strictly increasing")
    if any(right <= left for left, right in zip(iterations, iterations[1:])):
        raise ValueError("history iterations are not strictly increasing")
    return rows


def validate_checkpoint(
    root: Path, contract: dict[str, object], endpoint: dict[str, str],
    closure_validator: Callable[[Path], dict[str, object]],
) -> dict[str, object]:
    dump = regular(root / "precursor-final.dump")
    metadata_path = regular(Path(str(dump) + ".meta"))
    closure = regular(Path(str(dump) + ".prediction-closure-v4"))
    metadata = read_metadata(metadata_path)
    if set(metadata) != CHECKPOINT_METADATA_KEYS:
        missing = sorted(CHECKPOINT_METADATA_KEYS - set(metadata))
        extra = sorted(set(metadata) - CHECKPOINT_METADATA_KEYS)
        raise ValueError(
            f"checkpoint metadata key-set mismatch missing={missing} extra={extra}"
        )
    expected_strings = {
        "schema": "internal_nozzle_precursor_checkpoint_v2",
        "case_id": contract["case_id"],
        "geometry_fingerprint": contract["geometry_fingerprint"],
        "source_commit": contract["source_commit"],
        "source_sha256": contract["source_sha256"],
        "prediction_closure_schema": "internal_nozzle_prediction_closure_v4",
        "prediction_closure_state": closure.name,
    }
    for key, expected in expected_strings.items():
        if metadata.get(key) != expected:
            raise ValueError(f"checkpoint metadata mismatch {key}: {root}")
    if integer(metadata["maxlevel"], "checkpoint maxlevel") != contract["maxlevel"]:
        raise ValueError(f"checkpoint metadata mismatch maxlevel: {root}")
    for key in ("pressure_forcing", "density_liquid", "viscosity_liquid"):
        if not same_number(metadata[key], contract[key]):
            raise ValueError(f"checkpoint metadata mismatch {key}: {root}")
    for key in ("t", "t_star"):
        if not same_number(metadata[key], endpoint[key]):
            raise ValueError(f"checkpoint metadata mismatch {key}: {root}")
    if integer(metadata["i"], "checkpoint i") != integer(endpoint["i"], "endpoint i"):
        raise ValueError(f"checkpoint metadata mismatch i: {root}")
    solver_dt = number(metadata["solver_dt"], "checkpoint solver_dt")
    solver_dtmax = number(metadata["solver_dtmax"], "checkpoint solver_dtmax")
    timestep_previous = number(
        metadata["timestep_previous"], "checkpoint timestep_previous"
    )
    if solver_dt <= 0.0 or solver_dtmax <= 0.0 or timestep_previous < 0.0:
        raise ValueError(f"invalid checkpoint timestep state: {root}")
    if integer(
        metadata["previous_profile_available"], "previous profile flag"
    ) not in {0, 1}:
        raise ValueError(f"invalid checkpoint previous profile flag: {root}")

    report = closure_validator(closure)
    if not isinstance(report, dict) or report.get("valid") is not True:
        raise ValueError(f"prediction closure validator did not return valid=true: {root}")
    expected_exact = {
        "source_sha256": contract["source_sha256"],
        "schedule_version": PRECURSOR_SCHEDULE_VERSION,
        "schedule_sha256": PRECURSOR_SCHEDULE_SHA256,
        "iteration": integer(endpoint["i"], "endpoint i"),
        "grid_maxdepth": contract["maxlevel"],
    }
    for key, expected in expected_exact.items():
        if report.get(key) != expected:
            raise ValueError(f"closure/metadata mismatch {key}: {root}")
    for key, expected in (
        ("checkpoint_t", endpoint["t"]),
        ("checkpoint_dt", solver_dt),
        ("checkpoint_dtmax", solver_dtmax),
        ("timestep_previous", timestep_previous),
    ):
        if not same_number(report.get(key), expected):
            raise ValueError(f"closure/metadata mismatch {key}: {root}")
    domain = report.get("domain")
    if not isinstance(domain, list) or len(domain) != 4:
        raise ValueError(f"invalid closure domain: {root}")
    x0, y0, z0, length = (number(value, "closure domain") for value in domain)
    if (
        length <= 0.0 or not same_number(x0, 0.0)
        or not same_number(y0, -0.5 * length)
        or not same_number(z0, -0.5 * length)
    ):
        raise ValueError(f"incompatible precursor closure domain: {root}")
    return {
        "members": {
            "dump": file_record(dump),
            "metadata": file_record(metadata_path),
            "prediction_closure": file_record(closure),
        },
        "metadata": metadata,
        "closure": report,
    }


def compare_keyed(
    left_rows: list[dict[str, str]], right_rows: list[dict[str, str]],
    key_fields: tuple[str, ...], value_fields: tuple[str, ...], context: str,
) -> dict[str, object]:
    def index(
        rows: list[dict[str, str]], side: str,
    ) -> dict[tuple[str, ...], dict[str, str]]:
        result: dict[tuple[str, ...], dict[str, str]] = {}
        for row in rows:
            key = tuple(row[field] for field in key_fields)
            if key in result:
                raise ValueError(f"duplicate {context} key on {side}: {key}")
            result[key] = row
        return result

    left, right = index(left_rows, "left"), index(right_rows, "right")
    maxima = {field: 0.0 for field in value_fields}
    for key in left.keys() & right.keys():
        for field in value_fields:
            a = number(left[key][field], f"{context}.{field}")
            b = number(right[key][field], f"{context}.{field}")
            maxima[field] = max(maxima[field], normalized_delta(a, b))
    return {
        "left_count": len(left),
        "right_count": len(right),
        "left_only": sorted(left.keys() - right.keys()),
        "right_only": sorted(right.keys() - left.keys()),
        "maximum_normalized_delta": maxima,
        "overall_maximum": max(maxima.values()),
    }


def compare_rows(
    left: dict[str, str], right: dict[str, str], fields: tuple[str, ...],
) -> dict[str, object]:
    differences = {
        field: normalized_delta(number(left[field], field), number(right[field], field))
        for field in fields
    }
    return {
        "maximum_normalized_delta": differences,
        "overall_maximum": max(differences.values()),
    }


def validate_split_lineage(
    continuous: Path, restored: Path, continuous_contract: dict[str, object],
    restored_contract: dict[str, object], continuous_rows: list[dict[str, str]],
    restored_rows: list[dict[str, str]], tolerance: float,
    closure_validator: Callable[[Path], dict[str, object]],
) -> dict[str, object]:
    checkpoint_value = restored_contract["restore_checkpoint"]
    metadata_value = restored_contract["restore_metadata"]
    if checkpoint_value == "not_applicable" or metadata_value == "not_applicable":
        raise ValueError("restored run has no predecessor checkpoint")
    checkpoint = regular(Path(str(checkpoint_value)))
    metadata = regular(Path(str(metadata_value)))
    expected_metadata = regular(Path(str(checkpoint) + ".meta"))
    if checkpoint.name != "precursor-final.dump" or metadata != expected_metadata:
        raise ValueError(
            "restored predecessor is not an exact precursor checkpoint/sidecar pair"
        )
    split_root = checkpoint.parent
    if split_root in {continuous.resolve(strict=True), restored.resolve(strict=True)}:
        raise ValueError("split predecessor must be a distinct completed run directory")
    split_contract, split_contract_record = read_contract(split_root)
    if contract_identity(split_contract) != contract_identity(continuous_contract):
        raise ValueError("split predecessor contract does not match continuous identity")
    if contract_identity(split_contract) != contract_identity(restored_contract):
        raise ValueError("split predecessor contract does not match restored identity")
    if (
        split_contract["restore_checkpoint"] != "not_applicable"
        or split_contract["restore_metadata"] != "not_applicable"
    ):
        raise ValueError("split predecessor must be a fresh trajectory")
    split_rows = read_history(split_root, "fresh")
    split_terminal = terminal(split_rows, "split predecessor history")
    split_checkpoint = validate_checkpoint(
        split_root, split_contract, split_terminal, closure_validator
    )

    restored_first = restored_rows[0]
    if (
        not same_number(restored_first["t"], split_terminal["t"])
        or integer(restored_first["i"], "restored first i")
        != integer(split_terminal["i"], "split terminal i")
    ):
        raise ValueError(
            "restored history does not begin at the authenticated split endpoint"
        )
    boundary_comparison = compare_rows(
        split_terminal, restored_first, ("t_star", *HISTORY_FIELDS)
    )
    if boundary_comparison["overall_maximum"] > tolerance:
        raise ValueError("restored boundary differs from authenticated split endpoint")

    matching_continuous = [
        row for row in continuous_rows
        if same_number(row["t"], split_terminal["t"])
        and integer(row["i"], "continuous i")
        == integer(split_terminal["i"], "split i")
    ]
    if len(matching_continuous) != 1:
        raise ValueError("continuous history lacks one exact split t/i sample")
    continuous_split_comparison = compare_rows(
        matching_continuous[0], split_terminal, ("t_star", *HISTORY_FIELDS)
    )
    if continuous_split_comparison["overall_maximum"] > tolerance:
        raise ValueError("fresh split endpoint differs from continuous trajectory")
    if number(split_terminal["t"], "split t") >= number(
        terminal(continuous_rows, "continuous history")["t"],
        "continuous terminal t",
    ):
        raise ValueError("split checkpoint is not earlier than comparison endpoint")
    return {
        "kind": "authenticated_fresh_split_checkpoint",
        "run_directory": str(split_root),
        "run_contract": split_contract_record,
        "checkpoint": split_checkpoint,
        "split_t": number(split_terminal["t"], "split t"),
        "split_t_star": number(split_terminal["t_star"], "split t_star"),
        "split_iteration": integer(split_terminal["i"], "split i"),
        "restored_boundary_comparison": boundary_comparison,
        "continuous_split_comparison": continuous_split_comparison,
    }


def compare_runs(
    continuous: Path, restored: Path, tolerance: float,
    closure_validator: Callable[[Path], dict[str, object]] = validate_closure_v4,
) -> dict[str, object]:
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("relative tolerance must be finite and positive")
    continuous = continuous.resolve(strict=True)
    restored = restored.resolve(strict=True)
    if continuous == restored:
        raise ValueError("continuous and restored directories must differ")
    left_contract, left_contract_record = read_contract(continuous)
    right_contract, right_contract_record = read_contract(restored)
    contract_match = contract_identity(left_contract) == contract_identity(right_contract)
    if not contract_match:
        raise ValueError("continuous and restored contracts do not share one identity")
    if (
        left_contract["restore_checkpoint"] != "not_applicable"
        or left_contract["restore_metadata"] != "not_applicable"
    ):
        raise ValueError("continuous comparison run must be fresh")

    left_history_rows = read_history(continuous, "fresh")
    right_history_rows = read_history(restored, "restored")
    left_history = terminal(left_history_rows, "continuous history")
    right_history = terminal(right_history_rows, "restored history")
    left_checkpoint = validate_checkpoint(
        continuous, left_contract, left_history, closure_validator
    )
    right_checkpoint = validate_checkpoint(
        restored, right_contract, right_history, closure_validator
    )
    metadata_match = all(
        left_checkpoint["metadata"].get(key)
        == right_checkpoint["metadata"].get(key)
        for key in (
            "case_id", "geometry_fingerprint", "source_commit",
            "source_sha256", "maxlevel", "pressure_forcing",
            "density_liquid", "viscosity_liquid", "t", "t_star", "i",
        )
    )

    predecessor = validate_split_lineage(
        continuous, restored, left_contract, right_contract,
        left_history_rows, right_history_rows, tolerance, closure_validator,
    )
    left_cells = read_csv(
        continuous / "precursor-transfer-cells.csv", CELL_KEY + CELL_FIELDS
    )
    right_cells = read_csv(
        restored / "precursor-transfer-cells.csv", CELL_KEY + CELL_FIELDS
    )
    cells = compare_keyed(left_cells, right_cells, CELL_KEY, CELL_FIELDS, "cells")
    histories = compare_rows(
        left_history, right_history, ("t", "t_star", *HISTORY_FIELDS)
    )
    if integer(left_history["i"], "left terminal i") != integer(
        right_history["i"], "right terminal i"
    ):
        raise ValueError("continuous/restored terminal iterations differ")
    left_planes_all = read_csv(
        continuous / "precursor_plane_history.csv",
        ("t", "i", "plane_label") + PLANE_FIELDS,
    )
    right_planes_all = read_csv(
        restored / "precursor_plane_history.csv",
        ("t", "i", "plane_label") + PLANE_FIELDS,
    )
    lt = number(left_history["t"], "left terminal t")
    rt = number(right_history["t"], "right terminal t")
    left_planes = [row for row in left_planes_all if same_number(row["t"], lt)]
    right_planes = [row for row in right_planes_all if same_number(row["t"], rt)]
    planes = compare_keyed(
        left_planes, right_planes, ("plane_label",), PLANE_FIELDS, "planes"
    )
    passed = bool(
        metadata_match
        and not cells["left_only"] and not cells["right_only"]
        and cells["overall_maximum"] <= tolerance
        and histories["overall_maximum"] <= tolerance
        and not planes["left_only"] and not planes["right_only"]
        and planes["overall_maximum"] <= tolerance
    )
    return {
        "schema": "internal_nozzle_precursor_restart_comparison_v2",
        "tolerance": tolerance,
        "contract_identity_match": contract_match,
        "run_contracts": {
            "continuous": left_contract_record,
            "restored": right_contract_record,
        },
        "checkpoint_metadata_identity_match": metadata_match,
        "restored_predecessor": predecessor,
        "continuous_checkpoint": left_checkpoint,
        "restored_checkpoint": right_checkpoint,
        "cells": cells,
        "history": histories,
        "planes": planes,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continuous-dir", type=Path, required=True)
    parser.add_argument("--restored-dir", type=Path, required=True)
    parser.add_argument("--relative-tolerance", type=float, default=1e-8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("a new output path is required")
    payload = compare_runs(
        args.continuous_dir, args.restored_dir, args.relative_tolerance
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, args.output)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
