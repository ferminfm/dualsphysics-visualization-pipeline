#!/usr/bin/env python3
"""Classify steady-precursor convergence from sequential segment histories.

The scientific thresholds are fixed by the Layer 1 Task 03 contract.  Solver
and cell-population bounds are deliberately supplied by the caller so this
reducer does not invent or loosen an operational safety contract.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from validate_internal_nozzle_checkpoint_v4 import validate as validate_closure_v4


SCHEMA = "internal_nozzle_precursor_convergence_v1"
REQUIRED_COLUMNS = {
    "case_id",
    "t",
    "t_star",
    "i",
    "Q_l",
    "J_k",
    "pressure_drop",
    "mass_flow_imbalance",
    "profile_l2_change",
    "mgp_iterations",
    "mgu_iterations",
    "mgp_residual",
    "mgu_residual",
    "cell_count",
    "restart_state",
}
CORE_THRESHOLDS = {
    "Q_l": 0.001,
    "J_k": 0.002,
    "pressure_drop": 0.001,
}
PROFILE_L2_LIMIT = 0.005
MASS_IMBALANCE_LIMIT = 0.005
CONTRACT_IDENTITY_KEYS = (
    "geometry_fingerprint",
    "source_commit",
    "source_sha256",
    "pressure_forcing",
    "density_liquid",
    "viscosity_liquid",
    "maxlevel",
    "delta_min_Dh",
    "target_template",
    "target_template_sha256",
)
PRECURSOR_SCHEDULE_VERSION = "internal_nozzle_precursor_schedule_v1"
PRECURSOR_SCHEDULE_SHA256 = (
    "3598151fc5833c68d778830532e9c90e5d451f0c08b44e5da95a11b2952dcd11"
)
CHECKPOINT_METADATA_KEYS = {
    "schema", "case_id", "geometry_fingerprint", "source_commit",
    "source_sha256", "maxlevel", "pressure_forcing", "density_liquid",
    "viscosity_liquid", "t", "t_star", "i", "solver_dt",
    "solver_dtmax", "timestep_previous", "previous_profile_available",
    "prediction_closure_schema", "prediction_closure_state",
}


@dataclass(frozen=True)
class OperationalBounds:
    max_pressure_iterations: int
    max_velocity_iterations: int
    max_pressure_residual: float
    max_velocity_residual: float
    max_cell_range_fraction: float

    def validate(self) -> None:
        if self.max_pressure_iterations < 1 or self.max_velocity_iterations < 1:
            raise ValueError("solver iteration bounds must be positive integers")
        for name, value in (
            ("max_pressure_residual", self.max_pressure_residual),
            ("max_velocity_residual", self.max_velocity_residual),
            ("max_cell_range_fraction", self.max_cell_range_fraction),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular_file(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"history must be a regular non-symlink file: {path}")
    return resolved


def file_record(path: Path) -> dict[str, object]:
    resolved = require_regular_file(path)
    return {
        "path": str(path),
        "resolved_path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def read_key_value_file(path: Path) -> dict[str, str]:
    resolved = require_regular_file(path)
    values: dict[str, str] = {}
    for line_number, line in enumerate(
        resolved.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if "=" not in line:
            raise ValueError(f"malformed checkpoint sidecar line {line_number}: {path}")
        key, value = line.split("=", 1)
        if not key or key in values:
            raise ValueError(f"duplicate/empty checkpoint sidecar key: {path}")
        values[key] = value
    return values


def reject_duplicate_object_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def close_number(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=64.0 * math.ulp(1.0), abs_tol=1e-15)


def finite_float(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is not numeric: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} is not finite: {value!r}")
    return number


def exact_integer(value: object, label: str) -> int:
    number = finite_float(value, label)
    integer = int(number)
    if number != integer:
        raise ValueError(f"{label} is not an integer: {value!r}")
    return integer


def read_segment(path: Path, segment_index: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    resolved = require_regular_file(path)
    raw = resolved.read_text(encoding="utf-8")
    if not raw:
        raise ValueError(f"empty history: {path}")
    header = next(csv.reader(raw.splitlines()), [])
    duplicates = sorted({name for name in header if header.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate columns in {path}: {duplicates}")
    missing = sorted(REQUIRED_COLUMNS - set(header))
    if missing:
        raise ValueError(f"missing columns in {path}: {missing}")

    parsed: list[dict[str, object]] = []
    with resolved.open(newline="", encoding="utf-8") as stream:
        for row_number, row in enumerate(csv.DictReader(stream), start=2):
            context = f"{path}:{row_number}"
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"malformed CSV row at {context}")
            case_id = str(row["case_id"]).strip()
            restart_state = str(row["restart_state"]).strip()
            if not case_id or restart_state not in {"fresh", "restored"}:
                raise ValueError(f"invalid identity/state at {context}")
            values: dict[str, object] = {
                "case_id": case_id,
                "restart_state": restart_state,
                "segment_index": segment_index,
                "source_row": row_number,
            }
            for name in (
                "t", "t_star", "Q_l", "J_k", "pressure_drop",
                "mass_flow_imbalance", "profile_l2_change",
                "mgp_residual", "mgu_residual", "cell_count",
            ):
                values[name] = finite_float(row[name], f"{context}:{name}")
            for name in ("i", "mgp_iterations", "mgu_iterations"):
                values[name] = exact_integer(row[name], f"{context}:{name}")
            if values["t"] < 0 or values["t_star"] < 0:
                raise ValueError(f"negative time at {context}")
            if values["Q_l"] <= 0 or values["J_k"] <= 0 or values["pressure_drop"] <= 0:
                raise ValueError(f"non-positive core hydraulic value at {context}")
            if values["mass_flow_imbalance"] < 0 or values["profile_l2_change"] < -1:
                raise ValueError(f"invalid diagnostic value at {context}")
            if values["mgp_iterations"] < 0 or values["mgu_iterations"] < 0:
                raise ValueError(f"negative solver iteration count at {context}")
            if values["mgp_residual"] < 0 or values["mgu_residual"] < 0:
                raise ValueError(f"negative solver residual at {context}")
            if values["cell_count"] <= 0 or int(values["cell_count"]) != values["cell_count"]:
                raise ValueError(f"invalid cell count at {context}")
            parsed.append(values)
    if len(parsed) < 2:
        raise ValueError(f"history segment needs at least two rows: {path}")
    for before, after in zip(parsed, parsed[1:]):
        if after["t_star"] <= before["t_star"] or after["t"] <= before["t"]:
            raise ValueError(f"times are not strictly increasing within {path}")
    return parsed, {
        "path": str(path),
        "resolved_path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
        "rows": len(parsed),
        "first_t_star": parsed[0]["t_star"],
        "last_t_star": parsed[-1]["t_star"],
    }


def read_contract(path: Path, expected_case_id: str) -> tuple[dict[str, object], dict[str, object]]:
    resolved = require_regular_file(path)
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_object_pairs,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid run contract JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"run contract is not an object: {path}")
    required = {
        "schema", "case_id", "geometry_fingerprint", "source_commit",
        "source_sha256", "pressure_forcing", "density_liquid",
        "viscosity_liquid", "maxlevel", "delta_min_Dh",
        "restore_checkpoint", "restore_metadata", "target_template",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"run contract {path} is missing {missing}")
    if payload["schema"] != "internal_nozzle_precursor_run_v1":
        raise ValueError(f"unsupported run contract schema in {path}")
    if payload["case_id"] != expected_case_id:
        raise ValueError(f"run contract/history case mismatch in {path}")
    if not isinstance(payload["geometry_fingerprint"], str) or not payload["geometry_fingerprint"]:
        raise ValueError(f"invalid geometry fingerprint in {path}")
    for key, length in (("source_commit", 40), ("source_sha256", 64)):
        value = payload[key]
        if not isinstance(value, str) or len(value) != length or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            raise ValueError(f"invalid {key} in {path}")
    for key in ("pressure_forcing", "density_liquid", "viscosity_liquid", "delta_min_Dh"):
        value = finite_float(payload[key], f"{path}:{key}")
        if value <= 0:
            raise ValueError(f"non-positive {key} in {path}")
        payload[key] = value
    payload["maxlevel"] = exact_integer(payload["maxlevel"], f"{path}:maxlevel")
    if payload["maxlevel"] < 1:
        raise ValueError(f"invalid maxlevel in {path}")
    restore = payload["restore_checkpoint"]
    restore_metadata = payload["restore_metadata"]
    target_template = payload["target_template"]
    if not isinstance(restore, str) or not restore:
        raise ValueError(f"invalid restore_checkpoint in {path}")
    if not isinstance(restore_metadata, str) or not restore_metadata:
        raise ValueError(f"invalid restore_metadata in {path}")
    if not isinstance(target_template, str) or not target_template:
        raise ValueError(f"invalid target_template in {path}")
    if target_template == "not_applicable":
        raise ValueError(f"precursor run requires a target_template in {path}")
    template = require_regular_file(Path(target_template))
    payload["target_template"] = str(template)
    payload["target_template_sha256"] = sha256_file(template)
    return payload, file_record(resolved)


def require_metadata_number(
    metadata: dict[str, str], key: str, expected: float,
) -> None:
    actual = finite_float(metadata.get(key), f"checkpoint metadata {key}")
    if not close_number(actual, expected):
        raise ValueError(f"checkpoint metadata mismatch {key}")


def validate_checkpoint(
    directory: Path, contract: dict[str, object], terminal_row: dict[str, object],
    closure_validator: Callable[[Path], dict[str, object]],
) -> dict[str, object]:
    dump = require_regular_file(directory / "precursor-final.dump")
    sidecar = require_regular_file(Path(str(dump) + ".meta"))
    closure = require_regular_file(Path(str(dump) + ".prediction-closure-v4"))
    metadata = read_key_value_file(sidecar)
    if set(metadata) != CHECKPOINT_METADATA_KEYS:
        missing = sorted(CHECKPOINT_METADATA_KEYS - set(metadata))
        extra = sorted(set(metadata) - CHECKPOINT_METADATA_KEYS)
        raise ValueError(
            f"checkpoint metadata key-set mismatch missing={missing} extra={extra}"
        )
    expected_strings = {
        "schema": "internal_nozzle_precursor_checkpoint_v2",
        "case_id": str(contract["case_id"]),
        "geometry_fingerprint": str(contract["geometry_fingerprint"]),
        "source_commit": str(contract["source_commit"]),
        "source_sha256": str(contract["source_sha256"]),
        "prediction_closure_schema": "internal_nozzle_prediction_closure_v4",
        "prediction_closure_state": closure.name,
    }
    for key, expected in expected_strings.items():
        if metadata.get(key) != expected:
            raise ValueError(f"checkpoint metadata mismatch {key}")
    if exact_integer(metadata["maxlevel"], "checkpoint metadata maxlevel") != contract["maxlevel"]:
        raise ValueError("checkpoint metadata mismatch maxlevel")
    for key in ("pressure_forcing", "density_liquid", "viscosity_liquid"):
        require_metadata_number(metadata, key, float(contract[key]))
    require_metadata_number(metadata, "t", float(terminal_row["t"]))
    require_metadata_number(metadata, "t_star", float(terminal_row["t_star"]))
    if exact_integer(metadata["i"], "checkpoint metadata i") != int(terminal_row["i"]):
        raise ValueError("checkpoint metadata mismatch i")
    solver_dt = finite_float(metadata["solver_dt"], "checkpoint metadata solver_dt")
    solver_dtmax = finite_float(metadata["solver_dtmax"], "checkpoint metadata solver_dtmax")
    timestep_previous = finite_float(
        metadata["timestep_previous"], "checkpoint metadata timestep_previous"
    )
    if solver_dt <= 0.0 or solver_dtmax <= 0.0 or timestep_previous < 0.0:
        raise ValueError("checkpoint metadata contains invalid timestep state")
    if exact_integer(
        metadata["previous_profile_available"],
        "checkpoint metadata previous_profile_available",
    ) not in {0, 1}:
        raise ValueError("checkpoint metadata previous_profile_available is not 0 or 1")

    closure_report = closure_validator(closure)
    if not isinstance(closure_report, dict) or closure_report.get("valid") is not True:
        raise ValueError("prediction closure validator did not return valid=true")
    exact_closure = {
        "source_sha256": str(contract["source_sha256"]),
        "schedule_version": PRECURSOR_SCHEDULE_VERSION,
        "schedule_sha256": PRECURSOR_SCHEDULE_SHA256,
        "iteration": int(terminal_row["i"]),
        "grid_maxdepth": int(contract["maxlevel"]),
    }
    for key, expected in exact_closure.items():
        if closure_report.get(key) != expected:
            raise ValueError(f"prediction closure mismatch {key}")
    for key, expected in (
        ("checkpoint_t", float(terminal_row["t"])),
        ("checkpoint_dt", solver_dt),
        ("checkpoint_dtmax", solver_dtmax),
        ("timestep_previous", timestep_previous),
    ):
        actual = finite_float(closure_report.get(key), f"prediction closure {key}")
        if not close_number(actual, expected):
            raise ValueError(f"prediction closure mismatch {key}")
    domain = closure_report.get("domain")
    if (
        not isinstance(domain, list) or len(domain) != 4
        or any(not math.isfinite(float(value)) for value in domain)
    ):
        raise ValueError("prediction closure has invalid domain")
    x0, y0, z0, length = (float(value) for value in domain)
    if length <= 0.0 or not close_number(x0, 0.0) or not close_number(y0, -0.5 * length) \
            or not close_number(z0, -0.5 * length):
        raise ValueError("prediction closure has incompatible precursor domain")
    return {
        "dump": file_record(dump),
        "metadata": file_record(sidecar),
        "prediction_closure": file_record(closure),
        "validated_identity": {
            "case_id": contract["case_id"],
            "source_commit": contract["source_commit"],
            "source_sha256": contract["source_sha256"],
            "t": terminal_row["t"],
            "t_star": terminal_row["t_star"],
            "i": terminal_row["i"],
            "schedule_version": PRECURSOR_SCHEDULE_VERSION,
            "schedule_sha256": PRECURSOR_SCHEDULE_SHA256,
        },
        "closure_validation": closure_report,
    }


def same_boundary_row(left: dict[str, object], right: dict[str, object]) -> bool:
    fields = REQUIRED_COLUMNS - {"restart_state"}
    return all(left[field] == right[field] for field in fields)


def combine_segments(
    paths: Sequence[Path], contracts: Sequence[Path],
    closure_validator: Callable[[Path], dict[str, object]] | None = None,
) -> tuple[
    list[dict[str, object]], list[dict[str, object]]
]:
    if not paths:
        raise ValueError("at least one history is required")
    if len(paths) != len(contracts):
        raise ValueError("each history requires one matching run contract")
    combined: list[dict[str, object]] = []
    provenance: list[dict[str, object]] = []
    case_id: str | None = None
    reference_identity: tuple[object, ...] | None = None
    closure_validator = closure_validator or validate_closure_v4
    previous_checkpoint: dict[str, object] | None = None
    for segment_index, path in enumerate(paths):
        rows, record = read_segment(path, segment_index)
        segment_case = str(rows[0]["case_id"])
        if any(row["case_id"] != segment_case for row in rows):
            raise ValueError(f"mixed case IDs within {path}")
        if case_id is None:
            case_id = segment_case
        elif segment_case != case_id:
            raise ValueError("sequential histories have different case IDs")
        contract, contract_record = read_contract(contracts[segment_index], segment_case)
        history_resolved = Path(str(record["resolved_path"]))
        contract_resolved = Path(str(contract_record["resolved_path"]))
        if contract_resolved.parent != history_resolved.parent:
            raise ValueError("history and run contract must be in the same directory")
        identity = tuple(contract[key] for key in CONTRACT_IDENTITY_KEYS)
        if reference_identity is None:
            reference_identity = identity
        elif identity != reference_identity:
            raise ValueError("sequential run contracts do not share one physical/source identity")
        restore_checkpoint = str(contract["restore_checkpoint"])
        restore_metadata = str(contract["restore_metadata"])
        expected_state = "fresh" if segment_index == 0 else "restored"
        if any(row["restart_state"] != expected_state for row in rows):
            raise ValueError(
                f"segment {segment_index} has incompatible restart_state"
            )
        predecessor: dict[str, object]
        if previous_checkpoint is None:
            if restore_checkpoint != "not_applicable" or restore_metadata != "not_applicable":
                raise ValueError("first precursor segment must be a fresh trajectory")
            if not close_number(float(rows[0]["t"]), 0.0) or not close_number(
                float(rows[0]["t_star"]), 0.0
            ):
                raise ValueError("first fresh precursor segment must start at t=t_star=0")
            predecessor = {"kind": "fresh"}
        else:
            expected_dump = Path(str(previous_checkpoint["dump"]["resolved_path"]))
            expected_sidecar = Path(str(previous_checkpoint["metadata"]["resolved_path"]))
            expected_closure = Path(
                str(previous_checkpoint["prediction_closure"]["resolved_path"])
            )
            try:
                requested_dump = Path(restore_checkpoint).resolve(strict=True)
                requested_sidecar = Path(restore_metadata).resolve(strict=True)
            except FileNotFoundError as error:
                raise ValueError("segment predecessor checkpoint is missing") from error
            if requested_dump != expected_dump or requested_sidecar != expected_sidecar:
                raise ValueError("segment does not restore the immediately preceding checkpoint")
            current_members = {
                "dump": file_record(expected_dump),
                "metadata": file_record(expected_sidecar),
                "prediction_closure": file_record(expected_closure),
            }
            for member in current_members:
                if current_members[member]["sha256"] != previous_checkpoint[member]["sha256"]:
                    raise ValueError(f"predecessor checkpoint {member} changed after validation")
            predecessor = {
                "kind": "checkpoint",
                "dump": current_members["dump"],
                "metadata": current_members["metadata"],
                "prediction_closure": current_members["prediction_closure"],
            }
        checkpoint = validate_checkpoint(
            history_resolved.parent, contract, rows[-1], closure_validator
        )
        provenance.append({
            "segment_index": segment_index,
            "history": record,
            "run_contract": contract_record,
            "restart_checkpoint": contract["restore_checkpoint"],
            "predecessor": predecessor,
            "terminal_checkpoint": checkpoint,
        })
        if combined:
            previous_t = float(combined[-1]["t_star"])
            first_t = float(rows[0]["t_star"])
            if not close_number(first_t, previous_t) or not close_number(
                float(rows[0]["t"]), float(combined[-1]["t"])
            ):
                raise ValueError("segment boundary must exactly continue prior endpoint")
            if not same_boundary_row(combined[-1], rows[0]):
                raise ValueError("segment boundary duplicate has different scientific values")
            rows = rows[1:]
        combined.extend(rows)
        previous_checkpoint = checkpoint
    if len(combined) < 2:
        raise ValueError("combined history needs at least two unique rows")
    return combined, provenance


def ordinary_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator <= 0:
        raise ValueError("trend times have zero variance")
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator


def robust_slope(xs: Sequence[float], ys: Sequence[float], maximum_points: int = 129) -> float:
    if len(xs) > maximum_points:
        indexes = sorted({round(index * (len(xs) - 1) / (maximum_points - 1))
                          for index in range(maximum_points)})
        xs = [xs[index] for index in indexes]
        ys = [ys[index] for index in indexes]
    slopes = [
        (ys[right] - ys[left]) / (xs[right] - xs[left])
        for left in range(len(xs) - 1)
        for right in range(left + 1, len(xs))
        if xs[right] > xs[left]
    ]
    if not slopes:
        raise ValueError("insufficient unique times for robust trend")
    return statistics.median(slopes)


def monotonic_fraction(values: Sequence[float]) -> float:
    signs = [1 if right > left else -1 if right < left else 0
             for left, right in zip(values, values[1:])]
    nonzero = [sign for sign in signs if sign]
    if not nonzero:
        return 0.0
    return max(nonzero.count(1), nonzero.count(-1)) / len(nonzero)


def trend_resolution(
    xs: Sequence[float], ys: Sequence[float], ordinary: float, robust: float,
) -> dict[str, object]:
    """Separate a resolved monotonic drift from fluctuations around zero slope."""
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    intercept = y_mean - ordinary * x_mean
    residuals = [
        value - (intercept + ordinary * point)
        for point, value in zip(xs, ys)
    ]
    degrees_of_freedom = len(xs) - 2
    standard_error = (
        math.sqrt(sum(value * value for value in residuals) / degrees_of_freedom)
        / math.sqrt(denominator)
    )
    robust_intercept = statistics.median(
        [value - robust * point for point, value in zip(xs, ys)]
    )
    robust_residuals = [
        value - (robust_intercept + robust * point)
        for point, value in zip(xs, ys)
    ]
    residual_median = statistics.median(robust_residuals)
    robust_residual_scale = 1.4826 * statistics.median(
        abs(value - residual_median) for value in robust_residuals
    )
    confidence_half_width = 1.96 * standard_error
    confidence_excludes_zero = abs(ordinary) > confidence_half_width
    trend_span = abs(robust) * (max(xs) - min(xs))
    numerical_floor = max(abs(y_mean), 1.0) * 128.0 * math.ulp(1.0)
    robust_signal_exceeds_noise = trend_span > max(
        3.0 * robust_residual_scale, numerical_floor
    )
    directions_agree = ordinary == 0.0 or robust == 0.0 or ordinary * robust > 0.0
    resolved = bool(
        confidence_excludes_zero and robust_signal_exceeds_noise and directions_agree
    )
    return {
        "ordinary_slope_standard_error": standard_error,
        "ordinary_95_percent_half_width": confidence_half_width,
        "ordinary_95_percent_interval_excludes_zero": confidence_excludes_zero,
        "robust_residual_mad_scale": robust_residual_scale,
        "robust_trend_span": trend_span,
        "minimum_resolvable_span": max(3.0 * robust_residual_scale, numerical_floor),
        "ordinary_robust_direction_agreement": directions_agree,
        "resolved_monotonic_trend": resolved,
    }


def metric_audit(rows: Sequence[dict[str, object]], name: str,
                 window: float, limit: float) -> dict[str, object]:
    xs = [float(row["t_star"]) for row in rows]
    ys = [float(row[name]) for row in rows]
    mean = statistics.fmean(ys)
    if not math.isfinite(mean) or mean <= 0:
        raise ValueError(f"{name} has non-positive final-window mean")
    ordinary = ordinary_slope(xs, ys)
    robust = robust_slope(xs, ys)
    signed_drift = (ys[-1] - ys[0]) / mean
    ordinary_window_trend = ordinary * window / mean
    robust_window_trend = robust * window / mean
    trend = trend_resolution(xs, ys, ordinary, robust)
    tests = {
        "end_to_end_relative_drift": abs(signed_drift) <= limit,
        "ordinary_projected_relative_trend": abs(ordinary_window_trend) <= limit,
        "robust_projected_relative_trend": abs(robust_window_trend) <= limit,
        "no_unresolved_monotonic_trend": not trend["resolved_monotonic_trend"],
    }
    return {
        "mean": mean,
        "first": ys[0],
        "last": ys[-1],
        "signed_end_to_end_relative_drift": signed_drift,
        "ordinary_relative_slope_per_t_star": ordinary / mean,
        "robust_relative_slope_per_t_star": robust / mean,
        "ordinary_projected_relative_trend_over_window": ordinary_window_trend,
        "robust_projected_relative_trend_over_window": robust_window_trend,
        "monotonic_fraction": monotonic_fraction(ys),
        "trend_resolution": trend,
        "limit": limit,
        "tests": tests,
        "pass": all(tests.values()),
    }


def analyze(paths: Sequence[Path], *, contracts: Sequence[Path], window_t_star: float,
            maximum_gap_t_star: float, minimum_samples: int,
            bounds: OperationalBounds,
            closure_validator: Callable[[Path], dict[str, object]] | None = None,
            ) -> dict[str, object]:
    bounds.validate()
    if not math.isfinite(window_t_star) or window_t_star <= 0:
        raise ValueError("window_t_star must be finite and positive")
    if not math.isfinite(maximum_gap_t_star) or maximum_gap_t_star <= 0:
        raise ValueError("maximum_gap_t_star must be finite and positive")
    if minimum_samples < 3:
        raise ValueError("minimum_samples must be at least three")
    rows, provenance = combine_segments(paths, contracts, closure_validator)
    final_t_star = float(rows[-1]["t_star"])
    window_start = final_t_star - window_t_star
    if window_start < 0:
        raise ValueError("history does not reach the requested final window")
    selected = [row for row in rows if float(row["t_star"]) >= window_start]
    if len(selected) < minimum_samples:
        raise ValueError("final window has too few samples")
    selected_times = [float(row["t_star"]) for row in selected]
    coverage = selected_times[-1] - selected_times[0]
    gaps = [right - left for left, right in zip(selected_times, selected_times[1:])]
    if selected_times[0] > window_start + maximum_gap_t_star:
        raise ValueError("final window start is not sampled within the allowed gap")
    if gaps and max(gaps) > maximum_gap_t_star:
        raise ValueError("final window contains a sampling gap above the declared limit")

    metrics = {
        name: metric_audit(selected, name, window_t_star, limit)
        for name, limit in CORE_THRESHOLDS.items()
    }
    profile_values = [float(row["profile_l2_change"]) for row in selected]
    if any(value < 0 for value in profile_values):
        raise ValueError("final window contains unavailable profile L2 values")
    imbalance_values = [float(row["mass_flow_imbalance"]) for row in selected]
    cell_values = [int(float(row["cell_count"])) for row in selected]
    cell_mean = statistics.fmean(cell_values)
    cell_range_fraction = (max(cell_values) - min(cell_values)) / cell_mean
    pressure_iterations = [int(row["mgp_iterations"]) for row in selected]
    velocity_iterations = [int(row["mgu_iterations"]) for row in selected]
    pressure_residuals = [float(row["mgp_residual"]) for row in selected]
    velocity_residuals = [float(row["mgu_residual"]) for row in selected]

    auxiliary_tests = {
        "consecutive_normalized_profile_l2": max(profile_values) <= PROFILE_L2_LIMIT,
        "mass_flow_imbalance": max(imbalance_values) <= MASS_IMBALANCE_LIMIT,
        "pressure_iterations_bounded": max(pressure_iterations) <= bounds.max_pressure_iterations,
        "velocity_iterations_bounded": max(velocity_iterations) <= bounds.max_velocity_iterations,
        "pressure_residual_bounded": max(pressure_residuals) <= bounds.max_pressure_residual,
        "velocity_residual_bounded": max(velocity_residuals) <= bounds.max_velocity_residual,
        "cell_population_bounded": cell_range_fraction <= bounds.max_cell_range_fraction,
    }
    passed = all(item["pass"] for item in metrics.values()) and all(auxiliary_tests.values())
    failures = [f"{name}:{test}" for name, item in metrics.items()
                for test, status in item["tests"].items() if not status]
    failures.extend(name for name, status in auxiliary_tests.items() if not status)
    return {
        "schema": SCHEMA,
        "classification": "precursor_converged" if passed else "not_converged",
        "pass": passed,
        "case_id": rows[0]["case_id"],
        "inputs": provenance,
        "combined_unique_sample_count": len(rows),
        "window": {
            "requested_delta_t_star": window_t_star,
            "start_t_star": window_start,
            "first_sample_t_star": selected_times[0],
            "end_t_star": final_t_star,
            "coverage_t_star": coverage,
            "sample_count": len(selected),
            "maximum_observed_gap_t_star": max(gaps) if gaps else 0.0,
            "maximum_allowed_gap_t_star": maximum_gap_t_star,
        },
        "fixed_scientific_thresholds": {
            "Q_l_relative_drift_and_projected_trend": CORE_THRESHOLDS["Q_l"],
            "J_k_relative_drift_and_projected_trend": CORE_THRESHOLDS["J_k"],
            "pressure_drop_relative_drift_and_projected_trend": CORE_THRESHOLDS["pressure_drop"],
            "consecutive_normalized_profile_l2": PROFILE_L2_LIMIT,
            "mass_flow_imbalance": MASS_IMBALANCE_LIMIT,
            "unresolved_monotonic_trend": (
                "fails when the ordinary 95-percent slope interval excludes zero "
                "and the agreeing robust trend exceeds three robust residual scales"
            ),
        },
        "declared_operational_bounds": {
            "max_pressure_iterations": bounds.max_pressure_iterations,
            "max_velocity_iterations": bounds.max_velocity_iterations,
            "max_pressure_residual": bounds.max_pressure_residual,
            "max_velocity_residual": bounds.max_velocity_residual,
            "max_cell_range_fraction": bounds.max_cell_range_fraction,
        },
        "metrics": metrics,
        "auxiliary": {
            "maximum_profile_l2_change": max(profile_values),
            "maximum_mass_flow_imbalance": max(imbalance_values),
            "maximum_pressure_iterations": max(pressure_iterations),
            "maximum_velocity_iterations": max(velocity_iterations),
            "maximum_pressure_residual": max(pressure_residuals),
            "maximum_velocity_residual": max(velocity_residuals),
            "minimum_cell_count": min(cell_values),
            "maximum_cell_count": max(cell_values),
            "cell_range_fraction": cell_range_fraction,
            "tests": auxiliary_tests,
        },
        "failures": failures,
        "claim_boundary": "operational precursor-generation convergence, not physical validation",
    }


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"temporary output already exists: {temporary}")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, action="append", required=True)
    parser.add_argument("--run-contract", type=Path, action="append", required=True)
    parser.add_argument("--window-t-star", type=float, required=True)
    parser.add_argument("--maximum-gap-t-star", type=float, required=True)
    parser.add_argument("--minimum-samples", type=int, default=6)
    parser.add_argument("--max-pressure-iterations", type=int, required=True)
    parser.add_argument("--max-velocity-iterations", type=int, required=True)
    parser.add_argument("--max-pressure-residual", type=float, required=True)
    parser.add_argument("--max-velocity-residual", type=float, required=True)
    parser.add_argument("--max-cell-range-fraction", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-converged", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    bounds = OperationalBounds(
        max_pressure_iterations=args.max_pressure_iterations,
        max_velocity_iterations=args.max_velocity_iterations,
        max_pressure_residual=args.max_pressure_residual,
        max_velocity_residual=args.max_velocity_residual,
        max_cell_range_fraction=args.max_cell_range_fraction,
    )
    result = analyze(
        args.history,
        contracts=args.run_contract,
        window_t_star=args.window_t_star,
        maximum_gap_t_star=args.maximum_gap_t_star,
        minimum_samples=args.minimum_samples,
        bounds=bounds,
    )
    atomic_json(args.output, result)
    print(json.dumps({"classification": result["classification"],
                      "output": str(args.output)}, sort_keys=True))
    # Non-convergence is always a failing operational gate.  The retained flag
    # is accepted for compatibility with existing launchers but cannot weaken
    # the default.
    return 0 if result["pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
