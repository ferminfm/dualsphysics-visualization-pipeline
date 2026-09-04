#!/usr/bin/env python3
"""Deterministically compare contracted rest, precursor, and control cases."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
from pathlib import Path

CORE = (
    "Q_l", "mdot_l", "area_weighted_liquid_velocity",
    "flux_weighted_liquid_velocity", "J_k_liquid", "J_p", "J_total",
    "forcing_to_plane_pressure_drop", "liquid_area",
)
PROFILE_METRICS = ("beta", "alpha", "momentum_equivalent_velocity")
METRICS = CORE + PROFILE_METRICS
PACKAGE_SCHEMA = "sealed_internal_nozzle_case_package_v2"
RUNTIME_CONTRACT_SCHEMA = "internal_nozzle_scientific_runtime_v1"
SCHEDULE_CONTRACT_SCHEMA = "internal_nozzle_launch_schedule_v1"
RUNTIME_CONTRACT_MEMBER = "scientific_runtime_contract.json"
MINIMUM_STATIONARITY_DWELL_T_STAR = 1.0
TIME_IDENTITY_COLUMNS = ("master_tick", "target_time", "actual_time")
INTERPOLATED_FIELDS = (
    "t", "t_star", "target_time", "actual_time",
    "cumulative_discharged_liquid_volume",
    "cumulative_discharged_liquid_volume_normalized",
    "cumulative_nozzle_exit_net_volume",
    "cumulative_nozzle_exit_net_volume_normalized", *METRICS,
)
GEOMETRY_FIELDS = ("W", "H", "Dh", "A0", "nozzle_exit_x")
COMPATIBILITY_FIELDS = (
    "domain_mode", "source_sha256", "scientific_source_commit",
    "schedule_version", "schedule_sha256", "maxlevel", "diagnostic_dt",
    "master_tick_dt",
)
CASE_MODES: dict[str, dict[str, object]] = {
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
REQUIRED_PACKAGE_MEMBERS = (
    "raw_export_manifest.json", "hydraulic_plane_metrics.csv",
    "hydraulic_plane_profiles.csv", "solver_health_metrics.csv",
    "initialization_contract.json", "run_schedule_contract.json",
    RUNTIME_CONTRACT_MEMBER,
    "checkpoint_manifest.json", "checkpoint_index.csv",
    "visual_pipeline_case_summary.csv",
)

# This is the complete consumer-side prerequisite matrix for package v2.  Keep
# the names centralized: producer-side spelling changes should require edits
# here, rather than weakening validation throughout the comparator.
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
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_file(path: Path, context: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{context}: symlinks are forbidden: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{context}: missing file: {path}") from error
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"{context}: not a nonempty regular file: {path}")
    return resolved


def verify_packaged_record(
    root: Path, record: object, context: str, *,
    expected_path: str | None = None, allow_empty: bool = False,
) -> Path:
    if not isinstance(record, dict):
        raise ValueError(f"{context}: package record must be an object")
    relative = record.get("path")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{context}: package path must be a nonempty string")
    if expected_path is not None and relative != expected_path:
        raise ValueError(f"{context}: unexpected package path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{context}: nonportable package path")
    unresolved = root / candidate
    if unresolved.is_symlink():
        raise ValueError(f"{context}: symlink forbidden")
    try:
        resolved = unresolved.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{context}: missing packaged file") from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{context}: packaged file escapes run root") from error
    if not resolved.is_file() or (not allow_empty and resolved.stat().st_size <= 0):
        raise ValueError(f"{context}: packaged file is not an admissible regular file")
    size, digest = record.get("size_bytes"), record.get("sha256")
    if (isinstance(size, bool) or not isinstance(size, int) or
            size != resolved.stat().st_size or not isinstance(digest, str) or
            sha256_file(resolved) != digest):
        raise ValueError(f"{context}: packaged file identity mismatch")
    return resolved


def finite_number(value: object, field: str, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{context}: invalid {field}") from error
    if not math.isfinite(result):
        raise ValueError(f"{context}: nonfinite {field}")
    return result


def number(row: dict[str, str], field: str) -> float:
    return finite_number(row.get(field), field, "CSV row")


def required_text(mapping: dict[str, object], field: str, context: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: missing/invalid {field}")
    return value


def load_json_object(path: Path, context: str) -> dict[str, object]:
    resolved = regular_file(path, context)
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{context}: unreadable JSON object") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{context}: expected a JSON object")
    return payload


def hash_text(mapping: dict[str, object], field: str, context: str,
              *, allow_not_applicable: bool = False) -> str:
    value = required_text(mapping, field, context).lower()
    if allow_not_applicable and value == "not_applicable":
        return value
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{context}: {field} must be 64 lowercase hex digits")
    return value


def option_values(argv: list[str], option: str, context: str) -> list[str]:
    values: list[str] = []
    for index, value in enumerate(argv):
        if value != option:
            continue
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            raise ValueError(f"{context}: {option} lacks a value")
        values.append(argv[index + 1])
    if len(values) > 1:
        raise ValueError(f"{context}: duplicate {option}")
    return values


def exact_option(argv: list[str], option: str, expected: str, context: str) -> None:
    values = option_values(argv, option, context)
    if values != [expected]:
        raise ValueError(f"{context}: {option} must equal {expected!r}")


def verified_input_hashes(record: dict[str, object], context: str) -> set[str]:
    inputs = record.get("verified_inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError(f"{context}: verified_inputs must be a nonempty list")
    observed: set[str] = set()
    for index, item in enumerate(inputs):
        item_context = f"{context}: verified_inputs {index}"
        if not isinstance(item, dict):
            raise ValueError(f"{item_context}: expected an object")
        expected = hash_text(item, "expected_sha256", item_context)
        if (hash_text(item, "observed_sha256", item_context) != expected or
                hash_text(item, "observed_sha256_after", item_context) != expected or
                item.get("verified") is not True or
                item.get("unchanged_during_run") is not True):
            raise ValueError(f"{item_context}: input identity not proven immutable")
        if expected in observed:
            raise ValueError(f"{item_context}: duplicate verified input hash")
        observed.add(expected)
    return observed


def read_runtime_contract(path: Path, role: str, root: Path) -> dict[str, object]:
    """Validate the package-v2 launch contract before consuming case data."""
    payload = load_json_object(path, f"Case {role} scientific runtime contract")
    context = f"{path} (Case {role} runtime contract)"
    if payload.get("schema") != RUNTIME_CONTRACT_SCHEMA:
        raise ValueError(f"{context}: unsupported schema")
    for field in (
        "execution_id", "segment_id", "case_id", "case_role", "domain_mode",
        "selected_case", "initial_state", "inlet_mode", "precursor_pressure_mode",
        "precursor_transfer_sha256", "source_sha256", "scientific_source_commit",
        "solver_sha256", "schedule_version", "schedule_sha256",
    ):
        required_text(payload, field, context)
    if payload["case_role"] != role:
        raise ValueError(f"{context}: case_role mismatch")
    if payload["domain_mode"] != "full":
        raise ValueError(f"{context}: domain_mode must be full")
    for field, expected in CASE_MODES[role].items():
        if payload.get(field) != expected:
            raise ValueError(
                f"{context}: {field} must be {expected!r}, found {payload.get(field)!r}"
            )
    if payload.get("exit_velocity_imposed") is not False:
        raise ValueError(f"{context}: exit_velocity_imposed must be false")
    if payload.get("run_root") != str(root):
        raise ValueError(f"{context}: run_root must equal the sealed package directory")

    source_sha = hash_text(payload, "source_sha256", context)
    solver_sha = hash_text(payload, "solver_sha256", context)
    schedule_sha = hash_text(payload, "schedule_sha256", context)
    transfer_sha = hash_text(
        payload, "precursor_transfer_sha256", context, allow_not_applicable=True,
    )
    source_commit = required_text(payload, "scientific_source_commit", context).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError(f"{context}: scientific_source_commit must be 40 lowercase hex digits")
    if role == "A" and transfer_sha != "not_applicable":
        raise ValueError(f"{context}: Case A transfer must be not_applicable")
    if role in "BC" and transfer_sha == "not_applicable":
        raise ValueError(f"{context}: Case {role} must bind a precursor transfer")

    prerequisites = payload.get("prerequisites")
    if prerequisites != ROLE_PREREQUISITES[role]:
        raise ValueError(f"{context}: role prerequisite matrix mismatch")
    argv = payload.get("solver_argv")
    if (not isinstance(argv, list) or not argv or
            not all(isinstance(item, str) and item for item in argv)):
        raise ValueError(f"{context}: solver_argv must be a nonempty string array")
    exact_option(argv, "--output-dir", str(root), context)
    exact_option(argv, "--source-sha", source_sha, context)
    exact_option(argv, "--source-commit", source_commit, context)
    exact_option(argv, "--schedule-sha", schedule_sha, context)
    exact_option(argv, "--schedule-version", str(payload["schedule_version"]), context)
    if role == "A":
        if option_values(argv, "--precursor-transfer", context) or option_values(
            argv, "--precursor-transfer-sha256", context
        ):
            raise ValueError(f"{context}: Case A argv must not name a precursor transfer")
    else:
        if not option_values(argv, "--precursor-transfer", context):
            raise ValueError(f"{context}: Case {role} argv lacks --precursor-transfer")
        exact_option(argv, "--precursor-transfer-sha256", transfer_sha, context)

    normalized = dict(payload)
    normalized.update({
        "source_sha256": source_sha,
        "scientific_source_commit": source_commit,
        "solver_sha256": solver_sha,
        "schedule_sha256": schedule_sha,
        "precursor_transfer_sha256": transfer_sha,
        "solver_argv": list(argv),
        "contract_path": str(path),
        "contract_sha256": sha256_file(path),
    })
    return normalized


def read_contract(path: Path, role: str) -> dict[str, object]:
    """Read one solver-produced case contract and enforce its exact role."""
    resolved = regular_file(path, f"Case {role} contract")
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{path}: unreadable case contract") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: case contract must be a JSON object")
    context = f"{path} (Case {role})"
    if payload.get("schema") != "internal_nozzle_raw_export_v1":
        raise ValueError(f"{context}: unsupported raw-export schema")
    for field in (
        "execution_id", "segment_id", "case_id", "domain_mode", "selected_case",
        "initial_state", "inlet_mode",
        "precursor_pressure_mode", "precursor_transfer_sha256", "source_sha256",
        "scientific_source_commit", "schedule_version", "schedule_sha256",
    ):
        required_text(payload, field, context)
    if payload["domain_mode"] != "full":
        raise ValueError(f"{context}: domain_mode must be full")
    for field, expected in CASE_MODES[role].items():
        if payload.get(field) != expected:
            raise ValueError(
                f"{context}: {field} must be {expected!r}, found {payload.get(field)!r}"
            )
    if payload.get("exit_velocity_imposed") is not False:
        raise ValueError(f"{context}: exit_velocity_imposed must be false")
    source_sha = required_text(payload, "source_sha256", context)
    source_commit = required_text(payload, "scientific_source_commit", context)
    schedule_sha = required_text(payload, "schedule_sha256", context)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", source_sha):
        raise ValueError(f"{context}: source_sha256 must be 64 hex digits")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_commit):
        raise ValueError(f"{context}: scientific_source_commit must be 40 hex digits")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", schedule_sha):
        raise ValueError(f"{context}: schedule_sha256 must be 64 hex digits")
    transfer_sha = required_text(payload, "precursor_transfer_sha256", context)
    if role == "A":
        if transfer_sha != "not_applicable":
            raise ValueError(f"{context}: rest start must not name a precursor transfer")
    elif not re.fullmatch(r"[0-9a-fA-F]{64}", transfer_sha):
        raise ValueError(f"{context}: precursor transfer identity must be 64 hex digits")
    maxlevel = payload.get("maxlevel")
    if isinstance(maxlevel, bool) or not isinstance(maxlevel, int) or maxlevel < 1:
        raise ValueError(f"{context}: maxlevel must be a positive integer")
    for field in ("diagnostic_dt", "master_tick_dt"):
        if finite_number(payload.get(field), field, context) <= 0.0:
            raise ValueError(f"{context}: {field} must be positive")
    geometry = payload.get("geometry")
    if not isinstance(geometry, dict):
        raise ValueError(f"{context}: geometry must be an object")
    normalized_geometry = {
        field: finite_number(geometry.get(field), f"geometry.{field}", context)
        for field in GEOMETRY_FIELDS
    }
    if any(normalized_geometry[field] <= 0.0 for field in ("W", "H", "Dh", "A0")):
        raise ValueError(f"{context}: W, H, Dh and A0 must be positive")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"{context}: files must be an object")
    for field, expected in (
        ("hydraulic_plane_metrics", "hydraulic_plane_metrics.csv"),
        ("hydraulic_plane_profiles", "hydraulic_plane_profiles.csv"),
        ("solver_health_metrics", "solver_health_metrics.csv"),
        ("initialization_contract", "initialization_contract.json"),
    ):
        if files.get(field) != expected:
            raise ValueError(f"{context}: files.{field} must be {expected}")
    normalized = dict(payload)
    normalized.update({
        "source_sha256": source_sha.lower(), "schedule_sha256": schedule_sha.lower(),
        "scientific_source_commit": source_commit.lower(),
        "precursor_transfer_sha256": (
            transfer_sha.lower() if transfer_sha != "not_applicable" else transfer_sha
        ),
        "diagnostic_dt": finite_number(payload["diagnostic_dt"], "diagnostic_dt", context),
        "master_tick_dt": finite_number(payload["master_tick_dt"], "master_tick_dt", context),
        "geometry": normalized_geometry, "files": dict(files),
        "contract_path": str(resolved),
        "contract_sha256": sha256_file(resolved), "case_role": role,
    })
    return normalized


def read_package(path: Path, role: str) -> dict[str, object]:
    resolved = regular_file(path, f"Case {role} sealed package")
    package = load_json_object(resolved, f"Case {role} sealed package")
    if (package.get("schema") != PACKAGE_SCHEMA or package.get("case_role") != role):
        raise ValueError(f"{path}: sealed package schema/role mismatch")
    root = resolved.parent.resolve(strict=True)
    if package.get("run_root") != str(root):
        raise ValueError(f"{path}: sealed package run-root identity mismatch")
    execution_id = required_text(package, "execution_id", str(path))
    final_segment_id = required_text(package, "final_segment_id", str(path))
    if package.get("validated_evidence") != ROLE_PREREQUISITES[role]:
        raise ValueError(f"{path}: package role prerequisite evidence mismatch")
    members = package.get("members")
    if not isinstance(members, dict):
        raise ValueError(f"{path}: sealed package members must be an object")
    required = set(REQUIRED_PACKAGE_MEMBERS)
    if role in "BC":
        required.add("precursor_transfer_projection.csv")
    if not required.issubset(members):
        raise ValueError(f"{path}: sealed package lacks required members")
    resolved_members: dict[str, str] = {}
    for name in required:
        member = verify_packaged_record(
            root, members.get(name), f"Case {role} sealed member {name}",
            expected_path=name,
        )
        resolved_members[name] = str(member)

    runtime_record = package.get("runtime_contract")
    runtime_path = verify_packaged_record(
        root, runtime_record, f"Case {role} runtime-contract binding",
        expected_path=RUNTIME_CONTRACT_MEMBER,
    )
    if runtime_record != members.get(RUNTIME_CONTRACT_MEMBER):
        raise ValueError(f"{path}: top-level/member runtime-contract records differ")
    runtime = read_runtime_contract(runtime_path, role, root)
    if (runtime["execution_id"] != execution_id or
            runtime["segment_id"] != final_segment_id):
        raise ValueError(f"{path}: runtime/package execution identity mismatch")

    schedule_path = Path(resolved_members["run_schedule_contract.json"])
    schedule = load_json_object(schedule_path, f"Case {role} schedule contract")
    if schedule.get("schema") != SCHEDULE_CONTRACT_SCHEMA:
        raise ValueError(f"{path}: unsupported launch-schedule schema")
    if (schedule.get("schedule_version") != runtime["schedule_version"] or
            sha256_file(schedule_path) != runtime["schedule_sha256"]):
        raise ValueError(f"{path}: schedule file/runtime identity mismatch")
    master_tick_dt = finite_number(
        schedule.get("master_tick_dt"), "master_tick_dt", f"Case {role} schedule",
    )
    event_tolerance = finite_number(
        schedule.get("event_time_tolerance"), "event_time_tolerance",
        f"Case {role} schedule",
    )
    if master_tick_dt <= 0.0 or event_tolerance < 0.0:
        raise ValueError(f"{path}: invalid launch-schedule timing values")
    for block_name in ("lightweight", "full_field"):
        block = schedule.get(block_name)
        if not isinstance(block, dict) or set(block) != {"base_stride", "dense_stride"}:
            raise ValueError(f"{path}: malformed schedule {block_name} block")
        for key in ("base_stride", "dense_stride"):
            value = block[key]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{path}: invalid schedule {block_name}.{key}")
    checkpoint_stride = schedule.get("checkpoint_stride")
    if (isinstance(checkpoint_stride, bool) or
            not isinstance(checkpoint_stride, int) or checkpoint_stride <= 0):
        raise ValueError(f"{path}: invalid schedule checkpoint_stride")
    dense_window = schedule.get("dense_window")
    if (not isinstance(dense_window, dict) or
            set(dense_window) != {"start_tick", "end_tick"}):
        raise ValueError(f"{path}: malformed schedule dense_window")
    for key in ("start_tick", "end_tick"):
        if (isinstance(dense_window[key], bool) or
                not isinstance(dense_window[key], int)):
            raise ValueError(f"{path}: invalid schedule dense_window.{key}")
    if dense_window["start_tick"] > dense_window["end_tick"]:
        raise ValueError(f"{path}: inverted schedule dense_window")

    initialization_path = Path(resolved_members["initialization_contract.json"])
    initialization = load_json_object(
        initialization_path, f"Case {role} initialization contract",
    )
    if initialization.get("schema") != "internal_nozzle_initialization_v1":
        raise ValueError(f"{path}: unsupported initialization schema")
    for field in (
        "execution_id", "segment_id", "initial_state", "inlet_mode",
        "precursor_pressure_mode",
    ):
        expected = runtime[field]
        if initialization.get(field) != expected:
            raise ValueError(f"{path}: initialization/runtime {field} mismatch")
    if initialization.get("native_restore_unchanged") is not True:
        raise ValueError(f"{path}: initialization does not preserve native restore")
    if initialization.get("transfer_sha256") != runtime["precursor_transfer_sha256"]:
        raise ValueError(f"{path}: initialization/runtime transfer identity mismatch")

    supervision = package.get("supervision")
    if not isinstance(supervision, list) or not supervision:
        raise ValueError(f"{path}: sealed package lacks terminal supervision")
    segment_ids: list[str] = []
    for index, item in enumerate(supervision):
        context = f"{path}: supervision {index}"
        if not isinstance(item, dict) or item.get("exit_code") != 0:
            raise ValueError(f"{context}: invalid packaged supervision result")
        item_execution = required_text(item, "execution_id", context)
        item_segment = required_text(item, "segment_id", context)
        if item_execution != execution_id or item.get("run_id") != item_segment:
            raise ValueError(f"{context}: execution/segment/run identity mismatch")
        if item_segment in segment_ids:
            raise ValueError(f"{context}: duplicate segment identity")
        segment_ids.append(item_segment)
        launch_path = verify_packaged_record(root, item.get("launch"), f"{context} launch")
        terminal_path = verify_packaged_record(root, item.get("terminal"), f"{context} terminal")
        stdout_path = verify_packaged_record(
            root, item.get("stdout"), f"{context} stdout", allow_empty=True,
        )
        stderr_path = verify_packaged_record(
            root, item.get("stderr"), f"{context} stderr", allow_empty=True,
        )
        try:
            launch = json.loads(
                launch_path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
            )
            terminal = json.loads(
                terminal_path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
            )
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"{context}: malformed supervision JSON") from error
        if not isinstance(launch, dict) or not isinstance(terminal, dict):
            raise ValueError(f"{context}: supervision records must be objects")
        for key in (
            "run_id", "execution_id", "segment_id", "cwd", "argv", "child_pid",
            "source_commit", "source_sha256",
        ):
            if launch.get(key) != terminal.get(key):
                raise ValueError(f"{context}: launch/terminal {key} mismatch")
        argv = terminal.get("argv")
        if (not isinstance(argv, list) or not argv or
                not all(isinstance(value, str) and value for value in argv)):
            raise ValueError(f"{context}: invalid terminal argv")
        exact_option(argv, "--output-dir", str(root), context)
        exact_option(argv, "--source-sha", str(runtime["source_sha256"]), context)
        exact_option(argv, "--source-commit", str(runtime["scientific_source_commit"]), context)
        exact_option(argv, "--schedule-sha", str(runtime["schedule_sha256"]), context)
        exact_option(argv, "--schedule-version", str(runtime["schedule_version"]), context)
        if role == "A":
            if option_values(argv, "--precursor-transfer", context) or option_values(
                argv, "--precursor-transfer-sha256", context
            ):
                raise ValueError(f"{context}: Case A segment names a precursor transfer")
        else:
            if not option_values(argv, "--precursor-transfer", context):
                raise ValueError(f"{context}: missing precursor transfer")
            exact_option(
                argv, "--precursor-transfer-sha256",
                str(runtime["precursor_transfer_sha256"]), context,
            )
        verified_hashes = verified_input_hashes(terminal, context)
        required_hashes = {
            str(runtime["source_sha256"]), str(runtime["solver_sha256"]),
            str(runtime["schedule_sha256"]),
        }
        if role in "BC":
            required_hashes.add(str(runtime["precursor_transfer_sha256"]))
        if not required_hashes.issubset(verified_hashes):
            raise ValueError(f"{context}: immutable input evidence is incomplete")
        if (terminal.get("run_id") != item.get("run_id") or
                terminal.get("execution_id") != execution_id or
                terminal.get("segment_id") != item_segment or
                terminal.get("cwd") != str(root) or
                terminal.get("source_commit") != runtime["scientific_source_commit"] or
                terminal.get("source_sha256") != runtime["source_sha256"] or
                terminal.get("exit_code") != 0 or
                terminal.get("terminal_state") != "normal_exit" or
                terminal.get("input_identity_changed") is not False or
                terminal.get("child_exists_after_wait") is not False or
                terminal.get("stdout_size_bytes") != stdout_path.stat().st_size or
                terminal.get("stderr_size_bytes") != stderr_path.stat().st_size or
                terminal.get("stdout_sha256") != sha256_file(stdout_path) or
                terminal.get("stderr_sha256") != sha256_file(stderr_path)):
            raise ValueError(f"{context}: terminal supervision evidence mismatch")
        if item_segment == final_segment_id and argv != runtime["solver_argv"]:
            raise ValueError(f"{context}: final segment argv differs from runtime contract")
    if segment_ids[-1] != final_segment_id:
        raise ValueError(f"{path}: final_segment_id is not the terminal supervision segment")

    contract = read_contract(Path(resolved_members["raw_export_manifest.json"]), role)
    for key in (
        "execution_id", "case_id", "source_sha256", "scientific_source_commit",
        "schedule_version", "schedule_sha256", "precursor_transfer_sha256",
    ):
        if package.get(key) != contract.get(key) or runtime.get(key) != contract.get(key):
            raise ValueError(f"{path}: package/runtime/raw {key} mismatch")
    if contract.get("segment_id") != final_segment_id:
        raise ValueError(f"{path}: raw export does not identify final segment")
    if (not math.isclose(float(contract["master_tick_dt"]), master_tick_dt,
                         rel_tol=0.0, abs_tol=1e-15) or
            runtime.get("master_tick_dt", master_tick_dt) != master_tick_dt):
        raise ValueError(f"{path}: schedule/runtime/raw master_tick_dt mismatch")
    for key in (
        "solver_sha256", "schedule_sha256", "precursor_transfer_sha256",
    ):
        if package.get(key) != runtime.get(key):
            raise ValueError(f"{path}: package/runtime {key} mismatch")
    if (package.get("runtime_contract_sha256") != runtime["contract_sha256"] or
            package.get("scientific_source_commit") != runtime["scientific_source_commit"]):
        raise ValueError(f"{path}: package runtime/source pin mismatch")
    contract["sealed_package_path"] = str(resolved)
    contract["sealed_package_sha256"] = sha256_file(resolved)
    contract["sealed_member_paths"] = resolved_members
    contract["execution_id"] = execution_id
    contract["final_segment_id"] = final_segment_id
    contract["solver_sha256"] = runtime["solver_sha256"]
    contract["runtime_contract_sha256"] = runtime["contract_sha256"]
    contract["runtime_contract"] = runtime
    contract["master_tick_dt"] = master_tick_dt
    contract["event_time_tolerance"] = event_tolerance
    contract["supervision_segment_ids"] = segment_ids
    return contract


def compatible_contracts(
    contracts: dict[str, dict[str, object]], dh: float
) -> dict[str, object]:
    if set(contracts) != set(CASE_MODES):
        raise ValueError("case contracts must contain exactly A, B, and C")
    case_ids = [str(contracts[role]["case_id"]) for role in "ABC"]
    if len(set(case_ids)) != 3:
        raise ValueError("Case A/B/C case_id values must be distinct")
    mode_tuples = [
        tuple(contracts[role][field] for field in CASE_MODES[role]) for role in "ABC"
    ]
    if len(set(mode_tuples)) != 3:
        raise ValueError("Case A/B/C mode identities must be distinct")
    reference = contracts["A"]
    for role in "BC":
        candidate = contracts[role]
        for field in COMPATIBILITY_FIELDS:
            if candidate[field] != reference[field]:
                raise ValueError(
                    f"Case {role}: incompatible {field}: "
                    f"{candidate[field]!r} != {reference[field]!r}"
                )
        reference_geometry = reference["geometry"]
        candidate_geometry = candidate["geometry"]
        assert isinstance(reference_geometry, dict) and isinstance(candidate_geometry, dict)
        for field in GEOMETRY_FIELDS:
            if not math.isclose(float(candidate_geometry[field]), float(reference_geometry[field]),
                                rel_tol=1e-12, abs_tol=1e-14):
                raise ValueError(f"Case {role}: incompatible geometry.{field}")
    if (contracts["B"]["precursor_transfer_sha256"] !=
            contracts["C"]["precursor_transfer_sha256"]):
        raise ValueError("Cases B and C must use the same precursor transfer identity")
    geometry = reference["geometry"]
    assert isinstance(geometry, dict)
    contract_dh = float(geometry["Dh"])
    if not math.isclose(dh, contract_dh, rel_tol=1e-12, abs_tol=1e-14):
        raise ValueError(f"--dh {dh!r} does not match contracted geometry.Dh {contract_dh!r}")
    return {
        "status": "compatible",
        "case_ids": {role: contracts[role]["case_id"] for role in "ABC"},
        "mode_identities": {
            role: {field: contracts[role][field] for field in CASE_MODES[role]}
            for role in "ABC"
        },
        "common": {field: reference[field] for field in COMPATIBILITY_FIELDS},
        "geometry": geometry,
        "precursor_transfer_sha256": contracts["B"]["precursor_transfer_sha256"],
        "contract_sha256": {role: contracts[role]["contract_sha256"] for role in "ABC"},
    }


def load(path: Path, dh: float, role: str, contract: dict[str, object]) -> tuple[
    list[dict[str, float]], dict[str, object]
]:
    resolved = regular_file(path, f"Case {role} hydraulic metrics")
    sealed = contract.get("sealed_member_paths")
    if not isinstance(sealed, dict):
        raise ValueError(f"Case {role}: missing sealed-package member map")
    expected = regular_file(
        Path(str(sealed["hydraulic_plane_metrics.csv"])),
        f"Case {role} sealed hydraulic metrics",
    )
    if resolved != expected:
        raise ValueError(f"Case {role}: metrics are not the contracted run member")
    with resolved.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: missing/duplicate CSV header")
        required = {
            "execution_id", "segment_id", "case_id", "plane_label", "t",
            *TIME_IDENTITY_COLUMNS, "maxlevel", "initial_state", "inlet_mode",
            "precursor_pressure_mode", "precursor_transfer_sha256",
            "cumulative_discharged_liquid_volume",
            "cumulative_nozzle_exit_net_volume", *METRICS,
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        rows = [row for row in reader if row.get("plane_label") == "geometric_nozzle_exit"]
    if len(rows) < 3:
        raise ValueError(f"{path}: insufficient exit-plane rows")
    expected_rows = {
        "execution_id": contract["execution_id"], "case_id": contract["case_id"],
        "initial_state": contract["initial_state"],
        "inlet_mode": contract["inlet_mode"],
        "precursor_pressure_mode": contract["precursor_pressure_mode"],
        "precursor_transfer_sha256": contract["precursor_transfer_sha256"],
    }
    output: list[dict[str, float]] = []
    previous: dict[str, float] | None = None
    seen_ticks: set[int] = set()
    valid_segments = set(contract["supervision_segment_ids"])
    tick_dt = float(contract["master_tick_dt"])
    event_tolerance = float(contract["event_time_tolerance"])
    nozzle_volume_scale = float(contract["geometry"]["A0"]) * dh
    if nozzle_volume_scale <= 0.0:
        raise ValueError(f"Case {role}: invalid nozzle discharge scale")
    def row_tick(row: dict[str, str]) -> int:
        value = number(row, "master_tick")
        if not value.is_integer():
            raise ValueError(f"{path}: master_tick must be an exact integer")
        return int(value)

    for index, row in enumerate(sorted(rows, key=row_tick)):
        context = f"{path}: exit row {index} (Case {role})"
        for field, expected in expected_rows.items():
            if row.get(field) != str(expected):
                raise ValueError(f"{context}: {field} does not match contract")
        level = finite_number(row.get("maxlevel"), "maxlevel", context)
        if not level.is_integer() or int(level) != contract["maxlevel"]:
            raise ValueError(f"{context}: maxlevel does not match contract")
        current = {name: finite_number(row.get(name), name, context) for name in METRICS}
        tick = row_tick(row)
        if tick in seen_ticks:
            raise ValueError(f"{path}: duplicate master_tick {tick}")
        seen_ticks.add(tick)
        if row.get("segment_id") not in valid_segments:
            raise ValueError(f"{context}: segment_id is not in sealed supervision lineage")
        target_time = finite_number(row.get("target_time"), "target_time", context)
        actual_time = finite_number(row.get("actual_time"), "actual_time", context)
        legacy_time = finite_number(row.get("t"), "t", context)
        canonical_target = tick * tick_dt
        if not math.isclose(target_time, canonical_target, rel_tol=0.0,
                            abs_tol=event_tolerance):
            raise ValueError(f"{context}: target_time is inconsistent with master_tick")
        if (abs(actual_time - target_time) > event_tolerance or
                abs(legacy_time - actual_time) > event_tolerance):
            raise ValueError(f"{context}: actual/legacy time violates schedule tolerance")
        current.update({
            "master_tick": tick, "target_time": target_time,
            "actual_time": actual_time, "t": actual_time,
            "t_star": target_time / dh,
        })
        for field in (
            "cumulative_discharged_liquid_volume",
            "cumulative_nozzle_exit_net_volume",
        ):
            current[field] = finite_number(row.get(field), field, context)
            current[field + "_normalized"] = current[field] / nozzle_volume_scale
        if "cumulative_nozzle_exit_discharge" in row:
            if contract["runtime_contract"].get(
                "legacy_cumulative_nozzle_exit_discharge_alias"
            ) != "cumulative_nozzle_exit_net_volume":
                raise ValueError(
                    f"{context}: legacy cumulative discharge lacks explicit net-volume alias"
                )
            legacy_cumulative = finite_number(
                row.get("cumulative_nozzle_exit_discharge"),
                "cumulative_nozzle_exit_discharge", context,
            )
            if not math.isclose(
                legacy_cumulative, current["cumulative_nozzle_exit_net_volume"],
                rel_tol=5e-12, abs_tol=1e-14,
            ):
                raise ValueError(f"{context}: legacy cumulative alias is inconsistent")
        if current["J_k_liquid"] < 0.0 or current["liquid_area"] <= 0.0:
            raise ValueError(
                f"{context}: J_k must be nonnegative and liquid area positive"
            )
        if (current["beta"] < 0.0 or current["alpha"] < 0.0 or
                current["momentum_equivalent_velocity"] < 0.0):
            raise ValueError(f"{context}: profile factors/velocity must be nonnegative")
        if current["Q_l"] > 1e-14 and (current["beta"] <= 0.0 or current["alpha"] <= 0.0):
            raise ValueError(f"{context}: flowing-state beta and alpha must be positive")
        if previous is not None:
            if current["master_tick"] <= previous["master_tick"]:
                raise ValueError(f"{path}: duplicate/nonmonotone master tick")
            if current["actual_time"] <= previous["actual_time"]:
                raise ValueError(f"{path}: duplicate/nonmonotone actual time")
            if (current["cumulative_discharged_liquid_volume"] <
                    previous["cumulative_discharged_liquid_volume"] - 1e-12):
                raise ValueError(f"{path}: cumulative discharged liquid volume decreased")
            dt = current["actual_time"] - previous["actual_time"]
            expected_net_increment = 0.5 * (previous["Q_l"] + current["Q_l"]) * dt
            expected_discharged_increment = 0.5 * (
                max(previous["Q_l"], 0.0) + max(current["Q_l"], 0.0)
            ) * dt
            observed_net_increment = (
                current["cumulative_nozzle_exit_net_volume"] -
                previous["cumulative_nozzle_exit_net_volume"]
            )
            observed_discharged_increment = (
                current["cumulative_discharged_liquid_volume"] -
                previous["cumulative_discharged_liquid_volume"]
            )
            if not math.isclose(
                observed_net_increment, expected_net_increment,
                rel_tol=5e-8, abs_tol=1e-12,
            ):
                raise ValueError(f"{path}: signed net-discharge integration is inconsistent")
            if not math.isclose(
                observed_discharged_increment, expected_discharged_increment,
                rel_tol=5e-8, abs_tol=1e-12,
            ):
                raise ValueError(f"{path}: positive-discharge integration is inconsistent")
        output.append(current)
        previous = current
    if (output[0]["master_tick"] != 0 or abs(output[0]["t_star"]) > 1e-12 or
            abs(output[0]["cumulative_discharged_liquid_volume"]) > 1e-12 or
            abs(output[0]["cumulative_nozzle_exit_net_volume"]) > 1e-12):
        raise ValueError(f"{path}: comparison series must begin at the proven fresh t=0 state")
    return output, {
        "path": str(resolved), "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved), "rows": len(output),
        "starts_at_t_star": output[0]["t_star"],
        "ends_at_t_star": output[-1]["t_star"],
        "terminal_master_tick": output[-1]["master_tick"],
        "time_identity": "master_tick_with_target_and_actual_time_within_schedule_tolerance",
        "preferred_cumulative_coordinate": (
            "integral(max(Q_l,0),dt)/(A0*Dh)"
        ),
        "signed_net_coordinate": "integral(Q_l,dt)/(A0*Dh)",
    }


def theil_sen(x: list[float], y: list[float]) -> float:
    slopes = [(y[j] - y[i]) / (x[j] - x[i]) for i in range(len(x))
              for j in range(i + 1, len(x)) if x[j] != x[i]]
    if not slopes:
        raise ValueError("no finite slope pairs")
    return statistics.median(slopes)


def ordinary_slope_and_95_uncertainty(x: list[float], y: list[float]) -> tuple[float, float]:
    mean_x, mean_y = statistics.fmean(x), statistics.fmean(y)
    sum_xx = sum((value - mean_x) ** 2 for value in x)
    if sum_xx <= 0.0:
        raise ValueError("no ordinary-regression slope support")
    slope = sum((xv - mean_x) * (yv - mean_y) for xv, yv in zip(x, y)) / sum_xx
    if len(x) <= 2:
        return slope, math.inf
    intercept = mean_y - slope * mean_x
    residual = sum((yv - intercept - slope * xv) ** 2 for xv, yv in zip(x, y))
    return slope, 1.96 * math.sqrt(max(residual, 0.0) / (len(x) - 2) / sum_xx)


def trend_metrics(rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for name in CORE:
        x, y = [row["t_star"] for row in rows], [row[name] for row in rows]
        mean = statistics.fmean(y)
        robust = theil_sen(x, y)
        ordinary, uncertainty = ordinary_slope_and_95_uncertainty(x, y)
        denominator = max(abs(mean), 1e-30)
        relative, relative_u = 100.0 * robust / denominator, 100.0 * uncertainty / denominator
        metrics[name] = {
            "mean": mean, "robust_relative_slope_percent_per_t_star": relative,
            "ordinary_relative_slope_percent_per_t_star": 100.0 * ordinary / denominator,
            "relative_slope_95_uncertainty_percent_per_t_star": relative_u,
            "absolute_relative_slope_95_upper_percent_per_t_star": abs(relative) + relative_u,
            "end_to_end_drift_percent": 100.0 * (y[-1] - y[0]) / denominator,
            "monotonic_fraction": max(
                sum(right > left for left, right in zip(y, y[1:])),
                sum(right < left for left, right in zip(y, y[1:])),
            ) / max(1, len(y) - 1),
        }
        intercept = statistics.fmean(y) - ordinary*statistics.fmean(x)
        residuals = [yv - (intercept + ordinary*xv) for xv, yv in zip(x, y)]
        fluctuation = 1.4826 * statistics.median(
            abs(value - statistics.median(residuals)) for value in residuals
        )
        metrics[name]["robust_residual_fluctuation"] = fluctuation
        metrics[name]["unresolved_monotonic_trend"] = bool(
            metrics[name]["monotonic_fraction"] >= 0.8 and
            abs(y[-1] - y[0]) > max(2.0*fluctuation, 1e-12*denominator)
        )
    return metrics


def window_trends(rows: list[dict[str, float]], width: float = 2.0) -> dict[str, object]:
    end = rows[-1]["t_star"]
    selected = [row for row in rows if row["t_star"] >= end - width - 1e-12]
    if len(selected) < 3 or selected[0]["t_star"] > end - width + 0.1 * width:
        return {"classification": "INSUFFICIENT", "metrics": {}}
    metrics = trend_metrics(selected)
    quasi = all(
        value["absolute_relative_slope_95_upper_percent_per_t_star"] <= 0.5
        and abs(value["end_to_end_drift_percent"]) <= 1.0
        and not value["unresolved_monotonic_trend"]
        for value in metrics.values()
    )
    classification = "OPERATIONAL_QUASI_STEADY" if quasi else "TRANSIENT"
    if not quasi:
        previous = [row for row in rows
                    if end - 2.0 * width - 1e-12 <= row["t_star"] <= end - width + 1e-12]
        if (len(previous) >= 3 and
                previous[0]["t_star"] <= end - 2.0 * width + 0.1 * width):
            previous_metrics = trend_metrics(previous)
            approaching = True
            for name, current in metrics.items():
                prior = previous_metrics[name]
                prior_lower = max(
                    0.0,
                    abs(prior["robust_relative_slope_percent_per_t_star"])
                    - prior["relative_slope_95_uncertainty_percent_per_t_star"],
                )
                if (current["absolute_relative_slope_95_upper_percent_per_t_star"] > 2.0 or
                        current["absolute_relative_slope_95_upper_percent_per_t_star"] >
                        0.5 * prior_lower):
                    approaching = False
            if approaching:
                classification = "APPROACHING_QUASI_STEADY"
    return {
        "classification": classification, "window_t_star": width,
        "start_t_star": selected[0]["t_star"], "end_t_star": end,
        "uncertainty_method": "ordinary_slope_95_percent_normal_approximation_around_theil_sen",
        "metrics": metrics,
    }


def time_to_stationarity(rows: list[dict[str, float]], width: float = 2.0) -> dict[str, object]:
    evaluations: list[tuple[float, str]] = []
    for index in range(2, len(rows)):
        if rows[index]["t_star"] - rows[0]["t_star"] + 1e-12 < width:
            continue
        trend = window_trends(rows[:index + 1], width)
        if trend["classification"] != "INSUFFICIENT":
            evaluations.append((rows[index]["t_star"], str(trend["classification"])))
    passing = [time for time, state in evaluations if state == "OPERATIONAL_QUASI_STEADY"]
    sustained_from = None
    for index, (candidate, state) in enumerate(evaluations):
        remaining = evaluations[index:]
        dwell = rows[-1]["t_star"] - candidate
        if (state == "OPERATIONAL_QUASI_STEADY" and
                dwell + 1e-12 >= MINIMUM_STATIONARITY_DWELL_T_STAR and
                all(other == "OPERATIONAL_QUASI_STEADY" for _, other in remaining)):
            sustained_from = candidate
            break
    return {
        "status": (
            "reached_and_sustained" if sustained_from is not None
            else "right_censored_unresolved"
        ),
        "window_t_star": width,
        "minimum_sustained_dwell_t_star": MINIMUM_STATIONARITY_DWELL_T_STAR,
        "evaluated_window_count": len(evaluations),
        "first_observed_pass_t_star": passing[0] if passing else None,
        "sustained_from_t_star": sustained_from,
        "observed_through_t_star": rows[-1]["t_star"],
        "censoring_disposition": (
            "resolved_sustained_dwell" if sustained_from is not None
            else "right_censored_stationarity_unresolved"
        ),
    }


def interpolation_candidates(
    rows: list[dict[str, float]], coordinate: str, target: float
) -> list[dict[str, object]]:
    exact = [(index, row) for index, row in enumerate(rows)
             if math.isclose(row[coordinate], target, rel_tol=1e-12, abs_tol=1e-14)]
    candidates: list[dict[str, object]] = [
        {"kind": "exact_sample", "left_index": index, "right_index": index,
         "left_coordinate": row[coordinate], "right_coordinate": row[coordinate],
         "left_t_star": row["t_star"], "right_t_star": row["t_star"],
         "left_master_tick": row.get("master_tick"),
         "right_master_tick": row.get("master_tick"), "fraction": 0.0,
         "values": {field: row[field] for field in INTERPOLATED_FIELDS}}
        for index, row in exact
    ]
    for index, (left, right) in enumerate(zip(rows, rows[1:])):
        lo, hi = left[coordinate], right[coordinate]
        if min(lo, hi) < target < max(lo, hi) and hi != lo:
            fraction = (target - lo) / (hi - lo)
            candidates.append({
                "kind": "linear_interpolation", "left_index": index,
                "right_index": index + 1, "left_coordinate": lo, "right_coordinate": hi,
                "left_t_star": left["t_star"], "right_t_star": right["t_star"],
                "left_master_tick": left.get("master_tick"),
                "right_master_tick": right.get("master_tick"),
                "fraction": fraction,
                "values": {field: left[field] + fraction * (right[field] - left[field])
                           for field in INTERPOLATED_FIELDS},
            })
    return candidates


def interpolate(rows: list[dict[str, float]], coordinate: str, target: float,
                fields: tuple[str, ...] = CORE) -> dict[str, float] | None:
    """Compatibility helper: return only an unambiguous bracketed match."""
    candidates = interpolation_candidates(rows, coordinate, target)
    if len(candidates) != 1:
        return None
    values = candidates[0]["values"]
    assert isinstance(values, dict)
    return {field: float(values[field]) for field in fields}


def matched_state(series: dict[str, list[dict[str, float]]], coordinate: str) -> dict[str, object]:
    overlap = [max(min(row[coordinate] for row in rows) for rows in series.values()),
               min(max(row[coordinate] for row in rows) for rows in series.values())]
    if overlap[0] > overlap[1] and not math.isclose(overlap[0], overlap[1],
                                                    rel_tol=1e-12, abs_tol=1e-14):
        return {"status": "no_common_bracket", "common_overlap": overlap}
    target = 0.5 * (overlap[0] + overlap[1])
    cases: dict[str, object] = {}
    unique = True
    for role, rows in series.items():
        candidates = interpolation_candidates(rows, coordinate, target)
        cases[role] = {"candidate_count": len(candidates), "candidates": candidates}
        unique &= len(candidates) == 1
    result = {
        "status": "matched_unique" if unique else "ambiguous_bracket",
        "common_overlap": overlap,
        "target_policy": "midpoint_of_three_case_common_observed_range",
        "target": target, "cases": cases,
    }
    if not unique:
        result["ambiguity"] = (
            "zero_or_multiple_observed_roots; exact hits and every strict crossing "
            "are preserved and no root is selected"
        )
    if unique:
        values = {
            role: cases[role]["candidates"][0]["values"] for role in "ABC"
        }
        comparisons: dict[str, object] = {}
        for label, left_role, right_role in (
            ("B_minus_A", "A", "B"),
            ("C_minus_A", "A", "C"),
            ("C_minus_B", "B", "C"),
        ):
            comparisons[label] = {}
            for field in METRICS:
                left = float(values[left_role][field])
                difference = float(values[right_role][field]) - left
                comparisons[label][field] = {
                    "difference": difference,
                    "relative_difference_percent": (
                        None if abs(left) <= 1e-30 else 100.0 * difference / abs(left)
                    ),
                }
        result["pairwise_differences"] = comparisons
    return result


def slope_reduction_interval(a: dict[str, float], b: dict[str, float]) -> dict[str, float | None]:
    av, bv = abs(a["robust_relative_slope_percent_per_t_star"]), abs(b["robust_relative_slope_percent_per_t_star"])
    au, bu = a["relative_slope_95_uncertainty_percent_per_t_star"], b["relative_slope_95_uncertainty_percent_per_t_star"]
    al, ah, bl, bh = max(0.0, av - au), av + au, max(0.0, bv - bu), bv + bu
    return {
        "point_reduction_fraction": None if av <= 1e-30 else 1.0 - bv / av,
        "conservative_95_reduction_fraction": None if al <= 1e-30 else 1.0 - bh / al,
        "optimistic_95_reduction_fraction": None if ah <= 1e-30 else 1.0 - bl / ah,
        "a_absolute_slope_95_lower": al, "a_absolute_slope_95_upper": ah,
        "b_absolute_slope_95_lower": bl, "b_absolute_slope_95_upper": bh,
    }


def classify(trends: dict[str, dict[str, object]],
             stationarity_times: dict[str, dict[str, object]], *,
             equivalence_predeclared: bool = False) -> tuple[str, dict[str, object]]:
    if any(trends[role]["classification"] == "INSUFFICIENT" for role in "ABC"):
        return "MIXED_OR_UNRESOLVED", {}
    c_time = stationarity_times["C"]["sustained_from_t_star"]
    b_time = stationarity_times["B"]["sustained_from_t_star"]
    if c_time is not None and b_time is None:
        return "FLOW_CONTROL_ONLY_STABILIZES", {}
    a_time = stationarity_times["A"]["sustained_from_t_star"]
    if b_time is not None and (a_time is None or float(b_time) <= float(a_time) - 2.0):
        return "PRECURSOR_RESOLVES_STARTUP_TRANSIENT", {
            "substantially_earlier_definition_t_star": 2.0,
            "case_a_sustained_from_t_star": a_time,
            "case_b_sustained_from_t_star": b_time,
        }
    reductions: dict[str, object] = {}
    for name in ("Q_l", "J_k_liquid"):
        am, bm = trends["A"]["metrics"], trends["B"]["metrics"]
        assert isinstance(am, dict) and isinstance(bm, dict)
        reductions[name] = slope_reduction_interval(am[name], bm[name])
    intervals = list(reductions.values())
    conservative = [item["conservative_95_reduction_fraction"] for item in intervals]
    if all(value is not None and value >= 0.5 for value in conservative):
        return "PRECURSOR_MATERIALLY_REDUCES_TRANSIENT", reductions
    indistinguishable = all(
        item["a_absolute_slope_95_lower"] <= item["b_absolute_slope_95_upper"] and
        item["b_absolute_slope_95_lower"] <= item["a_absolute_slope_95_upper"]
        for item in intervals
    )
    if indistinguishable:
        if equivalence_predeclared:
            reductions["equivalence_basis"] = "predeclared_equivalence_rule"
            return "PRECURSOR_HAS_NO_MATERIAL_EFFECT", reductions
        reductions["equivalence_basis"] = (
            "none; overlapping confidence intervals do not establish equivalence"
        )
        return "MIXED_OR_UNRESOLVED", reductions
    if all(value is not None and value > 0.0 for value in conservative):
        return "PRECURSOR_HAS_LIMITED_EFFECT", reductions
    return "MIXED_OR_UNRESOLVED", reductions


def common_horizon(
    series: dict[str, list[dict[str, float]]]
) -> tuple[dict[str, list[dict[str, float]]], int, float, dict[str, object]]:
    """Fail closed unless all cases share an exact canonical terminal tick."""
    terminal_ticks = {role: int(rows[-1]["master_tick"]) for role, rows in series.items()}
    common_tick = min(terminal_ticks.values())
    truncated: dict[str, list[dict[str, float]]] = {}
    dispositions: dict[str, object] = {}
    common_time: float | None = None
    for role, rows in series.items():
        retained = [row for row in rows if int(row["master_tick"]) <= common_tick]
        exact = [row for row in retained if int(row["master_tick"]) == common_tick]
        if len(exact) != 1:
            raise ValueError(
                f"Case {role}: no unique exact sample at common master tick {common_tick}"
            )
        if retained[-1] is not exact[0]:
            raise ValueError(f"Case {role}: common-tick truncation is not deterministic")
        candidate_time = float(exact[0]["t_star"])
        if common_time is None:
            common_time = candidate_time
        elif not math.isclose(candidate_time, common_time, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("common master tick maps to inconsistent t_star values")
        truncated[role] = retained
        dispositions[role] = {
            "original_terminal_master_tick": terminal_ticks[role],
            "used_terminal_master_tick": common_tick,
            "original_row_count": len(rows),
            "used_row_count": len(retained),
            "right_truncated_to_common_horizon": terminal_ticks[role] > common_tick,
        }
    assert common_time is not None
    return truncated, common_tick, common_time, dispositions


def compare(paths: dict[str, Path], package_paths: dict[str, Path], dh: float) -> dict[str, object]:
    if set(paths) != set(CASE_MODES) or set(package_paths) != set(CASE_MODES):
        raise ValueError("metric and package paths must contain exactly A, B, and C")
    if not math.isfinite(dh) or dh <= 0.0:
        raise ValueError("dh must be positive and finite")
    contracts = {role: read_package(package_paths[role], role) for role in "ABC"}
    compatibility = compatible_contracts(contracts, dh)
    loaded = {role: load(paths[role], dh, role, contracts[role]) for role in "ABC"}
    full_series = {role: loaded[role][0] for role in "ABC"}
    metric_provenance = {role: loaded[role][1] for role in "ABC"}
    series, common_tick, common_end, horizon_disposition = common_horizon(full_series)
    trends = {role: window_trends(series[role]) for role in "ABC"}
    stationarity_times = {role: time_to_stationarity(series[role]) for role in "ABC"}
    effect, reductions = classify(trends, stationarity_times)
    equal_time = {
        role: {field: rows[-1][field] for field in INTERPOLATED_FIELDS}
        for role, rows in series.items()
    }
    matched = {coordinate: matched_state(series, coordinate) for coordinate in (
        "cumulative_discharged_liquid_volume_normalized",
        "cumulative_nozzle_exit_net_volume_normalized", "Q_l",
        "J_k_liquid", "J_total")}
    return {
        "schema": "steady_precursor_matched_comparison_v2",
        "interpolation": "linear_within_observed_brackets_only_no_extrapolation",
        "contract_compatibility": compatibility,
        "metric_file_provenance": metric_provenance,
        "precursor_effect_candidate": effect,
        "precursor_effect_confirmation_required": (
            "parent_must_confirm_pressure_profile_support_and_exclude_diagnostic_artifact"
        ),
        "slope_reduction_uncertainty": reductions, "stationarity": trends,
        "time_to_stationarity": stationarity_times,
        "common_horizon": {
            "master_tick": common_tick, "t_star": common_end,
            "policy": "truncate_every_case_before_all_trends_and_matches",
            "case_disposition": horizon_disposition,
        },
        "last_common_t_star": common_end,
        "equal_t_star_metrics": equal_time, "matched_states": matched,
        "cumulative_coordinate_policy": {
            "preferred_matching_coordinate": (
                "cumulative_discharged_liquid_volume_normalized="
                "integral(max(Q_l,0),dt)/(A0*Dh)"
            ),
            "reported_net_coordinate": (
                "cumulative_nozzle_exit_net_volume_normalized="
                "integral(Q_l,dt)/(A0*Dh)"
            ),
            "root_policy": "enumerate_all_exact_hits_and_strict_crossings_fail_ambiguous",
        },
        "equivalence_policy": (
            "confidence_interval_overlap_is_not_equivalence_without_a_predeclared_rule"
        ),
        "claim_boundary": (
            "deterministic comparison candidate only; final causal classification "
            "requires authoritative pressure/profile and uncertainty review"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for role in "abc":
        parser.add_argument(f"--case-{role}", type=Path, required=True)
        parser.add_argument(f"--case-{role}-package", type=Path, required=True)
    parser.add_argument("--dh", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = compare(
        {role: getattr(args, f"case_{role.lower()}") for role in "ABC"},
        {role: getattr(args, f"case_{role.lower()}_package") for role in "ABC"},
        args.dh,
    )
    if args.output.exists() or args.output.is_symlink():
        parser.error("output path must not already exist")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        parser.error("temporary output path must not already exist")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, args.output)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
