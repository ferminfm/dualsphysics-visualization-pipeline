#!/usr/bin/env python3
"""Build and execute one hash-bound, observably supervised precursor start."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence


TRANSFER_SCHEMA = "internal_nozzle_exact_target_transfer_v1"
LAUNCH_SCHEMA = "internal_nozzle_bound_launch_v2"
SCHEDULE_SCHEMA = "internal_nozzle_launch_schedule_v1"
TRANSFER_METHOD = "exact_target_leaf_join_of_precursor_interpolated_samples"
TARGET_SAMPLING_METHOD = (
    "basilisk_interpolate_at_target_leaf_center_or_strict_outlet_"
    "straddle_internal_limit_v2"
)
TARGET_CLAMP_RULE = (
    "clamp_only_when_target_leaf_strictly_straddles_geometric_outlet"
)
PROTECTED_SOLVER_OPTIONS = {
    "--case-role",
    "--execution-id",
    "--segment-id",
    "--solver-sha256",
    "--build-variant",
    "--initial-state",
    "--precursor-transfer",
    "--precursor-transfer-sha256",
    "--precursor-pressure-mode",
    "--restore",
    "--auto-restore",
    "--restore-source-sha",
    "--source-commit",
    "--source-sha",
    "--schedule-version",
    "--schedule-sha",
    "--schedule-tick-dt",
    "--schedule-tolerance",
    "--light-base-stride",
    "--light-dense-stride",
    "--field-base-stride",
    "--field-dense-stride",
    "--checkpoint-stride",
    "--dense-start-tick",
    "--dense-end-tick",
    "--profile-bulk-velocity",
    "--precursor-convergence-sha256",
    "--precursor-history-sha256",
    "--precursor-target-q",
    "--precursor-target-area",
    "--precursor-target-velocity-tolerance",
    "--restore-sha256",
    "--restore-metadata-sha256",
    "--restore-closure-sha256",
    "--predecessor-segment-id",
}

ROLE_CONTRACTS = {
    "A": {
        "initial_state": "rest",
        "inlet_mode": "pressure_driven",
        "build_variant": "pressure_driven",
        "precursor_pressure_mode": "not_applicable",
    },
    "B": {
        "initial_state": "precursor",
        "inlet_mode": "pressure_driven",
        "build_variant": "pressure_driven",
        "precursor_pressure_mode": "transferred",
    },
    "C": {
        "initial_state": "precursor",
        "inlet_mode": "poiseuille_profile_controlled_diagnostic",
        "build_variant": "profile_controlled",
        "precursor_pressure_mode": "transferred",
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


def load_source_bundle(
    path: Path, expected_sha256: str, expected_commit: str,
) -> tuple[Path, dict[str, object]]:
    resolved, payload = load_object(path, "source-bundle manifest")
    if sha256(resolved) != expected_sha256:
        raise ValueError("source-bundle manifest SHA-256 mismatch")
    expected_keys = {
        "schema", "scientific_commit", "repository_root_name",
        "tracked_behavior_files", "tracked_behavior_file_count",
        "prepared_centered", "basilisk", "source_identity_semantics",
    }
    exact_keys(payload, expected_keys, "source-bundle manifest")
    if (payload.get("schema") != "internal_nozzle_source_bundle_v1" or
            payload.get("scientific_commit") != expected_commit or
            payload.get("source_identity_semantics") !=
            "sha256_of_this_complete_manifest_file"):
        raise ValueError("source-bundle manifest identity/semantics mismatch")
    rows = payload.get("tracked_behavior_files")
    if (not isinstance(rows, list) or not rows or
            payload.get("tracked_behavior_file_count") != len(rows)):
        raise ValueError("source-bundle tracked-file inventory is malformed")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "path", "git_blob", "git_mode", "size_bytes", "sha256",
        }:
            raise ValueError("source-bundle tracked-file record is malformed")
        relative = row.get("path")
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute() or
                ".." in Path(relative).parts or relative in seen):
            raise ValueError("source-bundle tracked path is invalid")
        seen.add(relative)
        canonical_hex(str(row.get("git_blob")), 40, "source-bundle Git blob")
        canonical_hex(str(row.get("sha256")), 64, "source-bundle file SHA-256")
        if row.get("git_mode") not in {"100644", "100755"}:
            raise ValueError("source-bundle tracked mode is invalid")
    required_paths = {
        "cases/basilisk/rectangular_internal_nozzle_steady_precursor.c",
        "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c",
        "cases/basilisk/internal_nozzle_precursor_start.h",
        "scripts/rectangular_poiseuille_reference.py",
        "scripts/evaluate_internal_nozzle_acceptance.py",
    }
    if not required_paths.issubset(seen):
        raise ValueError("source-bundle lacks required launch behavior files")
    return resolved, payload


def load_build_manifest(
    path: Path, expected_sha256: str, source_bundle: Path,
    source_bundle_sha256: str, source_commit: str, solver: Path,
    solver_sha256: str, expected_role: str,
) -> tuple[Path, dict[str, object]]:
    resolved, payload = load_object(path, "observable qcc build manifest")
    if sha256(resolved) != expected_sha256:
        raise ValueError("observable qcc build manifest SHA-256 mismatch")
    exact_keys(payload, {
        "schema", "scientific_commit", "source_bundle_path",
        "source_bundle_sha256", "build_role", "entry_source",
        "required_defines", "compile_identity_semantics", "compile_run_id",
        "compile_argv", "compile_terminal", "binary", "verified_input_count",
    }, "observable qcc build manifest")
    role_contracts = {
        "precursor": (
            "cases/basilisk/rectangular_internal_nozzle_steady_precursor.c",
            ["INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1"],
        ),
        "pressure_driven": (
            "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c",
            ["INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1"],
        ),
        "profile_controlled": (
            "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c",
            ["INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1",
             "INTERNAL_NOZZLE_PROFILE_CONTROLLED=1"],
        ),
    }
    expected_entry, expected_defines = role_contracts[expected_role]
    binary = payload.get("binary")
    terminal = payload.get("compile_terminal")
    if (payload.get("schema") != "internal_nozzle_observable_qcc_build_v1" or
            payload.get("scientific_commit") != source_commit or
            payload.get("source_bundle_path") != str(source_bundle) or
            payload.get("source_bundle_sha256") != source_bundle_sha256 or
            payload.get("build_role") != expected_role or
            payload.get("entry_source") != expected_entry or
            payload.get("required_defines") != expected_defines or
            payload.get("compile_identity_semantics") !=
            "observable_qcc_exact_entry_source_role_defines_and_immutable_inputs" or
            not isinstance(binary, dict) or set(binary) != {"path", "size_bytes", "sha256"} or
            binary.get("path") != str(solver) or binary.get("sha256") != solver_sha256 or
            binary.get("size_bytes") != solver.stat().st_size or
            not isinstance(terminal, dict) or set(terminal) != {
                "path", "sha256", "exit_code", "terminal_state",
            } or terminal.get("exit_code") != 0 or
            terminal.get("terminal_state") != "normal_exit"):
        raise ValueError("observable qcc build identity/role mismatch")
    canonical_identifier(str(payload.get("compile_run_id")), "qcc compile run ID")
    canonical_hex(str(terminal.get("sha256")), 64, "qcc terminal SHA-256")
    argv = payload.get("compile_argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise ValueError("observable qcc build argv is malformed")
    return resolved, payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"{label} must be a nonempty regular file")
    return resolved


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_object(path: Path, label: str) -> tuple[Path, dict[str, object]]:
    try:
        resolved = regular(path, label)
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    try:
        value = json.loads(
            resolved.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label} JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return resolved, value


def load_manifest(path: Path) -> tuple[Path, dict[str, object]]:
    resolved, value = load_object(path, "transfer manifest")
    if value.get("schema") != TRANSFER_SCHEMA:
        raise ValueError("incompatible transfer manifest schema")
    return resolved, value


def canonical_hex(value: str, length: int, label: str) -> str:
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"{label} must be {length} lowercase hexadecimal characters")
    return value


def canonical_identifier(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError(
            f"{label} must be 1-128 letters, digits, dot, underscore or hyphen"
        )
    return value


def exact_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def finite_number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "positive finite" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}")
    return result


def exact_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ValueError(f"{label} keys mismatch: missing={missing} extra={extra}")


def load_schedule(path: Path, expected_version: str) -> tuple[Path, dict[str, object]]:
    resolved, value = load_object(path, "launch schedule")
    exact_keys(value, {
        "schema", "schedule_version", "master_tick_dt", "event_time_tolerance",
        "lightweight", "full_field", "checkpoint_stride", "dense_window",
    }, "launch schedule")
    if value.get("schema") != SCHEDULE_SCHEMA:
        raise ValueError("incompatible launch schedule schema")
    if value.get("schedule_version") != expected_version:
        raise ValueError("launch schedule version mismatch")
    canonical_identifier(expected_version, "schedule version")
    lightweight = value.get("lightweight")
    full_field = value.get("full_field")
    dense_window = value.get("dense_window")
    if not isinstance(lightweight, dict) or not isinstance(full_field, dict):
        raise ValueError("launch schedule cadence groups must be objects")
    if not isinstance(dense_window, dict):
        raise ValueError("launch schedule dense_window must be an object")
    exact_keys(lightweight, {"base_stride", "dense_stride"}, "launch schedule lightweight")
    exact_keys(full_field, {"base_stride", "dense_stride"}, "launch schedule full_field")
    exact_keys(dense_window, {"start_tick", "end_tick"}, "launch schedule dense_window")
    normalized = {
        "schema": SCHEDULE_SCHEMA,
        "schedule_version": expected_version,
        "master_tick_dt": finite_number(
            value.get("master_tick_dt"), "schedule master_tick_dt", positive=True,
        ),
        "event_time_tolerance": finite_number(
            value.get("event_time_tolerance"), "schedule event_time_tolerance",
            positive=True,
        ),
        "lightweight": {
            key: exact_int(lightweight.get(key), f"schedule lightweight.{key}")
            for key in ("base_stride", "dense_stride")
        },
        "full_field": {
            key: exact_int(full_field.get(key), f"schedule full_field.{key}")
            for key in ("base_stride", "dense_stride")
        },
        "checkpoint_stride": exact_int(
            value.get("checkpoint_stride"), "schedule checkpoint_stride",
        ),
        "dense_window": {
            key: exact_int(dense_window.get(key), f"schedule dense_window.{key}")
            for key in ("start_tick", "end_tick")
        },
    }
    strides = [
        *normalized["lightweight"].values(), *normalized["full_field"].values(),
        normalized["checkpoint_stride"],
    ]
    if any(value <= 0 for value in strides):
        raise ValueError("schedule strides must be positive integers")
    if (normalized["dense_window"]["start_tick"] < 0 or
            normalized["dense_window"]["end_tick"] <
            normalized["dense_window"]["start_tick"]):
        raise ValueError("schedule dense window is invalid")
    return resolved, normalized


PRECURSOR_HISTORY_FIELDS = (
    "case_id", "t", "t_star", "i", "Q_l", "mdot_l", "J_k",
    "pressure_drop", "exit_area", "U_bulk", "beta", "alpha",
    "inlet_boundary_face_flow", "outlet_boundary_face_flow",
    "mass_flow_imbalance", "profile_l2_change", "max_ux_change",
    "mgp_iterations", "mgu_iterations", "mgp_residual", "mgu_residual",
    "cell_count", "restart_state",
)


def load_convergence_bulk_target(
    path: Path, expected_sha256: str, manifest: dict[str, object],
) -> tuple[Path, Path, dict[str, object]]:
    """Derive U=Q/A from the terminal row already accepted as converged."""
    resolved, report = load_object(path, "precursor convergence report")
    if sha256(resolved) != expected_sha256:
        raise ValueError("precursor convergence report SHA-256 mismatch")
    if expected_sha256 != manifest.get("precursor_convergence_report_sha256"):
        raise ValueError("transfer manifest/convergence report SHA-256 mismatch")
    exact_keys(report, {
        "schema", "classification", "pass", "case_id", "inputs",
        "combined_unique_sample_count", "window", "fixed_scientific_thresholds",
        "declared_operational_bounds", "metrics", "auxiliary", "failures",
        "claim_boundary",
    }, "precursor convergence report")
    if (
        report.get("schema") != "internal_nozzle_precursor_convergence_v1"
        or report.get("classification") != "precursor_converged"
        or report.get("pass") is not True
    ):
        raise ValueError("precursor convergence report is not passing")
    inputs = report.get("inputs")
    if not isinstance(inputs, list) or not inputs or not isinstance(inputs[-1], dict):
        raise ValueError("precursor convergence report has no terminal segment")
    history_record = inputs[-1].get("history")
    if not isinstance(history_record, dict):
        raise ValueError("precursor convergence report has no terminal history")
    exact_keys(history_record, {"resolved_path", "sha256", "size_bytes"},
               "precursor terminal history record")
    history_sha = canonical_hex(
        str(history_record.get("sha256")), 64, "precursor terminal history SHA-256",
    )
    if history_sha != manifest.get("final_history_sha256"):
        raise ValueError("transfer manifest/terminal history SHA-256 mismatch")
    history = regular(Path(str(history_record.get("resolved_path"))),
                      "precursor terminal history")
    if sha256(history) != history_sha or history.stat().st_size != history_record.get("size_bytes"):
        raise ValueError("precursor terminal history identity mismatch")
    with history.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != PRECURSOR_HISTORY_FIELDS:
            raise ValueError("precursor terminal history has an incompatible header")
        rows = list(reader)
    if not rows or any(None in row or any(item is None for item in row.values()) for row in rows):
        raise ValueError("precursor terminal history is empty or malformed")
    terminal = rows[-1]
    if terminal["case_id"] != report.get("case_id"):
        raise ValueError("precursor terminal history case identity mismatch")
    try:
        terminal_t_star = float(terminal["t_star"])
        flow = float(terminal["Q_l"])
        area = float(terminal["exit_area"])
        bulk = float(terminal["U_bulk"])
    except (TypeError, ValueError) as error:
        raise ValueError("precursor terminal history has invalid numeric data") from error
    if (not all(math.isfinite(value) for value in (terminal_t_star, flow, area, bulk))
            or flow <= 0.0 or area <= 0.0 or bulk <= 0.0):
        raise ValueError("precursor terminal history has invalid numeric data")
    window = report.get("window")
    if not isinstance(window, dict):
        raise ValueError("precursor convergence report window is malformed")
    end_t_star = finite_number(window.get("end_t_star"), "convergence end_t_star")
    if not math.isclose(terminal_t_star, end_t_star, rel_tol=0.0, abs_tol=1e-14):
        raise ValueError("precursor terminal history is not the convergence endpoint")
    derived = flow / area
    tolerance = max(1e-14, 1e-12 * abs(derived))
    if not math.isclose(bulk, derived, rel_tol=0.0, abs_tol=tolerance):
        raise ValueError("precursor terminal U_bulk is inconsistent with Q_l/exit_area")
    return resolved, history, {
        "derivation": "terminal_converged_precursor_exit_Q_l_over_liquid_area",
        "conservation_equivalence": (
            "passing precursor mass-flow-imbalance bound makes the straight-duct "
            "exit flow conservation-equivalent to its upstream plane"
        ),
        "precursor_case_id": report["case_id"],
        "convergence_report_sha256": expected_sha256,
        "history_sha256": history_sha,
        "terminal_t_star": terminal_t_star,
        "terminal_Q_l": flow,
        "terminal_liquid_area": area,
        "reported_bulk_velocity": bulk,
        "bulk_velocity": derived,
        "absolute_consistency_tolerance": tolerance,
    }


def validate_manifest_semantics(manifest: dict[str, object]) -> str:
    expected = {
        "method": TRANSFER_METHOD,
        "source_field_sampling": TARGET_SAMPLING_METHOD,
        "target_exit_clamp_rule": TARGET_CLAMP_RULE,
        "additional_interpolation_by_preparer": False,
        "precursor_convergence_classification": "precursor_converged",
    }
    for key, value in expected.items():
        observed = manifest.get(key)
        if observed != value or (isinstance(value, bool) and observed is not value):
            raise ValueError(f"transfer manifest semantic mismatch: {key}")
    target_count = exact_int(manifest.get("target_leaf_count"), "target_leaf_count")
    loaded_count = exact_int(manifest.get("loaded_leaf_count"), "loaded_leaf_count")
    unused_count = exact_int(manifest.get("unused_source_rows"), "unused_source_rows")
    clamp_count = exact_int(
        manifest.get("target_exit_clamp_count"), "target_exit_clamp_count",
    )
    coverage = manifest.get("coverage_fraction")
    if (
        target_count <= 0 or loaded_count != target_count or unused_count != 0
        or clamp_count < 0 or clamp_count > target_count
        or isinstance(coverage, bool) or not isinstance(coverage, (int, float))
        or float(coverage) != 1.0
    ):
        raise ValueError("transfer manifest does not prove exact complete target coverage")
    hash_fields = (
        "source_sha256", "producer_unsealed_metadata_sha256",
        "precursor_checkpoint_sha256", "precursor_checkpoint_sidecar_sha256",
        "precursor_checkpoint_closure_sha256",
        "precursor_convergence_report_sha256", "final_history_sha256",
        "final_run_contract_sha256", "source_table_sha256",
        "target_template_sha256", "transfer_table_sha256",
    )
    for field in hash_fields:
        canonical_hex(str(manifest.get(field)), 64, f"transfer manifest {field}")
    return str(manifest["source_sha256"])


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite launch contract: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"temporary launch contract already exists: {temporary}")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def required_solver_option(argv: list[str], name: str) -> str:
    positions = [index for index, value in enumerate(argv) if value == name]
    if len(positions) != 1:
        raise ValueError(f"solver argv must contain exactly one {name}")
    position = positions[0]
    if position + 1 >= len(argv) or argv[position + 1].startswith("--"):
        raise ValueError(f"solver argv has no value for {name}")
    return argv[position + 1]


def build_contract(args: argparse.Namespace) -> dict[str, object]:
    execution_id = canonical_identifier(args.execution_id, "execution ID")
    segment_id = canonical_identifier(args.segment_id, "segment ID")
    if args.run_id is not None and args.run_id != segment_id:
        raise ValueError("run ID must equal segment ID")
    role = ROLE_CONTRACTS[args.case_role]
    cwd = args.cwd.resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("solver cwd is not a directory")

    supervisor = regular(args.supervisor, "process supervisor")
    supervisor_sha = canonical_hex(
        args.supervisor_sha256, 64, "supervisor SHA-256",
    )
    if sha256(supervisor) != supervisor_sha:
        raise ValueError("supervisor SHA-256 mismatch")
    source_commit = canonical_hex(args.source_commit, 40, "source commit")
    source_sha = canonical_hex(args.source_sha256, 64, "source SHA-256")
    source_bundle_sha = canonical_hex(
        args.source_bundle_manifest_sha256, 64, "source-bundle manifest SHA-256",
    )
    source_bundle, _ = load_source_bundle(
        args.source_bundle_manifest, source_bundle_sha, source_commit,
    )
    if source_sha != source_bundle_sha:
        raise ValueError("source identity must equal the source-bundle manifest SHA-256")
    schedule_path, schedule = load_schedule(args.schedule, args.schedule_version)
    schedule_sha = canonical_hex(args.schedule_sha256, 64, "schedule SHA-256")
    if sha256(schedule_path) != schedule_sha:
        raise ValueError("schedule SHA-256 mismatch")

    requested_solver = list(args.solver_argv)
    if requested_solver[:1] == ["--"]:
        requested_solver = requested_solver[1:]
    if not requested_solver:
        raise ValueError("solver argv is empty")
    solver = regular(
        Path(requested_solver[0]) if Path(requested_solver[0]).is_absolute()
        else cwd / requested_solver[0],
        "solver executable",
    )
    if not os.access(solver, os.X_OK):
        raise ValueError("solver executable is not executable")
    solver_sha = canonical_hex(args.solver_sha256, 64, "solver executable SHA-256")
    if sha256(solver) != solver_sha:
        raise ValueError("solver executable SHA-256 mismatch")
    build_manifest_sha = canonical_hex(
        args.build_manifest_sha256, 64, "observable qcc build manifest SHA-256",
    )
    build_manifest, build_record = load_build_manifest(
        args.build_manifest, build_manifest_sha, source_bundle, source_bundle_sha,
        source_commit, solver, solver_sha, str(role["build_variant"]),
    )
    for token in requested_solver[1:]:
        name = token.split("=", 1)[0]
        if name in PROTECTED_SOLVER_OPTIONS:
            raise ValueError(f"solver argv predefines protected option: {name}")
    case_id = canonical_identifier(
        required_solver_option(requested_solver, "--case-id"), "case ID",
    )
    if required_solver_option(requested_solver, "--domain") != "full":
        raise ValueError("canonical A/B/C launch requires --domain full")
    output_value = required_solver_option(requested_solver, "--output-dir")
    solver_output = (
        Path(output_value) if Path(output_value).is_absolute() else cwd / output_value
    ).resolve()
    if output_value != str(solver_output):
        raise ValueError("solver --output-dir must be its canonical absolute path")
    if cwd != solver_output:
        raise ValueError("solver cwd must equal the canonical output directory")
    if schedule_path != solver_output / "run_schedule_contract.json":
        raise ValueError(
            "schedule input must be OUTPUT_DIR/run_schedule_contract.json"
        )
    if solver_output.exists() and solver_output.is_symlink():
        raise ValueError("solver output directory must not be a symlink")
    evidence_dir = args.evidence_dir.resolve()
    expected_evidence = solver_output / "supervision" / segment_id
    if evidence_dir != expected_evidence:
        raise ValueError(
            "evidence directory must be OUTPUT_DIR/supervision/SEGMENT_ID"
        )
    output_path = args.output.resolve()
    expected_output = solver_output / f"scientific_launch_contract.{segment_id}.json"
    if output_path != expected_output:
        raise ValueError(
            "launch contract must be OUTPUT_DIR/scientific_launch_contract.SEGMENT_ID.json"
        )
    if evidence_dir.exists():
        raise ValueError("evidence directory must not exist before launch")
    batch_root = args.batch_root.resolve(strict=True)
    if (batch_root.is_symlink() or not batch_root.is_dir() or
            batch_root.name != args.batch_id):
        raise ValueError("batch root/ID identity mismatch")
    try:
        solver_output.relative_to(batch_root)
    except ValueError as error:
        raise ValueError("solver output directory is outside the declared batch root") from error
    lock_root = args.lock_root.resolve()
    if lock_root != batch_root / ".internal-nozzle-one-solver":
        raise ValueError("lock root must be the one canonical batch-wide lock root")

    verified: list[tuple[Path, str, str]] = [
        (solver, solver_sha, "solver_executable"),
        (source_bundle, source_bundle_sha, "source_bundle_manifest"),
        (build_manifest, build_manifest_sha, "observable_qcc_build_manifest"),
        (schedule_path, schedule_sha, "launch_schedule"),
        (supervisor, supervisor_sha, "supervisor"),
    ]
    transfer_record: dict[str, object]
    bulk_target: dict[str, object] | str = "not_applicable"
    if args.case_role == "A":
        if any(value is not None for value in (
            args.transfer, args.transfer_manifest, args.transfer_manifest_sha256,
            args.precursor_convergence_report,
            args.precursor_convergence_report_sha256,
            args.projection_criteria, args.projection_criteria_sha256,
        )):
            raise ValueError("Case A forbids precursor transfer/evidence inputs")
        transfer_record = {
            "path": "not_applicable", "sha256": "not_applicable",
            "manifest_path": "not_applicable", "manifest_sha256": "not_applicable",
        }
    else:
        required_values = (
            args.transfer, args.transfer_manifest, args.transfer_manifest_sha256,
            args.precursor_convergence_report,
            args.precursor_convergence_report_sha256,
            args.projection_criteria, args.projection_criteria_sha256,
        )
        if any(value is None for value in required_values):
            raise ValueError("Cases B/C require complete precursor transfer evidence")
        transfer = regular(args.transfer, "precursor transfer table")
        manifest_path, manifest = load_manifest(args.transfer_manifest)
        manifest_sha = canonical_hex(
            str(args.transfer_manifest_sha256), 64, "transfer manifest SHA-256",
        )
        if sha256(manifest_path) != manifest_sha:
            raise ValueError("transfer manifest SHA-256 mismatch")
        if manifest.get("source_commit") != source_commit:
            raise ValueError("transfer manifest source commit mismatch")
        precursor_source_sha = validate_manifest_semantics(manifest)
        transfer_sha = sha256(transfer)
        if manifest.get("transfer_table_sha256") != transfer_sha:
            raise ValueError("transfer table changed after sealing")
        convergence_sha = canonical_hex(
            str(args.precursor_convergence_report_sha256), 64,
            "precursor convergence report SHA-256",
        )
        convergence, history, bulk_target = load_convergence_bulk_target(
            args.precursor_convergence_report, convergence_sha, manifest,
        )
        verified.extend((
            (transfer, transfer_sha, "precursor_transfer"),
            (manifest_path, manifest_sha, "precursor_transfer_manifest"),
            (convergence, convergence_sha, "precursor_convergence_report"),
            (history, str(bulk_target["history_sha256"]), "precursor_terminal_history"),
        ))
        acceptance = acceptance_module()
        projection_criteria_sha = canonical_hex(
            str(args.projection_criteria_sha256), 64,
            "projection criteria SHA-256",
        )
        projection_criteria, projection_criteria_payload = (
            acceptance.load_projection_criteria(
                args.projection_criteria, projection_criteria_sha,
            )
        )
        criteria_normalization = projection_criteria_payload["normalization"]
        if (not isinstance(criteria_normalization, dict) or
                not math.isclose(
                    float(criteria_normalization["velocity_scale"]),
                    float(bulk_target["bulk_velocity"]),
                    rel_tol=5.0e-12, abs_tol=1.0e-14,
                )):
            raise ValueError(
                "projection criteria velocity scale does not equal precursor Q/A"
            )
        verified.append((
            projection_criteria, projection_criteria_sha,
            "transfer_projection_criteria",
        ))
        transfer_record = {
            "path": str(transfer), "sha256": transfer_sha,
            "manifest_path": str(manifest_path), "manifest_sha256": manifest_sha,
            "producer_unsealed_metadata_sha256":
                manifest.get("producer_unsealed_metadata_sha256"),
            "precursor_source_sha256": precursor_source_sha,
            "projection_criteria": {
                "path": str(projection_criteria),
                "sha256": projection_criteria_sha,
                "criteria_id": projection_criteria_payload["criteria_id"],
            },
        }

    profile_record: dict[str, object] | str = "not_applicable"
    profile_values = (
        args.poiseuille_profile_evidence, args.poiseuille_profile_evidence_sha256,
        args.poiseuille_profile_acceptance, args.poiseuille_profile_acceptance_sha256,
    )
    if args.case_role == "C":
        profile_authority_values = (
            args.poiseuille_reference_artifact,
            args.poiseuille_reference_artifact_sha256,
            args.poiseuille_reference_module,
            args.poiseuille_reference_module_sha256,
        )
        if any(value is None for value in (*profile_values, *profile_authority_values)):
            raise ValueError("Case C requires complete Task02 Poiseuille-profile acceptance")
        evidence_sha = canonical_hex(
            str(args.poiseuille_profile_evidence_sha256), 64,
            "Poiseuille profile evidence SHA-256",
        )
        acceptance_sha = canonical_hex(
            str(args.poiseuille_profile_acceptance_sha256), 64,
            "Poiseuille profile acceptance SHA-256",
        )
        profile_evidence = regular(
            args.poiseuille_profile_evidence, "Poiseuille profile evidence",
        )
        profile_acceptance = regular(
            args.poiseuille_profile_acceptance, "Poiseuille profile acceptance",
        )
        if (sha256(profile_evidence) != evidence_sha or
                sha256(profile_acceptance) != acceptance_sha):
            raise ValueError("Poiseuille profile evidence/acceptance SHA-256 mismatch")
        reference_artifact = regular(
            args.poiseuille_reference_artifact, "Task02 reference artifact",
        )
        reference_artifact_sha = canonical_hex(
            str(args.poiseuille_reference_artifact_sha256), 64,
            "Task02 reference artifact SHA-256",
        )
        reference_module = regular(
            args.poiseuille_reference_module, "Task02 reference module",
        )
        reference_module_sha = canonical_hex(
            str(args.poiseuille_reference_module_sha256), 64,
            "Task02 reference module SHA-256",
        )
        payload = acceptance_module().validate_profile_acceptance(
            source_bundle, source_bundle_sha,
            reference_artifact, reference_artifact_sha,
            reference_module, reference_module_sha,
            profile_evidence, profile_acceptance,
        )
        profile_record = {
            "evidence_path": str(profile_evidence),
            "evidence_sha256": evidence_sha,
            "acceptance_path": str(profile_acceptance),
            "acceptance_sha256": acceptance_sha,
            "assessment_id": payload["assessment_id"],
            "reference_artifact_path": str(reference_artifact),
            "reference_artifact_sha256": reference_artifact_sha,
            "reference_module_path": str(reference_module),
            "reference_module_sha256": reference_module_sha,
            "pass": True,
        }
        if (profile_evidence != solver_output / "poiseuille_profile_validation.csv" or
                profile_acceptance != solver_output / "poiseuille_profile_acceptance.json"):
            raise ValueError("Case C profile artifacts must use canonical output-root paths")
        verified.extend((
            (profile_evidence, evidence_sha, "poiseuille_profile_evidence"),
            (profile_acceptance, acceptance_sha, "poiseuille_profile_acceptance"),
            (reference_artifact, reference_artifact_sha, "poiseuille_reference_artifact"),
            (reference_module, reference_module_sha, "poiseuille_reference_module"),
        ))
    elif any(value is not None for value in (
        *profile_values,
        args.poiseuille_reference_artifact,
        args.poiseuille_reference_artifact_sha256,
        args.poiseuille_reference_module,
        args.poiseuille_reference_module_sha256,
    )):
        raise ValueError("Cases A/B forbid Case-C Poiseuille-profile acceptance inputs")

    restore_record: dict[str, object]
    restore_args = (
        args.restore, args.restore_sha256, args.restore_metadata_sha256,
        args.restore_closure_sha256, args.predecessor_segment_id,
    )
    if args.restore is None:
        if any(value is not None for value in restore_args[1:]):
            raise ValueError("fresh segment forbids partial predecessor checkpoint identity")
        restore_record = {"kind": "fresh", "predecessor_segment_id": "not_applicable"}
    else:
        if any(value is None for value in restore_args[1:]):
            raise ValueError("restart requires predecessor ID and all checkpoint hashes")
        predecessor_id = canonical_identifier(
            str(args.predecessor_segment_id), "predecessor segment ID",
        )
        if predecessor_id == segment_id:
            raise ValueError("segment cannot name itself as predecessor")
        checkpoint = regular(args.restore, "restore checkpoint")
        metadata = regular(Path(str(checkpoint) + ".meta"), "restore metadata")
        closure = regular(
            Path(str(checkpoint) + ".prediction-closure-v4"), "restore closure",
        )
        checkpoint_sha = canonical_hex(
            str(args.restore_sha256), 64, "restore checkpoint SHA-256",
        )
        metadata_sha = canonical_hex(
            str(args.restore_metadata_sha256), 64, "restore metadata SHA-256",
        )
        closure_sha = canonical_hex(
            str(args.restore_closure_sha256), 64, "restore closure SHA-256",
        )
        for path, expected, label in (
            (checkpoint, checkpoint_sha, "restore checkpoint"),
            (metadata, metadata_sha, "restore metadata"),
            (closure, closure_sha, "restore closure"),
        ):
            if sha256(path) != expected:
                raise ValueError(f"{label} SHA-256 mismatch")
            verified.append((path, expected, label.replace(" ", "_")))
        restore_record = {
            "kind": "checkpoint",
            "predecessor_segment_id": predecessor_id,
            "checkpoint": {"path": str(checkpoint), "sha256": checkpoint_sha},
            "metadata": {"path": str(metadata), "sha256": metadata_sha},
            "prediction_closure": {"path": str(closure), "sha256": closure_sha},
        }

    solver_argv = [
        str(solver), *requested_solver[1:],
        "--execution-id", execution_id,
        "--segment-id", segment_id,
        "--case-role", args.case_role,
        "--solver-sha256", solver_sha,
        "--build-variant", str(role["build_variant"]),
        "--initial-state", str(role["initial_state"]),
    ]
    if args.case_role != "A":
        solver_argv.extend(("--precursor-transfer", str(transfer_record["path"])))
        solver_argv.extend((
            "--precursor-transfer-sha256", str(transfer_record["sha256"]),
            "--precursor-pressure-mode", "transferred",
            "--precursor-convergence-sha256",
            str(bulk_target["convergence_report_sha256"]),
            "--precursor-history-sha256", str(bulk_target["history_sha256"]),
            "--precursor-target-q", format(float(bulk_target["terminal_Q_l"]), ".17g"),
            "--precursor-target-area",
            format(float(bulk_target["terminal_liquid_area"]), ".17g"),
            "--precursor-target-velocity-tolerance",
            format(float(bulk_target["absolute_consistency_tolerance"]), ".17g"),
        ))
        if args.case_role == "C":
            solver_argv.extend((
                "--profile-bulk-velocity",
                format(float(bulk_target["bulk_velocity"]), ".17g"),
            ))
    if args.restore is not None:
        solver_argv.extend((
            "--restore", str(restore_record["checkpoint"]["path"]),
            "--restore-sha256", str(restore_record["checkpoint"]["sha256"]),
            "--restore-metadata-sha256", str(restore_record["metadata"]["sha256"]),
            "--restore-closure-sha256",
            str(restore_record["prediction_closure"]["sha256"]),
            "--predecessor-segment-id", str(restore_record["predecessor_segment_id"]),
        ))
    solver_argv.extend((
        "--source-commit", source_commit,
        "--source-sha", source_sha,
        "--schedule-version", str(schedule["schedule_version"]),
        "--schedule-sha", schedule_sha,
        "--schedule-tick-dt", format(float(schedule["master_tick_dt"]), ".17g"),
        "--schedule-tolerance", format(float(schedule["event_time_tolerance"]), ".17g"),
        "--light-base-stride", str(schedule["lightweight"]["base_stride"]),
        "--light-dense-stride", str(schedule["lightweight"]["dense_stride"]),
        "--field-base-stride", str(schedule["full_field"]["base_stride"]),
        "--field-dense-stride", str(schedule["full_field"]["dense_stride"]),
        "--checkpoint-stride", str(schedule["checkpoint_stride"]),
        "--dense-start-tick", str(schedule["dense_window"]["start_tick"]),
        "--dense-end-tick", str(schedule["dense_window"]["end_tick"]),
    ))

    python_executable = regular(
        Path(args.python_executable).resolve(strict=True), "Python executable",
    )
    verified_records = [
        {"label": label, "path": str(path), "sha256": digest}
        for path, digest, label in verified
    ]
    if len({record["path"] for record in verified_records}) != len(verified_records):
        raise ValueError("immutable input paths must be distinct")
    supervisor_argv = [
        str(python_executable), str(supervisor),
        "--evidence-dir", str(evidence_dir),
        "--cwd", str(cwd),
        "--lock-root", str(lock_root),
        "--timeout-seconds", format(args.timeout_seconds, ".17g"),
        "--heartbeat-seconds", format(args.heartbeat_seconds, ".17g"),
        "--execution-id", execution_id,
        "--segment-id", segment_id,
        "--run-id", segment_id,
        "--source-commit", source_commit,
        "--source-sha256", source_sha,
    ]
    for record in verified_records:
        supervisor_argv.extend((
            "--input-file-sha256", str(record["path"]), str(record["sha256"]),
        ))
    supervisor_argv.extend(("--", *solver_argv))
    return {
        "schema": LAUNCH_SCHEMA,
        "execution_id": execution_id,
        "segment_id": segment_id,
        "case_role": args.case_role,
        "case_id": case_id,
        "cwd": str(cwd),
        "output_dir": str(solver_output),
        "expected_runtime_contract": str(
            solver_output / f"scientific_runtime_contract.{segment_id}.json"
        ),
        "expected_initialization_contract": str(
            solver_output / f"initialization_contract.{segment_id}.json"
        ),
        "scientific_source_commit": source_commit,
        "source_sha256": source_sha,
        "source_bundle_manifest": {"path": str(source_bundle), "sha256": source_bundle_sha},
        "observable_qcc_build_manifest": {
            "path": str(build_manifest), "sha256": build_manifest_sha,
            "build_role": build_record["build_role"],
            "compile_run_id": build_record["compile_run_id"],
        },
        "batch_identity": {
            "batch_id": args.batch_id, "batch_root": str(batch_root),
            "canonical_lock_root": str(lock_root),
        },
        "schedule": {"path": str(schedule_path), "sha256": schedule_sha, **schedule},
        "solver": {
            "path": str(solver), "sha256": solver_sha,
            "expected_build_variant": role["build_variant"],
        },
        "role_contract": role,
        "precursor_transfer": transfer_record,
        "precursor_bulk_target": bulk_target,
        "poiseuille_profile_validation": profile_record,
        "restore": restore_record,
        "verified_inputs": verified_records,
        "supervisor": {
            "path": str(supervisor), "sha256": supervisor_sha,
            "evidence_dir": str(evidence_dir), "lock_root": str(lock_root),
        },
        "solver_argv": solver_argv,
        "supervisor_argv": supervisor_argv,
        "execution_contract": "invoke_supervisor_argv_verbatim_once",
    }


def validate_verified_inputs(
    records: object, expected: dict[str, str], *, terminal: bool,
) -> None:
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError("supervisor input-evidence cardinality mismatch")
    observed: dict[str, dict[str, object]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("resolved_path"), str):
            raise ValueError("malformed supervisor input-evidence record")
        expected_keys = {
            "requested_path", "resolved_path", "size_bytes", "expected_sha256",
            "observed_sha256", "verified",
        }
        if terminal:
            expected_keys |= {"observed_sha256_after", "unchanged_during_run"}
        if set(record) != expected_keys:
            raise ValueError("supervisor input-evidence key set mismatch")
        resolved = str(Path(str(record["resolved_path"])).resolve(strict=True))
        if resolved in observed:
            raise ValueError("duplicate supervisor input-evidence path")
        observed[resolved] = record
    if set(observed) != set(expected):
        raise ValueError("supervisor verified the wrong immutable input set")
    for path, digest in expected.items():
        record = observed[path]
        if (
            record.get("expected_sha256") != digest
            or record.get("observed_sha256") != digest
            or record.get("verified") is not True
            or record.get("size_bytes") != Path(path).stat().st_size
        ):
            raise ValueError(f"supervisor input identity mismatch: {path}")
        if terminal and (
            record.get("observed_sha256_after") != digest
            or record.get("unchanged_during_run") is not True
        ):
            raise ValueError(f"supervisor input changed during run: {path}")


def reconcile_supervision(contract: dict[str, object], supervisor_rc: int) -> None:
    evidence = Path(str(contract["supervisor"]["evidence_dir"]))
    _, launch = load_object(evidence / "launch.json", "supervisor launch record")
    _, terminal = load_object(evidence / "terminal.json", "supervisor terminal record")
    expected_common = {
        "schema": "internal_nozzle_supervision_v2",
        "execution_id": contract["execution_id"],
        "segment_id": contract["segment_id"],
        "cwd": contract["cwd"],
        "argv": contract["solver_argv"],
        "source_commit": contract["scientific_source_commit"],
        "source_sha256": contract["source_sha256"],
    }
    for key, value in expected_common.items():
        if launch.get(key) != value or terminal.get(key) != value:
            raise ValueError(f"supervisor evidence mismatch: {key}")
    run_id = launch.get("run_id")
    if (
        run_id != contract["segment_id"]
        or terminal.get("run_id") != contract["segment_id"]
    ):
        raise ValueError("supervisor run identity mismatch")
    expected_inputs = {
        str(Path(str(record["path"])).resolve(strict=True)): str(record["sha256"])
        for record in contract["verified_inputs"]
    }
    validate_verified_inputs(launch.get("verified_inputs"), expected_inputs, terminal=False)
    validate_verified_inputs(terminal.get("verified_inputs"), expected_inputs, terminal=True)
    if terminal.get("input_identity_changed") is not False:
        raise ValueError("supervisor reports changed immutable input")
    if terminal.get("child_exists_after_wait") is not False:
        raise ValueError("supervisor did not prove child termination")
    identity_payload = json.dumps(
        {"argv": contract["solver_argv"], "cwd": contract["cwd"]},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    command_identity = hashlib.sha256(identity_payload).hexdigest()
    for record in (launch, terminal):
        if record.get("command_cwd_sha256") != command_identity:
            raise ValueError("supervisor command identity mismatch")
        expected_writer = str(Path(str(contract["supervisor"]["lock_root"])) / "one-solver.lock")
        if record.get("writer_lock") != expected_writer:
            raise ValueError("supervisor writer-lock identity mismatch")
    child_rc = terminal.get("returncode")
    state = terminal.get("terminal_state")
    if isinstance(child_rc, bool) or not isinstance(child_rc, int):
        raise ValueError("supervisor terminal return code is invalid")
    expected_supervisor_rc: int
    if state == "normal_exit" and child_rc >= 0:
        expected_supervisor_rc = child_rc
    elif state == "signal_exit" and child_rc < 0:
        expected_supervisor_rc = 128 - child_rc
    elif state == "timeout":
        expected_supervisor_rc = 124
    elif state in {"supervisor_error", "input_identity_changed"}:
        expected_supervisor_rc = 125
    elif state == "supervisor_signal" and isinstance(terminal.get("supervisor_signal"), int):
        expected_supervisor_rc = 128 + int(terminal["supervisor_signal"])
    else:
        raise ValueError("supervisor terminal-state classification is inconsistent")
    if supervisor_rc != expected_supervisor_rc:
        raise ValueError("supervisor process and terminal return codes disagree")
    for stem in ("stdout", "stderr"):
        path = evidence / f"{stem}.log"
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing regular supervisor {stem} log")
        if (
            terminal.get(f"{stem}_size_bytes") != path.stat().st_size
            or terminal.get(f"{stem}_sha256") != sha256(path)
        ):
            raise ValueError(f"supervisor {stem} log identity mismatch")
    for key in ("active_lock", "duplicate_lock", "writer_lock"):
        value = launch.get(key) if key == "active_lock" else terminal.get(key)
        if not isinstance(value, str) or Path(value).exists():
            raise ValueError(f"supervisor did not release {key}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-role", choices=tuple(ROLE_CONTRACTS), required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--segment-id", required=True)
    parser.add_argument("--supervisor", type=Path, required=True)
    parser.add_argument("--supervisor-sha256", required=True)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--lock-root", type=Path, required=True)
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--heartbeat-seconds", type=float, default=5.0)
    parser.add_argument("--run-id")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--source-bundle-manifest", type=Path, required=True)
    parser.add_argument("--source-bundle-manifest-sha256", required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--build-manifest-sha256", required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--schedule-sha256", required=True)
    parser.add_argument("--schedule-version", required=True)
    parser.add_argument("--solver-sha256", required=True)
    parser.add_argument("--transfer", type=Path)
    parser.add_argument("--transfer-manifest", type=Path)
    parser.add_argument("--transfer-manifest-sha256")
    parser.add_argument("--precursor-convergence-report", type=Path)
    parser.add_argument("--precursor-convergence-report-sha256")
    parser.add_argument("--projection-criteria", type=Path)
    parser.add_argument("--projection-criteria-sha256")
    parser.add_argument("--poiseuille-profile-evidence", type=Path)
    parser.add_argument("--poiseuille-profile-evidence-sha256")
    parser.add_argument("--poiseuille-profile-acceptance", type=Path)
    parser.add_argument("--poiseuille-profile-acceptance-sha256")
    parser.add_argument("--poiseuille-reference-artifact", type=Path)
    parser.add_argument("--poiseuille-reference-artifact-sha256")
    parser.add_argument("--poiseuille-reference-module", type=Path)
    parser.add_argument("--poiseuille-reference-module-sha256")
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--restore-sha256")
    parser.add_argument("--restore-metadata-sha256")
    parser.add_argument("--restore-closure-sha256")
    parser.add_argument("--predecessor-segment-id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("solver_argv", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv)
    if parsed.timeout_seconds <= 0.0 or parsed.heartbeat_seconds <= 0.0:
        parser.error("timeout and heartbeat must be positive")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_contract(args)
    atomic_json(args.output, payload)
    print(json.dumps({
        "output": str(args.output),
        "execution_id": payload["execution_id"],
        "segment_id": payload["segment_id"],
        "case_role": payload["case_role"],
        "transfer_sha256": payload["precursor_transfer"]["sha256"],
    }, sort_keys=True))
    completed = subprocess.run(
        payload["supervisor_argv"], cwd=payload["cwd"], check=False,
    )
    try:
        reconcile_supervision(payload, completed.returncode)
    except (OSError, ValueError) as error:
        print(f"ERROR: unverified supervisor result: {error}", file=sys.stderr)
        return 125
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
