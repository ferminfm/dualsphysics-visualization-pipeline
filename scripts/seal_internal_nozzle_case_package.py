#!/usr/bin/env python3
"""Seal one completed A/B/C run into a hash-bound local comparison package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path


ROLE_MODES: dict[str, dict[str, object]] = {
    "A": {"selected_case": "W2_pressure_driven", "initial_state": "rest_start",
          "inlet_mode": "pressure_driven", "precursor_pressure_mode": "not_applicable",
          "pressure_driven_preserved": True},
    "B": {"selected_case": "W2_pressure_driven", "initial_state": "precursor_start",
          "inlet_mode": "pressure_driven", "precursor_pressure_mode": "transferred",
          "pressure_driven_preserved": True},
    "C": {"selected_case": "W2_profile_controlled_diagnostic",
          "initial_state": "precursor_start",
          "inlet_mode": "poiseuille_profile_controlled_diagnostic",
          "precursor_pressure_mode": "transferred", "pressure_driven_preserved": False},
}

FIXED_MEMBERS = (
    "raw_export_manifest.json",
    "hydraulic_plane_metrics.csv",
    "hydraulic_plane_profiles.csv",
    "solver_health_metrics.csv",
    "initialization_contract.json",
    "scientific_runtime_contract.json",
    "run_schedule_contract.json",
    "checkpoint_manifest.json",
    "checkpoint_index.csv",
    "visual_pipeline_case_summary.csv",
)

PROJECTION_METRICS = (
    "divergence_l2", "divergence_max", "velocity_impulse_l2",
    "cell_pressure_change_l2", "projection_pressure_adjustment_l2",
)
PROJECTION_PHASES = (
    "pre_projection_input", "pre_advection_closure",
    "post_timestep_projection", "post_timestep_projection",
)

BOUND_LAUNCH_KEYS = {
    "schema", "execution_id", "segment_id", "case_role", "case_id", "cwd",
    "output_dir", "expected_runtime_contract", "expected_initialization_contract",
    "scientific_source_commit", "source_sha256", "source_bundle_manifest",
    "observable_qcc_build_manifest", "batch_identity", "schedule", "solver",
    "role_contract", "precursor_transfer", "precursor_bulk_target",
    "poiseuille_profile_validation", "restore", "verified_inputs", "supervisor",
    "solver_argv", "supervisor_argv", "execution_contract",
}

LAUNCH_ROLE_CONTRACTS = {
    "A": {
        "initial_state": "rest", "inlet_mode": "pressure_driven",
        "build_variant": "pressure_driven", "precursor_pressure_mode": "not_applicable",
    },
    "B": {
        "initial_state": "precursor", "inlet_mode": "pressure_driven",
        "build_variant": "pressure_driven", "precursor_pressure_mode": "transferred",
    },
    "C": {
        "initial_state": "precursor",
        "inlet_mode": "poiseuille_profile_controlled_diagnostic",
        "build_variant": "profile_controlled", "precursor_pressure_mode": "transferred",
    },
}


def acceptance_module():
    path = Path(__file__).resolve().with_name("evaluate_internal_nozzle_acceptance.py")
    spec = importlib.util.spec_from_file_location("internal_nozzle_acceptance", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load deterministic acceptance module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ROLE_PREREQUISITES: dict[str, dict[str, bool | str]] = {
    "A": {
        "source_bundle_verified": True,
        "schedule_verified": True,
        "solver_verified": True,
        "precursor_transfer_verified": "not_applicable",
        "precursor_transfer_projection_passed": "not_applicable",
        "precursor_convergence_verified": "not_applicable",
        "poiseuille_profile_verified": "not_applicable",
    },
    "B": {
        "source_bundle_verified": True,
        "schedule_verified": True,
        "solver_verified": True,
        "precursor_transfer_verified": True,
        "precursor_transfer_projection_passed": True,
        "precursor_convergence_verified": True,
        "poiseuille_profile_verified": "not_applicable",
    },
    "C": {
        "source_bundle_verified": True,
        "schedule_verified": True,
        "solver_verified": True,
        "precursor_transfer_verified": True,
        "precursor_transfer_projection_passed": True,
        "precursor_convergence_verified": True,
        "poiseuille_profile_verified": True,
    },
}


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, context: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{context}: unreadable JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{context}: JSON root must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_under(root: Path, path: Path, context: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{context}: symlink forbidden: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{context}: missing path: {path}") from error
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"{context}: expected nonempty regular file: {path}")
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{context}: path escapes run root: {path}") from error
    return resolved


def member_record(
    root: Path, path: Path, context: str, *, allow_empty: bool = False
) -> dict[str, object]:
    if allow_empty:
        if path.is_symlink():
            raise ValueError(f"{context}: symlink forbidden: {path}")
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"{context}: missing path: {path}") from error
        if not resolved.is_file():
            raise ValueError(f"{context}: expected regular file: {path}")
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(f"{context}: path escapes run root: {path}") from error
    else:
        resolved = regular_under(root, path, context)
    return {
        "path": resolved.relative_to(root).as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def require_csv_header(path: Path, required: set[str], context: str) -> None:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError(f"{context}: empty CSV") from error
    if len(header) != len(set(header)):
        raise ValueError(f"{context}: duplicate CSV header")
    missing = required - set(header)
    if missing:
        raise ValueError(f"{context}: missing columns {sorted(missing)}")


def required_text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: required nonempty string")
    return value


def verified_input(terminal: dict[str, object], expected_sha: str) -> bool:
    inputs = terminal.get("verified_inputs")
    if not isinstance(inputs, list):
        return False
    for item in inputs:
        if not isinstance(item, dict):
            continue
        if (item.get("expected_sha256") == expected_sha and
                item.get("observed_sha256") == expected_sha and
                item.get("observed_sha256_after") == expected_sha and
                item.get("verified") is True and
                item.get("unchanged_during_run") is True):
            return True
    return False


def canonical_hash(value: object, length: int, context: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"{context}: expected {length} lowercase hexadecimal characters")
    return value


def finite(value: object, context: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{context}: expected a finite number")
    try:
        result = float(value)
    except ValueError as error:
        raise ValueError(f"{context}: expected a finite number") from error
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise ValueError(f"{context}: invalid numeric value")
    return result


def csv_rows(path: Path, required: set[str], context: str) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{context}: missing or duplicate CSV header")
        if not required.issubset(reader.fieldnames):
            raise ValueError(f"{context}: missing columns {sorted(required - set(reader.fieldnames))}")
        rows = list(reader)
    if not rows or any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{context}: empty or malformed CSV")
    return rows


def option_values(argv: list[str], option: str, context: str) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(argv):
        if token == option:
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                raise ValueError(f"{context}: {option} lacks a value")
            values.append(argv[index + 1])
        elif token.startswith(option + "="):
            raise ValueError(f"{context}: noncanonical equals-form {option}")
    return values


def exact_option(argv: list[str], option: str, expected: str, context: str) -> None:
    if option_values(argv, option, context) != [expected]:
        raise ValueError(f"{context}: {option} must equal {expected!r} exactly once")


def atomic_create_json(path: Path, payload: dict[str, object], context: str) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"{context}: refusing to overwrite {path}")
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"{context}: temporary path already exists")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_verified_inputs(
    launch: dict[str, object], terminal: dict[str, object],
    expected: list[dict[str, object]], context: str,
) -> None:
    expected_map = {
        str(Path(str(item["path"])).resolve(strict=True)): str(item["sha256"])
        for item in expected
    }
    if len(expected_map) != len(expected):
        raise ValueError(f"{context}: duplicate expected input path")
    for record_name, record, after in (
        ("launch", launch, False), ("terminal", terminal, True),
    ):
        values = record.get("verified_inputs")
        if not isinstance(values, list) or len(values) != len(expected_map):
            raise ValueError(f"{context}: {record_name} verified-input cardinality mismatch")
        seen: set[str] = set()
        for item in values:
            if not isinstance(item, dict):
                raise ValueError(f"{context}: malformed verified-input record")
            resolved = str(Path(required_text(item.get("resolved_path"), context)).resolve(strict=True))
            if resolved in seen or resolved not in expected_map:
                raise ValueError(f"{context}: duplicate/unexpected verified input")
            seen.add(resolved)
            digest = expected_map[resolved]
            if (item.get("expected_sha256") != digest or
                    item.get("observed_sha256") != digest or
                    item.get("verified") is not True or
                    sha256_file(Path(resolved)) != digest):
                raise ValueError(f"{context}: verified input identity mismatch")
            if after and (item.get("observed_sha256_after") != digest or
                          item.get("unchanged_during_run") is not True):
                raise ValueError(f"{context}: input changed during run")


def bound_input_map(
    root: Path, records: object, context: str,
) -> dict[str, dict[str, str]]:
    if not isinstance(records, list) or not records:
        raise ValueError(f"{context}: bound launch lacks exact input set")
    result: dict[str, dict[str, str]] = {}
    seen_paths: set[str] = set()
    for index, item in enumerate(records):
        item_context = f"{context}: verified input {index}"
        if not isinstance(item, dict) or set(item) != {"label", "path", "sha256"}:
            raise ValueError(f"{item_context}: key set mismatch")
        label = required_text(item.get("label"), item_context)
        path_text = required_text(item.get("path"), item_context)
        digest = canonical_hash(item.get("sha256"), 64, item_context)
        try:
            path = Path(path_text).resolve(strict=True)
        except OSError as error:
            raise ValueError(f"{item_context}: input is unavailable") from error
        if path_text != str(path) or path.is_symlink() or not path.is_file():
            raise ValueError(f"{item_context}: path is not canonical regular input")
        if label in result or path_text in seen_paths:
            raise ValueError(f"{item_context}: duplicate label/path")
        if sha256_file(path) != digest:
            raise ValueError(f"{item_context}: current input digest mismatch")
        result[label] = {"path": path_text, "sha256": digest}
        seen_paths.add(path_text)
    return result


def validate_bound_build(
    bound: dict[str, object], input_map: dict[str, dict[str, str]],
    source_sha: str, source_commit: str, solver_sha: str, role: str,
    context: str,
) -> None:
    build_record = bound.get("observable_qcc_build_manifest")
    if not isinstance(build_record, dict) or set(build_record) != {
        "path", "sha256", "build_role", "compile_run_id",
    }:
        raise ValueError(f"{context}: observable qcc build binding is malformed")
    expected_role = "profile_controlled" if role == "C" else "pressure_driven"
    if build_record.get("build_role") != expected_role:
        raise ValueError(f"{context}: observable qcc build role mismatch")
    path = Path(required_text(build_record.get("path"), context + " build path"))
    digest = canonical_hash(build_record.get("sha256"), 64, context + " build SHA")
    if (input_map.get("observable_qcc_build_manifest") !=
            {"path": str(path), "sha256": digest}):
        raise ValueError(f"{context}: observable qcc build input is not hash-bound")
    payload = load_json(path, context + " observable qcc build")
    binary = payload.get("binary")
    if set(payload) != {
            "schema", "scientific_commit", "source_bundle_path",
            "source_bundle_sha256", "build_role", "entry_source",
            "required_defines", "compile_identity_semantics", "compile_run_id",
            "compile_argv", "compile_terminal", "binary", "verified_input_count",
    }:
        raise ValueError(f"{context}: observable qcc build key set mismatch")
    expected_entry = (
        "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c"
    )
    expected_defines = ["INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1"]
    if expected_role == "profile_controlled":
        expected_defines.append("INTERNAL_NOZZLE_PROFILE_CONTROLLED=1")
    compile_terminal = payload.get("compile_terminal")
    if (payload.get("schema") != "internal_nozzle_observable_qcc_build_v1" or
            payload.get("scientific_commit") != source_commit or
            payload.get("source_bundle_path") !=
            input_map["source_bundle_manifest"]["path"] or
            payload.get("source_bundle_sha256") != source_sha or
            payload.get("build_role") != expected_role or
            payload.get("entry_source") != expected_entry or
            payload.get("required_defines") != expected_defines or
            payload.get("compile_run_id") != build_record.get("compile_run_id") or
            payload.get("compile_identity_semantics") !=
            "observable_qcc_exact_entry_source_role_defines_and_immutable_inputs" or
            not isinstance(payload.get("compile_argv"), list) or
            not payload.get("compile_argv") or
            not isinstance(compile_terminal, dict) or
            set(compile_terminal) != {"path", "sha256", "exit_code", "terminal_state"} or
            compile_terminal.get("exit_code") != 0 or
            compile_terminal.get("terminal_state") != "normal_exit" or
            not isinstance(binary, dict) or
            set(binary) != {"path", "size_bytes", "sha256"} or
            binary.get("path") != input_map["solver_executable"]["path"] or
            binary.get("sha256") != solver_sha or
            binary.get("size_bytes") != Path(str(binary["path"])).stat().st_size or
            not isinstance(payload.get("verified_input_count"), int) or
            payload.get("verified_input_count") <= 0):
        raise ValueError(f"{context}: observable qcc build identity mismatch")


def validate_projection_acceptance(
    root: Path, execution_id: str, role: str, case_id: str,
    projection_path: Path, rows: list[dict[str, str]],
) -> tuple[Path, dict[str, object]]:
    path = regular_under(
        root, root / "precursor_transfer_projection_acceptance.json",
        "projection acceptance",
    )
    payload = load_json(path, "projection acceptance")
    if set(payload) != {
        "schema", "assessment_id", "execution_id", "case_id", "case_role",
        "acceptance_basis", "projection_evidence", "predicates", "pass",
        "claim_boundary",
    } or payload.get("schema") != "internal_nozzle_transfer_projection_acceptance_v1":
        raise ValueError("projection acceptance schema/key set mismatch")
    if (payload.get("execution_id") != execution_id or payload.get("case_id") != case_id or
            payload.get("case_role") != role or
            payload.get("acceptance_basis") != "task04_predeclared_projection_thresholds_v1" or
            payload.get("pass") is not True):
        raise ValueError("projection acceptance identity/pass mismatch")
    required_text(payload.get("assessment_id"), "projection assessment_id")
    required_text(payload.get("claim_boundary"), "projection claim_boundary")
    evidence = payload.get("projection_evidence")
    if (not isinstance(evidence, dict) or set(evidence) != {"path", "sha256"} or
            evidence.get("path") != "precursor_transfer_projection.csv" or
            evidence.get("sha256") != sha256_file(projection_path)):
        raise ValueError("projection acceptance does not bind exact projection evidence")
    predicates = payload.get("predicates")
    if not isinstance(predicates, list) or len(predicates) != len(PROJECTION_METRICS):
        raise ValueError("projection acceptance predicate cardinality mismatch")
    expected_observed = {
        metric: max(finite(row[metric], f"projection {metric}") for row in rows)
        for metric in PROJECTION_METRICS
    }
    seen: set[str] = set()
    for predicate in predicates:
        if not isinstance(predicate, dict) or set(predicate) != {
            "metric", "aggregation", "operator", "observed", "limit", "passed",
        }:
            raise ValueError("projection acceptance predicate key set mismatch")
        metric = required_text(predicate.get("metric"), "projection predicate metric")
        if metric not in expected_observed or metric in seen:
            raise ValueError("projection acceptance predicate metric mismatch")
        seen.add(metric)
        if (predicate.get("aggregation") != "max_over_ordered_records" or
                predicate.get("operator") != "<="):
            raise ValueError("projection acceptance predicate operation mismatch")
        observed = finite(predicate.get("observed"), f"projection {metric} observed")
        limit = finite(predicate.get("limit"), f"projection {metric} limit")
        if observed < 0.0 or limit < 0.0:
            raise ValueError("projection acceptance values must be nonnegative")
        expected = expected_observed[metric]
        if (not math.isclose(observed, expected, rel_tol=5e-13, abs_tol=1e-15) or
                predicate.get("passed") is not True or observed > limit):
            raise ValueError(f"projection acceptance predicate failed: {metric}")
    return path, payload


def validate_profile_acceptance(
    root: Path, source_sha: str, evidence_path: Path, acceptance_path: Path,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    evidence = regular_under(root, evidence_path, "Poiseuille profile evidence")
    acceptance = regular_under(root, acceptance_path, "Poiseuille profile acceptance")
    rows = csv_rows(evidence, {
        "sample_index", "y_over_width", "z_over_height", "quadrature_weight",
        "wall_sample", "implementation_unit_velocity", "reference_unit_velocity",
    }, "Poiseuille profile evidence")
    if len(rows) < 5:
        raise ValueError("Poiseuille profile evidence has insufficient samples")
    weighted_error_squared = 0.0
    weighted_reference_squared = 0.0
    weighted_implementation = 0.0
    total_weight = 0.0
    maximum_error = 0.0
    reference_peak = 0.0
    maximum_wall_velocity = 0.0
    wall_count = 0
    seen_coordinates: set[tuple[str, str]] = set()
    for expected_index, row in enumerate(rows):
        try:
            sample_index = int(row["sample_index"])
        except ValueError as error:
            raise ValueError("Poiseuille profile sample index is invalid") from error
        if str(sample_index) != row["sample_index"] or sample_index != expected_index:
            raise ValueError("Poiseuille profile samples are duplicated/out of order")
        coordinate = (row["y_over_width"], row["z_over_height"])
        if coordinate in seen_coordinates:
            raise ValueError("Poiseuille profile sample coordinate is duplicated")
        seen_coordinates.add(coordinate)
        finite(row["y_over_width"], "profile y coordinate")
        finite(row["z_over_height"], "profile z coordinate")
        weight = finite(row["quadrature_weight"], "profile quadrature weight")
        if weight < 0.0 or row["wall_sample"] not in {"true", "false"}:
            raise ValueError("Poiseuille profile weight/wall flag is invalid")
        implementation = finite(row["implementation_unit_velocity"], "profile implementation")
        reference = finite(row["reference_unit_velocity"], "profile reference")
        error = abs(implementation - reference)
        maximum_error = max(maximum_error, error)
        reference_peak = max(reference_peak, abs(reference))
        if row["wall_sample"] == "true":
            wall_count += 1
            maximum_wall_velocity = max(maximum_wall_velocity, abs(implementation))
        else:
            if weight <= 0.0:
                raise ValueError("interior Poiseuille quadrature weight must be positive")
            total_weight += weight
            weighted_error_squared += weight * error * error
            weighted_reference_squared += weight * reference * reference
            weighted_implementation += weight * implementation
    if (total_weight <= 0.0 or weighted_reference_squared <= 0.0 or
            reference_peak <= 0.0 or wall_count == 0):
        raise ValueError("Poiseuille profile evidence lacks quadrature/wall support")
    observed_metrics = {
        "weighted_relative_l2": math.sqrt(
            weighted_error_squared / weighted_reference_squared
        ),
        "peak_normalized_linf": maximum_error / reference_peak,
        "absolute_bulk_error": abs(weighted_implementation / total_weight - 1.0),
        "exact_wall_no_slip": maximum_wall_velocity,
    }
    payload = load_json(acceptance, "Poiseuille profile acceptance")
    if set(payload) != {
        "schema", "assessment_id", "classification", "acceptance_basis",
        "source_sha256", "profile_evidence", "predicates", "pass", "claim_boundary",
    } or payload.get("schema") != "internal_nozzle_poiseuille_profile_acceptance_v1":
        raise ValueError("Poiseuille profile acceptance schema/key set mismatch")
    if (payload.get("classification") != "poiseuille_profile_implementation_accepted" or
            payload.get("acceptance_basis") != "task02_high_mode_reference_predicate_v1" or
            payload.get("source_sha256") != source_sha or payload.get("pass") is not True):
        raise ValueError("Poiseuille profile acceptance identity/pass mismatch")
    required_text(payload.get("assessment_id"), "profile assessment_id")
    required_text(payload.get("claim_boundary"), "profile claim_boundary")
    evidence_record = payload.get("profile_evidence")
    if (not isinstance(evidence_record, dict) or set(evidence_record) != {"path", "sha256"} or
            evidence_record.get("path") != evidence.name or
            evidence_record.get("sha256") != sha256_file(evidence)):
        raise ValueError("Poiseuille profile acceptance does not bind exact evidence")
    predicates = payload.get("predicates")
    if not isinstance(predicates, list) or len(predicates) != len(observed_metrics):
        raise ValueError("Poiseuille profile predicate cardinality mismatch")
    seen_metrics: set[str] = set()
    for predicate in predicates:
        if not isinstance(predicate, dict) or set(predicate) != {
            "metric", "operator", "observed", "limit", "passed",
        }:
            raise ValueError("Poiseuille profile predicate key set mismatch")
        metric = required_text(predicate.get("metric"), "profile predicate metric")
        if metric not in observed_metrics or metric in seen_metrics:
            raise ValueError("Poiseuille profile predicate metric mismatch")
        seen_metrics.add(metric)
        observed = finite(predicate.get("observed"), "profile predicate observed")
        limit = finite(predicate.get("limit"), "profile predicate limit")
        expected_operator = "==" if metric == "exact_wall_no_slip" else "<="
        expected = observed_metrics[metric]
        passed = observed == limit if expected_operator == "==" else observed <= limit
        if (predicate.get("operator") != expected_operator or observed < 0.0 or limit < 0.0 or
                not math.isclose(observed, expected, rel_tol=5e-13, abs_tol=1e-15) or
                predicate.get("passed") is not True or not passed):
            raise ValueError(f"Poiseuille profile acceptance predicate failed: {metric}")
    return payload, rows


def read_key_values(path: Path, context: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "=" not in line:
            raise ValueError(f"{context}: malformed line {number}")
        key, value = line.split("=", 1)
        if not key or key in values:
            raise ValueError(f"{context}: duplicate/empty key")
        values[key] = value
    return values


def seal(run_root: Path, role: str, supervision_dirs: list[Path]) -> dict[str, object]:
    if role not in ROLE_MODES or not supervision_dirs:
        raise ValueError("role A/B/C and at least one supervision directory are required")
    if run_root.is_symlink():
        raise ValueError("run root must not be a symlink")
    root = run_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("run root must be a directory")

    raw = load_json(regular_under(root, root / "raw_export_manifest.json", "raw"), "raw")
    if raw.get("schema") != "internal_nozzle_raw_export_v1":
        raise ValueError("unsupported raw-export schema")
    for key, expected in ROLE_MODES[role].items():
        if raw.get(key) != expected:
            raise ValueError(f"raw export {key} mismatch for Case {role}")
    if raw.get("domain_mode") != "full" or raw.get("exit_velocity_imposed") is not False:
        raise ValueError("raw export domain/exit contract mismatch")
    execution_id = required_text(raw.get("execution_id"), "raw execution_id")
    final_segment_id = required_text(raw.get("segment_id"), "raw segment_id")
    case_id = required_text(raw.get("case_id"), "raw case_id")
    source_sha = canonical_hash(raw.get("source_sha256"), 64, "raw source_sha256")
    source_commit = canonical_hash(
        raw.get("scientific_source_commit"), 40, "raw source commit",
    )
    schedule_sha = canonical_hash(raw.get("schedule_sha256"), 64, "raw schedule")
    transfer_value = required_text(raw.get("precursor_transfer_sha256"), "raw transfer")
    transfer_sha = (
        "not_applicable" if role == "A" and transfer_value == "not_applicable"
        else canonical_hash(transfer_value, 64, "raw transfer")
    )
    completion = raw.get("completion")
    if (not isinstance(completion, dict) or completion != {
        "reached_end_time": True, "stable_flag": True, "mass_balance_passed": True,
    }):
        raise ValueError("raw export does not prove clean scientific completion")
    if (raw.get("cumulative_nozzle_exit_discharge_definition") !=
            "alias_of_cumulative_nozzle_exit_net_volume"):
        raise ValueError("legacy cumulative discharge alias is undefined")
    legacy = finite(raw.get("cumulative_nozzle_exit_discharge"), "raw legacy cumulative")
    net = finite(raw.get("cumulative_nozzle_exit_net_volume"), "raw net cumulative")
    discharged = finite(
        raw.get("cumulative_discharged_liquid_volume"), "raw discharged cumulative",
    )
    if not math.isclose(legacy, net, rel_tol=5e-12, abs_tol=1e-14) or discharged < 0:
        raise ValueError("raw cumulative discharge fields are inconsistent")

    schedule_path = regular_under(root, root / "run_schedule_contract.json", "schedule")
    schedule = load_json(schedule_path, "schedule")
    if set(schedule) != {
        "schema", "schedule_version", "master_tick_dt", "event_time_tolerance",
        "lightweight", "full_field", "checkpoint_stride", "dense_window",
    } or schedule.get("schema") != "internal_nozzle_launch_schedule_v1":
        raise ValueError("launch schedule schema/key set mismatch")
    if sha256_file(schedule_path) != schedule_sha or schedule.get("schedule_version") != raw.get("schedule_version"):
        raise ValueError("launch schedule identity mismatch")
    for block in ("lightweight", "full_field"):
        if not isinstance(schedule.get(block), dict) or set(schedule[block]) != {"base_stride", "dense_stride"}:
            raise ValueError("launch schedule cadence block mismatch")
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
               for value in schedule[block].values()):
            raise ValueError("launch schedule cadence is invalid")
    if (isinstance(schedule.get("checkpoint_stride"), bool) or
            not isinstance(schedule.get("checkpoint_stride"), int) or
            int(schedule["checkpoint_stride"]) <= 0):
        raise ValueError("launch schedule checkpoint stride is invalid")
    dense_window = schedule.get("dense_window")
    if (not isinstance(dense_window, dict) or set(dense_window) != {"start_tick", "end_tick"} or
            any(isinstance(value, bool) or not isinstance(value, int) for value in dense_window.values()) or
            dense_window["start_tick"] < 0 or dense_window["end_tick"] < dense_window["start_tick"]):
        raise ValueError("launch schedule dense window is invalid")
    master_tick_dt = finite(schedule.get("master_tick_dt"), "schedule tick", positive=True)
    event_tolerance = finite(schedule.get("event_time_tolerance"), "schedule tolerance", positive=True)

    supervision: list[dict[str, object]] = []
    segments: list[dict[str, object]] = []
    seen_segments: set[str] = set()
    for index, requested in enumerate(supervision_dirs):
        context = f"supervision {index}"
        directory = (requested if requested.is_absolute() else root / requested).resolve(strict=True)
        if directory.is_symlink() or directory.parent != root / "supervision":
            raise ValueError(f"{context}: must be a direct non-symlink supervision child")
        launch_path = regular_under(root, directory / "launch.json", context)
        terminal_path = regular_under(root, directory / "terminal.json", context)
        launch = load_json(launch_path, context + " launch")
        terminal = load_json(terminal_path, context + " terminal")
        segment_id = required_text(terminal.get("segment_id"), context)
        if segment_id in seen_segments or directory.name != segment_id:
            raise ValueError(f"{context}: duplicate/path-mismatched segment ID")
        seen_segments.add(segment_id)
        for key in ("schema", "run_id", "execution_id", "segment_id", "cwd", "argv",
                    "child_pid", "source_commit", "source_sha256", "command_cwd_sha256"):
            if launch.get(key) != terminal.get(key):
                raise ValueError(f"{context}: launch/terminal {key} mismatch")
        if (terminal.get("schema") != "internal_nozzle_supervision_v2" or
                terminal.get("run_id") != segment_id or
                terminal.get("execution_id") != execution_id or
                terminal.get("cwd") != str(root) or
                terminal.get("source_commit") != source_commit or
                terminal.get("source_sha256") != source_sha or
                terminal.get("exit_code") != 0 or terminal.get("returncode") != 0 or
                terminal.get("terminal_state") != "normal_exit" or
                terminal.get("input_identity_changed") is not False or
                terminal.get("child_exists_after_wait") is not False):
            raise ValueError(f"{context}: no clean same-execution terminal proof")
        stdout_record = member_record(
            root, directory / "stdout.log", context + " stdout", allow_empty=True,
        )
        stderr_record = member_record(
            root, directory / "stderr.log", context + " stderr", allow_empty=True,
        )
        stdout = (directory / "stdout.log").resolve(strict=True)
        stderr = (directory / "stderr.log").resolve(strict=True)
        if (terminal.get("stdout_size_bytes") != stdout.stat().st_size or
                terminal.get("stderr_size_bytes") != stderr.stat().st_size or
                terminal.get("stdout_sha256") != sha256_file(stdout) or
                terminal.get("stderr_sha256") != sha256_file(stderr)):
            raise ValueError(f"{context}: log identity mismatch")
        for lock_name in ("duplicate_lock", "writer_lock"):
            if not isinstance(terminal.get(lock_name), str) or Path(str(terminal[lock_name])).exists():
                raise ValueError(f"{context}: {lock_name} was not released")

        bound_path = regular_under(
            root, root / f"scientific_launch_contract.{segment_id}.json", context,
        )
        bound = load_json(bound_path, context + " bound launch")
        if set(bound) != BOUND_LAUNCH_KEYS:
            raise ValueError(f"{context}: bound launch key set mismatch")
        if (bound.get("schema") != "internal_nozzle_bound_launch_v2" or
                bound.get("execution_id") != execution_id or
                bound.get("segment_id") != segment_id or
                bound.get("case_role") != role or bound.get("case_id") != case_id or
                bound.get("cwd") != str(root) or bound.get("output_dir") != str(root) or
                bound.get("scientific_source_commit") != source_commit or
                bound.get("source_sha256") != source_sha):
            raise ValueError(f"{context}: bound launch identity mismatch")
        if (bound.get("expected_runtime_contract") !=
                str(root / f"scientific_runtime_contract.{segment_id}.json") or
                bound.get("expected_initialization_contract") !=
                str(root / f"initialization_contract.{segment_id}.json") or
                bound.get("execution_contract") !=
                "invoke_supervisor_argv_verbatim_once" or
                bound.get("role_contract") != LAUNCH_ROLE_CONTRACTS[role]):
            raise ValueError(f"{context}: bound launch contract structure mismatch")
        batch_identity = bound.get("batch_identity")
        if not isinstance(batch_identity, dict) or set(batch_identity) != {
            "batch_id", "batch_root", "canonical_lock_root",
        }:
            raise ValueError(f"{context}: batch/lock identity is malformed")
        batch_root = Path(required_text(
            batch_identity.get("batch_root"), context + " batch root",
        )).resolve(strict=True)
        if (batch_root.name != batch_identity.get("batch_id") or
                batch_identity.get("canonical_lock_root") !=
                str(batch_root / ".internal-nozzle-one-solver")):
            raise ValueError(f"{context}: canonical batch/lock identity mismatch")
        try:
            root.relative_to(batch_root)
        except ValueError as error:
            raise ValueError(f"{context}: run root is outside its batch root") from error
        supervisor_contract = bound.get("supervisor")
        if (not isinstance(supervisor_contract, dict) or
                supervisor_contract.get("lock_root") !=
                batch_identity["canonical_lock_root"] or
                terminal.get("writer_lock") !=
                str(Path(str(batch_identity["canonical_lock_root"])) / "one-solver.lock")):
            raise ValueError(f"{context}: supervisor did not use the canonical batch lock")
        if segments and batch_identity != segments[0]["batch_identity"]:
            raise ValueError(f"{context}: segment batch/lock identity changed")
        if segments and any(
            bound.get(key) != segments[0]["bound"].get(key)
            for key in (
                "source_bundle_manifest", "observable_qcc_build_manifest", "schedule",
                "solver", "role_contract", "precursor_transfer",
                "precursor_bulk_target", "poiseuille_profile_validation",
            )
        ):
            raise ValueError(f"{context}: immutable launch authority changed across segments")
        argv = bound.get("solver_argv")
        if not isinstance(argv, list) or argv != terminal.get("argv"):
            raise ValueError(f"{context}: solver argv does not equal bound launch")
        for option, expected in (
            ("--execution-id", execution_id), ("--segment-id", segment_id),
            ("--case-role", role), ("--output-dir", str(root)),
            ("--source-sha", source_sha), ("--source-commit", source_commit),
            ("--schedule-sha", schedule_sha),
            ("--schedule-version", str(schedule["schedule_version"])),
            ("--schedule-tick-dt", format(master_tick_dt, ".17g")),
            ("--schedule-tolerance", format(event_tolerance, ".17g")),
            ("--light-base-stride", str(schedule["lightweight"]["base_stride"])),
            ("--light-dense-stride", str(schedule["lightweight"]["dense_stride"])),
            ("--field-base-stride", str(schedule["full_field"]["base_stride"])),
            ("--field-dense-stride", str(schedule["full_field"]["dense_stride"])),
            ("--checkpoint-stride", str(schedule["checkpoint_stride"])),
            ("--dense-start-tick", str(schedule["dense_window"]["start_tick"])),
            ("--dense-end-tick", str(schedule["dense_window"]["end_tick"])),
        ):
            exact_option(argv, option, expected, context)
        solver_sha = canonical_hash(bound.get("solver", {}).get("sha256") if isinstance(bound.get("solver"), dict) else None, 64, context + " solver")
        exact_option(argv, "--solver-sha256", solver_sha, context)
        expected_role = {
            "A": ("rest", "pressure_driven"),
            "B": ("precursor", "pressure_driven"),
            "C": ("precursor", "profile_controlled"),
        }[role]
        exact_option(argv, "--initial-state", expected_role[0], context)
        exact_option(argv, "--build-variant", expected_role[1], context)
        if role == "A":
            if any(option_values(argv, option, context) for option in (
                "--precursor-transfer", "--precursor-transfer-sha256",
                "--precursor-convergence-sha256", "--precursor-history-sha256",
                "--precursor-target-q", "--precursor-target-area",
                "--precursor-target-velocity-tolerance", "--profile-bulk-velocity",
            )):
                raise ValueError("Case A argv names a precursor transfer")
        else:
            exact_option(argv, "--precursor-transfer-sha256", transfer_sha, context)
            if len(option_values(argv, "--precursor-transfer", context)) != 1:
                raise ValueError(f"{context}: precursor transfer path is not exact")
        expected_inputs = bound.get("verified_inputs")
        input_map = bound_input_map(root, expected_inputs, context)
        validate_verified_inputs(launch, terminal, expected_inputs, context)

        source_bundle_record = bound.get("source_bundle_manifest")
        if (not isinstance(source_bundle_record, dict) or
                set(source_bundle_record) != {"path", "sha256"} or
                source_bundle_record.get("sha256") != source_sha or
                input_map.get("source_bundle_manifest") != source_bundle_record):
            raise ValueError(f"{context}: source-bundle launch binding mismatch")
        bound_schedule = bound.get("schedule")
        expected_schedule = {
            "path": str(schedule_path), "sha256": schedule_sha, **schedule,
        }
        if bound_schedule != expected_schedule:
            raise ValueError(f"{context}: schedule launch binding mismatch")
        solver_record = bound.get("solver")
        if (not isinstance(solver_record, dict) or set(solver_record) != {
                "path", "sha256", "expected_build_variant",
        } or solver_record.get("expected_build_variant") !=
                LAUNCH_ROLE_CONTRACTS[role]["build_variant"] or
                input_map.get("solver_executable") != {
                    "path": solver_record.get("path"),
                    "sha256": solver_record.get("sha256"),
                }):
            raise ValueError(f"{context}: solver launch binding mismatch")
        bound_supervisor = bound.get("supervisor")
        if (not isinstance(bound_supervisor, dict) or set(bound_supervisor) != {
                "path", "sha256", "evidence_dir", "lock_root",
        } or bound_supervisor.get("evidence_dir") != str(directory) or
                input_map.get("supervisor") != {
                    "path": bound_supervisor.get("path"),
                    "sha256": bound_supervisor.get("sha256"),
                }):
            raise ValueError(f"{context}: supervisor launch binding mismatch")
        supervisor_argv = bound.get("supervisor_argv")
        if (not isinstance(supervisor_argv, list) or
                not supervisor_argv or
                not all(isinstance(item, str) for item in supervisor_argv) or
                supervisor_argv.count("--") != 1):
            raise ValueError(f"{context}: supervisor argv is malformed")
        separator = supervisor_argv.index("--")
        if supervisor_argv[separator + 1:] != argv:
            raise ValueError(f"{context}: supervisor argv does not embed exact solver argv")

        runtime_path = regular_under(root, root / f"scientific_runtime_contract.{segment_id}.json", context)
        runtime = load_json(runtime_path, context + " runtime")
        init_path = regular_under(root, root / f"initialization_contract.{segment_id}.json", context)
        init = load_json(init_path, context + " initialization")
        for record, schema_name in ((runtime, "internal_nozzle_scientific_runtime_v1"),
                                    (init, "internal_nozzle_initialization_v2")):
            if (record.get("schema") != schema_name or record.get("execution_id") != execution_id or
                    record.get("segment_id") != segment_id or record.get("case_role") != role or
                    record.get("case_id") != case_id or record.get("solver_sha256") != solver_sha or
                    record.get("source_sha256") != source_sha or
                    record.get("schedule_sha256") != schedule_sha):
                raise ValueError(f"{context}: emitted contract identity mismatch")
        for field in ("initial_state", "inlet_mode", "precursor_pressure_mode"):
            if runtime.get(field) != ROLE_MODES[role][field] or init.get(field) != runtime.get(field):
                raise ValueError(f"{context}: role-specific {field} mismatch")
        if runtime.get("precursor_transfer_sha256") != transfer_sha or init.get("transfer_sha256") != transfer_sha:
            raise ValueError(f"{context}: transfer identity mismatch")
        if init.get("native_restore_unchanged") is not True:
            raise ValueError(f"{context}: native restore is not preserved")
        restore = bound.get("restore")
        if not isinstance(restore, dict):
            raise ValueError(f"{context}: missing restore contract")
        transfer_contract = bound.get("precursor_transfer")
        if role == "A":
            if transfer_contract != {
                    "path": "not_applicable", "sha256": "not_applicable",
                    "manifest_path": "not_applicable",
                    "manifest_sha256": "not_applicable",
            } or bound.get("precursor_bulk_target") != "not_applicable":
                raise ValueError(f"{context}: Case A transfer contract is malformed")
        else:
            if not isinstance(transfer_contract, dict) or set(transfer_contract) != {
                    "path", "sha256", "manifest_path", "manifest_sha256",
                    "producer_unsealed_metadata_sha256", "precursor_source_sha256",
                    "projection_criteria",
            }:
                raise ValueError(f"{context}: precursor transfer contract is malformed")
            for label, path_key, sha_key in (
                ("precursor_transfer", "path", "sha256"),
                ("precursor_transfer_manifest", "manifest_path", "manifest_sha256"),
            ):
                if input_map.get(label) != {
                        "path": transfer_contract.get(path_key),
                        "sha256": transfer_contract.get(sha_key),
                }:
                    raise ValueError(f"{context}: {label} launch binding mismatch")
            canonical_hash(
                transfer_contract.get("producer_unsealed_metadata_sha256"), 64,
                context + " producer metadata SHA",
            )
            canonical_hash(
                transfer_contract.get("precursor_source_sha256"), 64,
                context + " precursor source SHA",
            )
        expected_labels = {
            "solver_executable", "source_bundle_manifest",
            "observable_qcc_build_manifest", "launch_schedule", "supervisor",
        }
        if role in "BC":
            expected_labels |= {
                "precursor_transfer", "precursor_transfer_manifest",
                "precursor_convergence_report", "precursor_terminal_history",
                "transfer_projection_criteria",
            }
        if role == "C":
            expected_labels |= {
                "poiseuille_profile_evidence", "poiseuille_profile_acceptance",
                "poiseuille_reference_artifact", "poiseuille_reference_module",
            }
        elif bound.get("poiseuille_profile_validation") != "not_applicable":
            raise ValueError(f"{context}: Case A/B profile validation must be not_applicable")
        if restore.get("kind") == "checkpoint":
            expected_labels |= {
                "restore_checkpoint", "restore_metadata", "restore_closure",
            }
        if set(input_map) != expected_labels:
            raise ValueError(f"{context}: role/restart verified-input labels mismatch")
        if (input_map["solver_executable"]["sha256"] != solver_sha or
                input_map["source_bundle_manifest"] != source_bundle_record or
                input_map["launch_schedule"] != {
                    "path": str(schedule_path), "sha256": schedule_sha,
                }):
            raise ValueError(f"{context}: core verified-input digest mismatch")
        validate_bound_build(
            bound, input_map, source_sha, source_commit, solver_sha, role, context,
        )

        if role in "BC":
            bulk = bound.get("precursor_bulk_target")
            if not isinstance(bulk, dict) or set(bulk) != {
                "derivation", "conservation_equivalence", "precursor_case_id",
                "convergence_report_sha256", "history_sha256", "terminal_t_star",
                "terminal_Q_l", "terminal_liquid_area", "reported_bulk_velocity",
                "bulk_velocity", "absolute_consistency_tolerance",
            }:
                raise ValueError(f"{context}: precursor bulk-target key set mismatch")
            if (bulk.get("derivation") !=
                    "terminal_converged_precursor_exit_Q_l_over_liquid_area" or
                    not isinstance(bulk.get("conservation_equivalence"), str) or
                    not bulk.get("conservation_equivalence")):
                raise ValueError(f"{context}: precursor target derivation mismatch")
            convergence_sha = canonical_hash(
                bulk.get("convergence_report_sha256"), 64, context + " convergence",
            )
            history_sha = canonical_hash(
                bulk.get("history_sha256"), 64, context + " history",
            )
            if (input_map["precursor_transfer"]["sha256"] != transfer_sha or
                    input_map["precursor_convergence_report"]["sha256"] != convergence_sha or
                    input_map["precursor_terminal_history"]["sha256"] != history_sha):
                raise ValueError(f"{context}: precursor evidence digest mismatch")
            report = load_json(
                Path(input_map["precursor_convergence_report"]["path"]),
                context + " convergence report",
            )
            if (report.get("schema") != "internal_nozzle_precursor_convergence_v1" or
                    report.get("classification") != "precursor_converged" or
                    report.get("pass") is not True or
                    report.get("case_id") != bulk.get("precursor_case_id")):
                raise ValueError(f"{context}: convergence report is not a bound pass")
            report_inputs = report.get("inputs")
            if (not isinstance(report_inputs, list) or not report_inputs or
                    not isinstance(report_inputs[-1], dict) or
                    not isinstance(report_inputs[-1].get("history"), dict) or
                    report_inputs[-1]["history"].get("sha256") != history_sha):
                raise ValueError(f"{context}: convergence report/history binding mismatch")
            q_value = finite(bulk.get("terminal_Q_l"), context + " target Q", positive=True)
            area_value = finite(
                bulk.get("terminal_liquid_area"), context + " target area", positive=True,
            )
            target_value = finite(
                bulk.get("bulk_velocity"), context + " target bulk", positive=True,
            )
            reported_value = finite(
                bulk.get("reported_bulk_velocity"), context + " reported bulk", positive=True,
            )
            target_tolerance = finite(
                bulk.get("absolute_consistency_tolerance"), context + " target tolerance",
                positive=True,
            )
            derived_value = q_value / area_value
            if (not math.isclose(target_value, derived_value, rel_tol=0.0,
                                 abs_tol=target_tolerance) or
                    not math.isclose(reported_value, derived_value, rel_tol=0.0,
                                     abs_tol=target_tolerance)):
                raise ValueError(f"{context}: precursor Q/A target mismatch")
            for field, expected in (
                ("precursor_convergence_sha256", convergence_sha),
                ("precursor_history_sha256", history_sha),
                ("precursor_target_derivation", bulk["derivation"]),
            ):
                if runtime.get(field) != expected:
                    raise ValueError(f"{context}: runtime {field} mismatch")
            for field, expected in (
                ("precursor_target_Q_l", q_value),
                ("precursor_target_liquid_area", area_value),
                ("precursor_target_bulk_velocity", target_value),
                ("precursor_target_velocity_tolerance", target_tolerance),
            ):
                if not math.isclose(finite(runtime.get(field), context + " " + field),
                                    expected, rel_tol=5e-15, abs_tol=1e-15):
                    raise ValueError(f"{context}: runtime {field} mismatch")
            exact_option(argv, "--precursor-convergence-sha256", convergence_sha, context)
            exact_option(argv, "--precursor-history-sha256", history_sha, context)
            exact_option(argv, "--precursor-target-q", format(q_value, ".17g"), context)
            exact_option(argv, "--precursor-target-area", format(area_value, ".17g"), context)
            exact_option(
                argv, "--precursor-target-velocity-tolerance",
                format(target_tolerance, ".17g"), context,
            )
            if role == "C":
                exact_option(argv, "--profile-bulk-velocity", format(target_value, ".17g"), context)
                profile_bulk = finite(init.get("profile_bulk_velocity"), context + " profile bulk")
                unit_bulk = finite(
                    init.get("profile_discrete_unit_bulk"), context + " discrete unit bulk",
                    positive=True,
                )
                normalization = finite(
                    init.get("profile_normalization"), context + " profile normalization",
                    positive=True,
                )
                achieved = finite(
                    init.get("profile_achieved_bulk_velocity"), context + " achieved bulk",
                    positive=True,
                )
                error = finite(init.get("profile_target_absolute_error"), context + " profile error")
                tolerance = finite(
                    init.get("profile_numerical_tolerance"), context + " profile tolerance",
                    positive=True,
                )
                expected_numerical_tolerance = 64.0 * sys.float_info.epsilon * max(
                    1.0, abs(profile_bulk),
                )
                if (init.get("poiseuille_profile_validation_passed") is not True or error < 0.0 or
                        not math.isclose(profile_bulk, target_value, rel_tol=0.0,
                                         abs_tol=target_tolerance) or
                        not math.isclose(achieved, profile_bulk * unit_bulk * normalization,
                                         rel_tol=5e-15, abs_tol=1e-15) or
                        not math.isclose(error, abs(achieved - target_value),
                                         rel_tol=5e-15, abs_tol=1e-15) or error > tolerance):
                    raise ValueError(f"{context}: profile pass artifact is invalid")
                if not math.isclose(tolerance, expected_numerical_tolerance,
                                    rel_tol=5e-15, abs_tol=1e-18):
                    raise ValueError(f"{context}: profile numerical tolerance mismatch")
                profile_record = bound.get("poiseuille_profile_validation")
                if not isinstance(profile_record, dict) or set(profile_record) != {
                    "evidence_path", "evidence_sha256", "acceptance_path",
                    "acceptance_sha256", "assessment_id", "reference_artifact_path",
                    "reference_artifact_sha256", "reference_module_path",
                    "reference_module_sha256", "pass",
                } or profile_record.get("pass") is not True:
                    raise ValueError(f"{context}: profile validation binding is malformed")
                profile_evidence_path = Path(
                    required_text(profile_record.get("evidence_path"), context + " profile evidence")
                )
                profile_acceptance_path = Path(
                    required_text(profile_record.get("acceptance_path"), context + " profile acceptance")
                )
                if (profile_evidence_path != root / "poiseuille_profile_validation.csv" or
                        profile_acceptance_path != root / "poiseuille_profile_acceptance.json"):
                    raise ValueError(f"{context}: profile validation paths are noncanonical")
                profile_payload = acceptance_module().validate_profile_acceptance(
                    Path(input_map["source_bundle_manifest"]["path"]), source_sha,
                    Path(required_text(profile_record.get("reference_artifact_path"),
                                       context + " reference artifact")),
                    canonical_hash(profile_record.get("reference_artifact_sha256"), 64,
                                   context + " reference artifact SHA"),
                    Path(required_text(profile_record.get("reference_module_path"),
                                       context + " reference module")),
                    canonical_hash(profile_record.get("reference_module_sha256"), 64,
                                   context + " reference module SHA"),
                    profile_evidence_path, profile_acceptance_path,
                )
                if (profile_record.get("evidence_sha256") != sha256_file(profile_evidence_path) or
                        profile_record.get("acceptance_sha256") != sha256_file(profile_acceptance_path) or
                        profile_record.get("assessment_id") != profile_payload.get("assessment_id") or
                        input_map["poiseuille_profile_evidence"]["sha256"] !=
                        profile_record.get("evidence_sha256") or
                        input_map["poiseuille_profile_acceptance"]["sha256"] !=
                        profile_record.get("acceptance_sha256") or
                        input_map["poiseuille_reference_artifact"]["sha256"] !=
                        profile_record.get("reference_artifact_sha256") or
                        input_map["poiseuille_reference_module"]["sha256"] !=
                        profile_record.get("reference_module_sha256")):
                    raise ValueError(f"{context}: profile validation digest mismatch")
            elif option_values(argv, "--profile-bulk-velocity", context):
                raise ValueError(f"{context}: Case B argv must not impose an inlet profile")
        segments.append({"segment_id": segment_id, "bound": bound, "runtime": runtime,
                         "initialization": init, "restore": restore, "solver_sha": solver_sha,
                         "argv": argv, "runtime_path": runtime_path, "init_path": init_path,
                         "bound_path": bound_path, "input_map": input_map,
                         "profile_validation": bound.get("poiseuille_profile_validation"),
                         "batch_identity": batch_identity})
        supervision.append({
            "directory": directory.relative_to(root).as_posix(),
            "launch": member_record(root, launch_path, context),
            "terminal": member_record(root, terminal_path, context),
            "stdout": stdout_record,
            "stderr": stderr_record,
            "run_id": segment_id, "execution_id": execution_id,
            "segment_id": segment_id, "exit_code": 0,
        })

    if segments[-1]["segment_id"] != final_segment_id:
        raise ValueError("final raw segment is not the final supervised segment")
    for index, segment in enumerate(segments):
        restore = segment["restore"]
        if index == 0:
            if restore.get("kind") != "fresh" or restore.get("predecessor_segment_id") != "not_applicable":
                raise ValueError("first segment must be fresh")
            if any(option_values(segment["argv"], option, "first segment") for option in (
                "--restore", "--restore-sha256", "--restore-metadata-sha256",
                "--restore-closure-sha256", "--predecessor-segment-id",
            )):
                raise ValueError("first segment argv must not name restart state")
        elif (restore.get("kind") != "checkpoint" or
              restore.get("predecessor_segment_id") != segments[index - 1]["segment_id"]):
            raise ValueError("restart segment does not name its immediate predecessor")
        else:
            for field in ("checkpoint", "metadata", "prediction_closure"):
                if not isinstance(restore.get(field), dict) or set(restore[field]) != {"path", "sha256"}:
                    raise ValueError("restart identity record is malformed")
            exact_option(segment["argv"], "--restore", str(restore["checkpoint"]["path"]), "restart")
            exact_option(segment["argv"], "--restore-sha256", str(restore["checkpoint"]["sha256"]), "restart")
            exact_option(segment["argv"], "--restore-metadata-sha256", str(restore["metadata"]["sha256"]), "restart")
            exact_option(segment["argv"], "--restore-closure-sha256", str(restore["prediction_closure"]["sha256"]), "restart")
            exact_option(segment["argv"], "--predecessor-segment-id", str(restore["predecessor_segment_id"]), "restart")

    hydraulic = csv_rows(root / "hydraulic_plane_metrics.csv", {
        "execution_id", "segment_id", "case_role", "case_id", "plane_label", "t",
        "master_tick", "target_time", "actual_time", "Q_l", "liquid_area",
        "mdot_l", "J_k_liquid", "J_k_mixture", "J_p", "J_total",
        "area_weighted_liquid_velocity", "flux_weighted_liquid_velocity",
        "legacy_Q_l_times_area_weighted_velocity", "I2_liquid", "I3_liquid",
        "beta", "alpha", "momentum_equivalent_velocity",
        "cumulative_nozzle_exit_discharge", "cumulative_nozzle_exit_net_volume",
        "cumulative_discharged_liquid_volume",
        "cumulative_nozzle_exit_discharge_definition",
    }, "hydraulic metrics")
    valid_segment_ids = seen_segments
    exit_rows = []
    segment_order = {str(segment["segment_id"]): index for index, segment in enumerate(segments)}
    segment_ticks: dict[str, list[int]] = {segment: [] for segment in valid_segment_ids}
    plane_previous: dict[str, tuple[int, float, int]] = {}
    previous_discharged = -math.inf
    density_liquid = finite(
        segments[-1]["runtime"].get("density_liquid"), "runtime liquid density",
        positive=True,
    )
    for row in hydraulic:
        if (row["execution_id"] != execution_id or row["segment_id"] not in valid_segment_ids or
                row["case_role"] != role or row["case_id"] != case_id):
            raise ValueError("hydraulic row identity mismatch")
        for field in ("t", "target_time", "actual_time", "Q_l", "liquid_area",
                      "mdot_l", "J_k_liquid", "J_k_mixture", "J_p", "J_total",
                      "area_weighted_liquid_velocity", "flux_weighted_liquid_velocity",
                      "legacy_Q_l_times_area_weighted_velocity", "I2_liquid", "I3_liquid",
                      "beta", "alpha", "momentum_equivalent_velocity",
                      "cumulative_nozzle_exit_discharge",
                      "cumulative_nozzle_exit_net_volume",
                      "cumulative_discharged_liquid_volume"):
            finite(row[field], f"hydraulic {field}")
        try:
            tick = int(row["master_tick"])
        except ValueError as error:
            raise ValueError("hydraulic master_tick is invalid") from error
        target = float(row["target_time"])
        actual = float(row["actual_time"])
        time = float(row["t"])
        current_order = segment_order[row["segment_id"]]
        previous = plane_previous.get(row["plane_label"])
        if (str(tick) != row["master_tick"] or tick < 0 or
                abs(target - tick * master_tick_dt) > event_tolerance or
                abs(actual - target) > event_tolerance or
                abs(time - actual) > event_tolerance or
                (previous is not None and
                 (tick <= previous[0] or actual <= previous[1] or
                  current_order < previous[2]))):
            raise ValueError("hydraulic rows are duplicated, off-schedule or out of order")
        plane_previous[row["plane_label"]] = (tick, actual, current_order)
        segment_ticks[row["segment_id"]].append(tick)
        if row["cumulative_nozzle_exit_discharge_definition"] != "alias_of_cumulative_nozzle_exit_net_volume":
            raise ValueError("hydraulic legacy cumulative alias is undefined")
        if row["plane_label"] == "geometric_nozzle_exit":
            q_value = float(row["Q_l"])
            area = float(row["liquid_area"])
            mdot = float(row["mdot_l"])
            i2 = float(row["I2_liquid"])
            i3 = float(row["I3_liquid"])
            discharged_value = float(row["cumulative_discharged_liquid_volume"])
            if (q_value <= 0.0 or area <= 0.0 or i2 <= 0.0 or i3 <= 0.0 or
                    discharged_value + 1e-14 < previous_discharged):
                raise ValueError("hydraulic exit flow/cumulative state is nonphysical")
            previous_discharged = discharged_value
            identities = {
                "mdot_l": density_liquid * q_value,
                "area_weighted_liquid_velocity": q_value / area,
                "flux_weighted_liquid_velocity": i2 / q_value,
                "J_k_liquid": density_liquid * i2,
                "J_total": float(row["J_k_mixture"]) + float(row["J_p"]),
                "legacy_Q_l_times_area_weighted_velocity": q_value * q_value / area,
                "beta": area * i2 / (q_value * q_value),
                "alpha": area * area * i3 / (q_value * q_value * q_value),
                "momentum_equivalent_velocity": math.sqrt(i2 / area),
            }
            for field, expected in identities.items():
                if not math.isclose(float(row[field]), expected, rel_tol=5e-10,
                                    abs_tol=1e-13):
                    raise ValueError(f"hydraulic exit identity mismatch: {field}")
            if (not math.isclose(float(row["cumulative_nozzle_exit_discharge"]),
                                 float(row["cumulative_nozzle_exit_net_volume"]),
                                 rel_tol=5e-12, abs_tol=1e-14)):
                raise ValueError("hydraulic legacy cumulative alias value mismatch")
            exit_rows.append(row)
    if any(not ticks for ticks in segment_ticks.values()):
        raise ValueError("each supervised segment must own hydraulic evidence")
    ranges = [
        (min(segment_ticks[str(segment["segment_id"])]),
         max(segment_ticks[str(segment["segment_id"])]))
        for segment in segments
    ]
    if any(current[0] <= previous[1] for previous, current in zip(ranges, ranges[1:])):
        raise ValueError("hydraulic segment tick ranges overlap or branch")
    if len(exit_rows) < 3 or float(exit_rows[0]["t"]) != 0.0:
        raise ValueError("hydraulic exit history lacks a fresh t=0 trajectory")
    final_exit = max(exit_rows, key=lambda row: int(row["master_tick"]))
    if (not math.isclose(float(final_exit["cumulative_nozzle_exit_net_volume"]), net,
                         rel_tol=5e-12, abs_tol=1e-14) or
            not math.isclose(float(final_exit["cumulative_discharged_liquid_volume"]), discharged,
                             rel_tol=5e-12, abs_tol=1e-14)):
        raise ValueError("raw/hydraulic terminal cumulative values disagree")
    final_time = float(final_exit["actual_time"])
    if abs(final_time - finite(raw.get("end_time"), "raw end_time")) > event_tolerance:
        raise ValueError("hydraulic history does not reach declared end time")

    profiles = csv_rows(root / "hydraulic_plane_profiles.csv", {
        "execution_id", "segment_id", "case_role", "case_id", "plane_label",
        "t", "x", "y", "z", "f", "ux", "p",
    }, "hydraulic profiles")
    required_planes = {"upstream_plenum", "pre_contraction", "post_contraction",
                       "mid_straight", "geometric_nozzle_exit"}
    if not required_planes.issubset({row["plane_label"] for row in profiles}):
        raise ValueError("hydraulic profiles lack required station coverage")
    if any(row["execution_id"] != execution_id or row["segment_id"] not in valid_segment_ids or
           row["case_role"] != role or row["case_id"] != case_id for row in profiles):
        raise ValueError("hydraulic profile identity mismatch")
    health = csv_rows(root / "solver_health_metrics.csv", {
        "execution_id", "segment_id", "case_role", "case_id", "t", "i", "dt",
        "grid_maxdepth", "total_grid_cells", "mgp_i", "maxlevel",
    }, "solver health")
    for row in health:
        if (row["execution_id"] != execution_id or
                row["segment_id"] not in valid_segment_ids or
                row["case_role"] != role or row["case_id"] != case_id):
            raise ValueError("solver-health identity mismatch")
        if finite(row["dt"], "health dt", positive=True) <= 0 or int(row["total_grid_cells"]) <= 0:
            raise ValueError("solver-health row is invalid")

    projection_acceptance_path: Path | None = None
    projection_acceptance: dict[str, object] | None = None
    if role in "BC":
        projection_path = regular_under(
            root, root / "precursor_transfer_projection.csv", "transfer projection",
        )
        projection = csv_rows(projection_path, {
            "execution_id", "segment_id", "case_role", "case_id", "phase", "t", "i",
            "record_index",
            "divergence_l2", "divergence_max", "velocity_impulse_l2",
            "cell_pressure_change_l2", "projection_pressure_adjustment_l2",
            "fluid_volume", "initial_state", "inlet_mode", "precursor_pressure_mode",
            "transfer_sha256",
        }, "transfer projection")
        if (len(projection) != len(PROJECTION_PHASES) or
                tuple(row["phase"] for row in projection) != PROJECTION_PHASES):
            raise ValueError("transfer projection phase sequence is incomplete/out of order")
        fresh_segment_id = str(segments[0]["segment_id"])
        seen_projection_indices: set[int] = set()
        previous_time = -math.inf
        previous_iteration = -1
        measured_projection: list[dict[str, object]] = []
        for expected_index, row in enumerate(projection):
            try:
                record_index = int(row["record_index"])
                iteration = int(row["i"])
            except ValueError as error:
                raise ValueError("transfer projection index/iteration is invalid") from error
            if (str(record_index) != row["record_index"] or record_index != expected_index or
                    record_index in seen_projection_indices or iteration < previous_iteration):
                raise ValueError("transfer projection records are duplicated/out of order")
            seen_projection_indices.add(record_index)
            record_time = finite(row["t"], "projection time")
            volume = finite(row["fluid_volume"], "projection fluid volume", positive=True)
            if record_time < previous_time:
                raise ValueError("transfer projection time decreased")
            values = {
                metric: finite(row[metric], f"projection {metric}")
                for metric in PROJECTION_METRICS
            }
            if any(value < 0.0 for value in values.values()):
                raise ValueError("transfer projection metric is negative")
            measured_projection.append({
                "record_index": record_index, "phase": row["phase"],
                "t": record_time, "i": iteration, "fluid_volume": volume, **values,
            })
            previous_time = record_time
            previous_iteration = iteration
        if any(row["execution_id"] != execution_id or row["case_role"] != role or
               row["case_id"] != case_id or row["segment_id"] != fresh_segment_id or
               row["segment_id"] not in valid_segment_ids or
               row["initial_state"] != ROLE_MODES[role]["initial_state"] or
               row["inlet_mode"] != ROLE_MODES[role]["inlet_mode"] or
               row["precursor_pressure_mode"] !=
               ROLE_MODES[role]["precursor_pressure_mode"] or
               row["transfer_sha256"] != transfer_sha for row in projection):
            raise ValueError("transfer projection identity mismatch")
        projection_acceptance_path = regular_under(
            root, root / "precursor_transfer_projection_acceptance.json",
            "projection acceptance",
        )
        transfer_contract = segments[0]["bound"].get("precursor_transfer")
        criteria_record = (
            transfer_contract.get("projection_criteria")
            if isinstance(transfer_contract, dict) else None
        )
        if not isinstance(criteria_record, dict) or set(criteria_record) != {
            "path", "sha256", "criteria_id",
        }:
            raise ValueError("projection criteria launch binding is malformed")
        criteria_path = Path(required_text(
            criteria_record.get("path"), "projection criteria path",
        ))
        criteria_sha = canonical_hash(
            criteria_record.get("sha256"), 64, "projection criteria SHA-256",
        )
        if (segments[0]["input_map"]["transfer_projection_criteria"] != {
                "path": str(criteria_path), "sha256": criteria_sha,
        }):
            raise ValueError("projection criteria is not a launch-bound immutable input")
        projection_acceptance = acceptance_module().validate_projection_acceptance(
            criteria_path, criteria_sha, projection_path, projection_acceptance_path,
        )
        if (projection_acceptance.get("execution_id") != execution_id or
                projection_acceptance.get("case_id") != case_id or
                projection_acceptance.get("case_role") != role or
                projection_acceptance.get("segment_id") != fresh_segment_id or
                projection_acceptance.get("criteria", {}).get("criteria_id") !=
                criteria_record.get("criteria_id")):
            raise ValueError("projection acceptance identity mismatch")
    elif (root / "precursor_transfer_projection.csv").exists():
        raise ValueError("Case A must not contain precursor projection evidence")
    elif (root / "precursor_transfer_projection_acceptance.json").exists():
        raise ValueError("Case A must not contain precursor projection acceptance")

    checkpoint_rows = csv_rows(root / "checkpoint_index.csv", {
        "case_id", "domain_mode", "checkpoint_index", "t", "i", "maxlevel",
        "execution_id", "segment_id", "case_role", "solver_sha256", "filename",
        "parent_checkpoint", "source_sha256", "schedule_version", "schedule_sha256",
        "master_tick", "target_time", "actual_time", "initial_state", "inlet_mode",
        "precursor_pressure_mode", "precursor_transfer_sha256",
        "profile_bulk_velocity", "scientific_source_commit",
        "metadata_file", "prediction_closure_state_v4_file",
        "cumulative_nozzle_exit_net_volume", "cumulative_discharged_liquid_volume",
    }, "checkpoint index")
    checkpoint_records: list[dict[str, object]] = []
    previous_checkpoint_tick = -1
    previous_checkpoint_time = -math.inf
    seen_checkpoint_paths: set[Path] = set()
    for expected_index, row in enumerate(checkpoint_rows):
        try:
            checkpoint_index = int(row["checkpoint_index"])
            checkpoint_tick = int(row["master_tick"])
            checkpoint_iteration = int(row["i"])
        except ValueError as error:
            raise ValueError("checkpoint index/tick/iteration is invalid") from error
        checkpoint_time = finite(row["actual_time"], "checkpoint actual time")
        if (row["execution_id"] != execution_id or
                row["segment_id"] not in valid_segment_ids or row["case_role"] != role or
                row["case_id"] != case_id or row["domain_mode"] != "full" or
                row["solver_sha256"] != segments[segment_order[row["segment_id"]]]["solver_sha"] or
                row["source_sha256"] != source_sha or
                row["scientific_source_commit"] != source_commit or
                row["schedule_version"] != schedule["schedule_version"] or
                row["schedule_sha256"] != schedule_sha or
                row["initial_state"] != ROLE_MODES[role]["initial_state"] or
                row["inlet_mode"] != ROLE_MODES[role]["inlet_mode"] or
                row["precursor_pressure_mode"] != ROLE_MODES[role]["precursor_pressure_mode"] or
                row["precursor_transfer_sha256"] != transfer_sha):
            raise ValueError("checkpoint row identity mismatch")
        if (checkpoint_index != expected_index or str(checkpoint_index) != row["checkpoint_index"] or
                checkpoint_tick <= previous_checkpoint_tick or
                checkpoint_time <= previous_checkpoint_time or checkpoint_iteration < 0 or
                abs(float(row["t"]) - checkpoint_time) > event_tolerance or
                abs(float(row["target_time"]) - checkpoint_tick * master_tick_dt) > event_tolerance or
                abs(checkpoint_time - float(row["target_time"])) > event_tolerance):
            raise ValueError("checkpoint sequence is duplicated, off-schedule or out of order")
        dump = regular_under(root, Path(row["filename"]), "checkpoint dump")
        metadata = regular_under(root, Path(row["metadata_file"]), "checkpoint metadata")
        closure = regular_under(root, Path(row["prediction_closure_state_v4_file"]), "checkpoint closure")
        values = read_key_values(metadata, "checkpoint metadata")
        if dump in seen_checkpoint_paths:
            raise ValueError("checkpoint dump path is duplicated")
        seen_checkpoint_paths.add(dump)
        if (values.get("schema") != "internal_nozzle_checkpoint_metadata_v6" or
                values.get("case_id") != case_id or
                values.get("execution_id") != execution_id or values.get("segment_id") != row["segment_id"] or
                values.get("case_role") != role or values.get("solver_sha256") != row["solver_sha256"] or
                values.get("source_sha256") != source_sha or
                values.get("scientific_source_commit") != source_commit or
                values.get("schedule_version") != schedule["schedule_version"] or
                values.get("schedule_sha256") != schedule_sha or
                values.get("master_tick") != row["master_tick"] or
                values.get("iteration") != row["i"] or
                values.get("initial_state") != row["initial_state"] or
                values.get("inlet_mode") != row["inlet_mode"] or
                values.get("precursor_pressure_mode") != row["precursor_pressure_mode"] or
                values.get("precursor_transfer_sha256") != transfer_sha or
                values.get("cumulative_nozzle_exit_discharge_definition") !=
                "alias_of_cumulative_nozzle_exit_net_volume"):
            raise ValueError("checkpoint sidecar identity mismatch")
        row_net = finite(row["cumulative_nozzle_exit_net_volume"], "checkpoint net cumulative")
        row_discharged = finite(
            row["cumulative_discharged_liquid_volume"], "checkpoint discharged cumulative",
        )
        metadata_net = finite(
            values.get("cumulative_nozzle_exit_net_volume"), "checkpoint metadata net cumulative",
        )
        metadata_discharged = finite(
            values.get("cumulative_discharged_liquid_volume"),
            "checkpoint metadata discharged cumulative",
        )
        if (row_discharged < 0.0 or metadata_discharged < 0.0 or
                not math.isclose(row_net, metadata_net, rel_tol=5e-12, abs_tol=1e-14) or
                not math.isclose(row_discharged, metadata_discharged,
                                 rel_tol=5e-12, abs_tol=1e-14)):
            raise ValueError("checkpoint cumulative state is inconsistent")
        matching_exit = [candidate for candidate in exit_rows
                         if candidate["master_tick"] == row["master_tick"]]
        if (len(matching_exit) != 1 or
                not math.isclose(row_net, float(matching_exit[0]["cumulative_nozzle_exit_net_volume"]),
                                 rel_tol=5e-12, abs_tol=1e-14) or
                not math.isclose(row_discharged,
                                 float(matching_exit[0]["cumulative_discharged_liquid_volume"]),
                                 rel_tol=5e-12, abs_tol=1e-14)):
            raise ValueError("checkpoint cumulative state lacks same-tick hydraulic identity")
        checkpoint_records.append({"index": checkpoint_index, "tick": checkpoint_tick,
                                   "time": checkpoint_time,
                                   "segment_id": row["segment_id"], "dump": dump,
                                   "metadata": metadata, "closure": closure,
                                   "dump_sha": sha256_file(dump),
                                   "metadata_sha": sha256_file(metadata),
                                   "closure_sha": sha256_file(closure)})
        previous_checkpoint_tick = checkpoint_tick
        previous_checkpoint_time = checkpoint_time
    for index, segment in enumerate(segments[1:], 1):
        restore = segment["restore"]
        predecessor_records = [item for item in checkpoint_records
                               if item["segment_id"] == segments[index - 1]["segment_id"]]
        if not predecessor_records:
            raise ValueError("predecessor segment has no checkpoint generation")
        latest_predecessor = max(predecessor_records, key=lambda item: int(item["index"]))
        matches = [item for item in predecessor_records
                   if item["dump_sha"] == restore["checkpoint"]["sha256"] and
                   item["metadata_sha"] == restore["metadata"]["sha256"] and
                   item["closure_sha"] == restore["prediction_closure"]["sha256"]]
        if (len(matches) != 1 or matches[0] is not latest_predecessor or
                matches[0]["dump"] != Path(restore["checkpoint"]["path"]).resolve()):
            raise ValueError("restart does not bind the predecessor terminal checkpoint generation")
    checkpoint_manifest = load_json(root / "checkpoint_manifest.json", "checkpoint manifest")
    if (checkpoint_manifest.get("schema") != "internal_nozzle_checkpoint_manifest_v1" or
            checkpoint_manifest.get("execution_id") != execution_id or
            checkpoint_manifest.get("final_segment_id") != final_segment_id or
            checkpoint_manifest.get("case_role") != role or
            checkpoint_manifest.get("case_id") != case_id or
            checkpoint_manifest.get("checkpoint_count") != len(checkpoint_rows) or
            checkpoint_manifest.get("latest_checkpoint_file") !=
            str(checkpoint_records[-1]["dump"])):
        raise ValueError("checkpoint manifest/index identity mismatch")

    final = segments[-1]
    final_runtime = final["runtime"]
    final_init = final["initialization"]
    prerequisites = dict(ROLE_PREREQUISITES[role])
    runtime_projection = dict(final_runtime)
    runtime_projection.update({
        "schema": "internal_nozzle_scientific_runtime_v1",
        "execution_id": execution_id, "segment_id": final_segment_id,
        "case_id": case_id, "case_role": role, "domain_mode": "full",
        **ROLE_MODES[role], "exit_velocity_imposed": False,
        "run_root": str(root), "solver_argv": final["argv"],
        "solver_sha256": final["solver_sha"], "source_sha256": source_sha,
        "scientific_source_commit": source_commit,
        "schedule_version": schedule["schedule_version"],
        "schedule_sha256": schedule_sha, "master_tick_dt": master_tick_dt,
        "precursor_transfer_sha256": transfer_sha,
        "prerequisites": prerequisites,
        "legacy_cumulative_nozzle_exit_discharge_alias":
            "cumulative_nozzle_exit_net_volume",
    })
    if role in "BC":
        bulk = final["bound"]["precursor_bulk_target"]
        runtime_projection["precursor_convergence_evidence"] = {
            "report_sha256": bulk["convergence_report_sha256"],
            "terminal_history_sha256": bulk["history_sha256"],
            "derivation": bulk["derivation"],
            "terminal_Q_l": bulk["terminal_Q_l"],
            "terminal_liquid_area": bulk["terminal_liquid_area"],
            "bulk_velocity": bulk["bulk_velocity"],
        }
        assert projection_acceptance_path is not None
        assert projection_acceptance is not None
        runtime_projection["precursor_transfer_projection_acceptance"] = {
            "path": projection_acceptance_path.name,
            "sha256": sha256_file(projection_acceptance_path),
            "assessment_id": projection_acceptance["assessment_id"],
            "acceptance_basis": projection_acceptance["acceptance_basis"],
            "pass": True,
        }
    if role == "C":
        profile_validation = final["profile_validation"]
        assert isinstance(profile_validation, dict)
        runtime_projection["poiseuille_profile_evidence"] = {
            "source_initialization_contract": final["init_path"].name,
            "source_initialization_contract_sha256": sha256_file(final["init_path"]),
            "task02_profile_evidence_sha256": profile_validation["evidence_sha256"],
            "task02_profile_acceptance_sha256": profile_validation["acceptance_sha256"],
            "task02_assessment_id": profile_validation["assessment_id"],
            "target_bulk_velocity": final_init["profile_bulk_velocity"],
            "achieved_bulk_velocity": final_init["profile_achieved_bulk_velocity"],
            "absolute_error": final_init["profile_target_absolute_error"],
            "numerical_tolerance": final_init["profile_numerical_tolerance"],
            "pass": True,
        }
    init_projection = {
        "schema": "internal_nozzle_initialization_v1",
        "execution_id": execution_id, "segment_id": final_segment_id,
        "initial_state": final_runtime["initial_state"],
        "inlet_mode": final_runtime["inlet_mode"],
        "precursor_pressure_mode": final_runtime["precursor_pressure_mode"],
        "transfer_sha256": transfer_sha,
        "native_restore_unchanged": True,
        "source_segment_contract_sha256": sha256_file(final["init_path"]),
    }
    atomic_create_json(root / "scientific_runtime_contract.json", runtime_projection,
                       "runtime projection")
    atomic_create_json(root / "initialization_contract.json", init_projection,
                       "initialization projection")

    members: dict[str, dict[str, object]] = {
        name: member_record(root, root / name, name) for name in FIXED_MEMBERS
    }
    if role in "BC":
        members["precursor_transfer_projection.csv"] = member_record(
            root, root / "precursor_transfer_projection.csv", "projection",
        )
        assert projection_acceptance_path is not None
        members[projection_acceptance_path.name] = member_record(
            root, projection_acceptance_path, "projection acceptance",
        )
    if role == "C":
        for name in (
            "poiseuille_profile_validation.csv", "poiseuille_profile_acceptance.json",
        ):
            members[name] = member_record(root, root / name, name)
    for segment in segments:
        sid = str(segment["segment_id"])
        for prefix, path_key in (("scientific_launch_contract", "bound_path"),
                                 ("scientific_runtime_contract", "runtime_path"),
                                 ("initialization_contract", "init_path")):
            name = f"{prefix}.{sid}.json"
            members[name] = member_record(root, segment[path_key], name)
    runtime_record = members["scientific_runtime_contract.json"]
    return {
        "schema": "sealed_internal_nozzle_case_package_v2",
        "execution_id": execution_id, "final_segment_id": final_segment_id,
        "case_role": role, "case_id": case_id, "run_root": str(root),
        "source_sha256": source_sha, "scientific_source_commit": source_commit,
        "solver_sha256": final["solver_sha"], "schedule_sha256": schedule_sha,
        "schedule_version": schedule["schedule_version"],
        "precursor_transfer_sha256": transfer_sha,
        "runtime_contract": runtime_record,
        "runtime_contract_sha256": runtime_record["sha256"],
        "validated_evidence": prerequisites,
        "members": members, "supervision": supervision,
        "member_count": len(members),
        "claim_boundary": "local hash-bound completed-run evidence; not scientific acceptance",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--case-role", choices=tuple(ROLE_MODES), required=True)
    parser.add_argument("--supervision-dir", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or args.run_root / "sealed_case_package.json"
    if output.exists() or output.is_symlink():
        parser.error("output must not already exist")
    payload = seal(args.run_root, args.case_role, args.supervision_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        parser.error("temporary output must not already exist")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
