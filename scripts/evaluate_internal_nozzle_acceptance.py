#!/usr/bin/env python3
"""Produce and validate immutable projection and Case-C profile evidence.

The projection limits are supplied only by a pre-run criteria artifact which is
hash-bound by the launch contract.  The Case-C profile check has no tunable
acceptance limit: it deterministically characterizes the declared 20-odd-mode
C series against the Task-02 256-odd-mode reference on one fixed Simpson grid.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from pathlib import Path


PROJECTION_CRITERIA_SCHEMA = "internal_nozzle_transfer_projection_criteria_v1"
PROJECTION_ACCEPTANCE_SCHEMA = "internal_nozzle_transfer_projection_acceptance_v2"
PROFILE_ACCEPTANCE_SCHEMA = "internal_nozzle_poiseuille_profile_acceptance_v2"
PROJECTION_PHASES = (
    "pre_projection_input", "pre_advection_closure",
    "post_timestep_projection", "post_timestep_projection",
)
PROJECTION_METRICS = (
    "divergence_l2", "divergence_max", "velocity_impulse_l2",
    "cell_pressure_change_l2", "projection_pressure_adjustment_l2",
)
PROJECTION_SELECTION = "records_0_and_1_immediate_transfer_projection_only"
PROJECTION_DIVERGENCE = (
    "basilisk_face_flux_difference_over_Delta;uf_already_contains_face_metric"
)
PROJECTION_LENGTH_SCALE = 0.13925712636838891
PROJECTION_PRESSURE_SCALE = 351.48
PROJECTION_NORMALIZED_LIMITS = {
    "divergence_l2": 1.0e-3,
    "divergence_max": 5.0e-2,
    "velocity_impulse_l2": 2.0e-2,
    "cell_pressure_change_l2": 1.0e-2,
    "projection_pressure_adjustment_l2": 1.0e-2,
}
PROFILE_HEADER = (
    "sample_index", "y_over_width", "z_over_height", "quadrature_weight",
    "wall_sample", "implementation_unit_velocity", "reference_unit_velocity",
)
PROFILE_CONFIGURATION = {
    "aspect_ratio": 2.0,
    "implementation_odd_mode_count": 20,
    "reference_odd_mode_count": 256,
    "width_intervals": 64,
    "height_intervals": 32,
    "quadrature": "tensor_composite_simpson_including_exact_zero_walls",
    "normalization": "independent_continuum_bulk_velocity_equals_one",
}
PROFILE_LIMITS = {
    "weighted_relative_l2_to_high_reference": 5.0e-5,
    "peak_normalized_linf_to_high_reference": 1.0e-4,
    "absolute_simpson_bulk_error": 2.0e-5,
    "exact_wall_no_slip": 0.0,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, context: str) -> dict[str, object]:
    def reject_nonfinite(value: str) -> object:
        raise ValueError(f"nonfinite JSON constant: {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
            parse_constant=reject_nonfinite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{context}: invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{context}: JSON root must be an object")
    return value


def regular(path: Path, context: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{context}: symlink forbidden")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{context}: missing file") from error
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"{context}: nonempty regular file required")
    return resolved


def canonical_hash(value: object, length: int, context: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"{context}: expected {length} lowercase hex digits")
    return value


def required_text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: nonempty string required")
    return value


def finite(value: object, context: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{context}: finite number required")
    try:
        result = float(value)
    except ValueError as error:
        raise ValueError(f"{context}: finite number required") from error
    if not math.isfinite(result) or (nonnegative and result < 0.0):
        raise ValueError(f"{context}: invalid number")
    return result


def exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{context}: key set mismatch")


def csv_rows(path: Path, header: tuple[str, ...], context: str) -> list[dict[str, str]]:
    resolved = regular(path, context)
    with resolved.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != header:
            raise ValueError(f"{context}: exact CSV header mismatch")
        rows = list(reader)
    if not rows or any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{context}: empty or malformed CSV")
    return rows


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load_projection_criteria(path: Path, expected_sha256: str) -> tuple[Path, dict[str, object]]:
    criteria_path = regular(path, "projection criteria")
    canonical_hash(expected_sha256, 64, "projection criteria SHA-256")
    if sha256_file(criteria_path) != expected_sha256:
        raise ValueError("projection criteria SHA-256 mismatch")
    payload = load_json(criteria_path, "projection criteria")
    exact_keys(payload, {
        "schema", "criteria_id", "applicable_case_roles", "phase_selection",
        "divergence_convention", "normalization", "metrics", "claim_boundary",
    }, "projection criteria")
    if (payload.get("schema") != PROJECTION_CRITERIA_SCHEMA or
            payload.get("applicable_case_roles") != ["B", "C"] or
            payload.get("phase_selection") != PROJECTION_SELECTION or
            payload.get("divergence_convention") != PROJECTION_DIVERGENCE):
        raise ValueError("projection criteria semantic mismatch")
    required_text(payload.get("criteria_id"), "projection criteria ID")
    required_text(payload.get("claim_boundary"), "projection criteria claim boundary")
    normalization = payload.get("normalization")
    if not isinstance(normalization, dict):
        raise ValueError("projection criteria normalization is missing")
    exact_keys(normalization, {"length_scale", "velocity_scale", "pressure_scale"},
               "projection criteria normalization")
    length_scale = finite(normalization.get("length_scale"), "projection length scale")
    velocity_scale = finite(normalization.get("velocity_scale"), "projection velocity scale")
    pressure_scale = finite(normalization.get("pressure_scale"), "projection pressure scale")
    if (length_scale <= 0.0 or velocity_scale <= 0.0 or pressure_scale <= 0.0 or
            not math.isclose(length_scale, PROJECTION_LENGTH_SCALE,
                             rel_tol=0.0, abs_tol=1.0e-15) or
            not math.isclose(pressure_scale, PROJECTION_PRESSURE_SCALE,
                             rel_tol=0.0, abs_tol=1.0e-12)):
        raise ValueError("projection criteria normalization is not the fixed Task-04 scale contract")
    dimensional_scales = {
        "divergence_l2": velocity_scale / length_scale,
        "divergence_max": velocity_scale / length_scale,
        "velocity_impulse_l2": velocity_scale,
        "cell_pressure_change_l2": pressure_scale,
        "projection_pressure_adjustment_l2": pressure_scale,
    }
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(PROJECTION_METRICS):
        raise ValueError("projection criteria metric set mismatch")
    for metric in PROJECTION_METRICS:
        specification = metrics[metric]
        if not isinstance(specification, dict):
            raise ValueError("projection criterion must be an object")
        exact_keys(specification, {"aggregation", "operator", "limit"},
                   f"projection criterion {metric}")
        if (specification.get("aggregation") != "max_over_selected_records" or
                specification.get("operator") != "<="):
            raise ValueError("projection criterion operation mismatch")
        limit = finite(specification.get("limit"), f"projection criterion {metric}",
                       nonnegative=True)
        expected_limit = (PROJECTION_NORMALIZED_LIMITS[metric] *
                          dimensional_scales[metric])
        if not math.isclose(limit, expected_limit, rel_tol=1.0e-12, abs_tol=1.0e-15):
            raise ValueError(f"projection criterion {metric} is not the fixed normalized limit")
    return criteria_path, payload


PROJECTION_HEADER = (
    "case_id", "record_index", "phase", "t", "i", "divergence_l2",
    "divergence_max", "velocity_impulse_l2", "cell_pressure_change_l2",
    "projection_pressure_adjustment_l2", "fluid_volume", "initial_state",
    "inlet_mode", "precursor_pressure_mode", "transfer_sha256", "execution_id",
    "segment_id", "case_role",
)


def projection_measurements(path: Path) -> tuple[list[dict[str, str]], dict[str, str], dict[str, float]]:
    rows = csv_rows(path, PROJECTION_HEADER, "projection evidence")
    if len(rows) != len(PROJECTION_PHASES):
        raise ValueError("projection evidence record count mismatch")
    identity = {
        key: required_text(rows[0].get(key), f"projection {key}")
        for key in ("execution_id", "segment_id", "case_id", "case_role", "transfer_sha256")
    }
    if identity["case_role"] not in {"B", "C"}:
        raise ValueError("projection evidence is not Case B/C")
    canonical_hash(identity["transfer_sha256"], 64, "projection transfer SHA-256")
    for expected_index, (row, phase) in enumerate(zip(rows, PROJECTION_PHASES)):
        try:
            index = int(row["record_index"])
            iteration = int(row["i"])
        except ValueError as error:
            raise ValueError("projection evidence index is invalid") from error
        if (str(index) != row["record_index"] or index != expected_index or
                iteration < 0 or row["phase"] != phase or
                any(row[key] != value for key, value in identity.items())):
            raise ValueError("projection evidence order/identity mismatch")
        finite(row["t"], "projection time", nonnegative=True)
        if finite(row["fluid_volume"], "projection volume") <= 0.0:
            raise ValueError("projection fluid volume must be positive")
        for metric in PROJECTION_METRICS:
            finite(row[metric], f"projection {metric}", nonnegative=True)
    selected = rows[:2]
    observed = {
        metric: max(float(row[metric]) for row in selected)
        for metric in PROJECTION_METRICS
    }
    return rows, identity, observed


def expected_projection_acceptance(
    criteria_path: Path, criteria_sha256: str, criteria: dict[str, object],
    evidence_path: Path, identity: dict[str, str], observed: dict[str, float],
) -> dict[str, object]:
    predicates = []
    passed = True
    specifications = criteria["metrics"]
    assert isinstance(specifications, dict)
    for metric in PROJECTION_METRICS:
        specification = specifications[metric]
        assert isinstance(specification, dict)
        limit = float(specification["limit"])
        metric_passed = observed[metric] <= limit
        passed = passed and metric_passed
        predicates.append({
            "metric": metric,
            "aggregation": "max_over_selected_records",
            "operator": "<=",
            "observed": observed[metric],
            "limit": limit,
            "passed": metric_passed,
        })
    return {
        "schema": PROJECTION_ACCEPTANCE_SCHEMA,
        "assessment_id": (
            f"{criteria['criteria_id']}:{identity['execution_id']}:"
            f"{identity['segment_id']}:{identity['case_role']}"
        ),
        **identity,
        "acceptance_basis": "hash_bound_pre_run_projection_criteria_v1",
        "criteria": {
            "path": str(criteria_path), "sha256": criteria_sha256,
            "criteria_id": criteria["criteria_id"],
        },
        "projection_evidence": {
            "path": evidence_path.name, "sha256": sha256_file(evidence_path),
        },
        "selected_record_indices": [0, 1],
        "context_record_indices": [2, 3],
        "predicates": predicates,
        "pass": passed,
        "claim_boundary": (
            "immediate transfer/projection numerical acceptance only; records 2-3 are "
            "early physical-evolution context and are not acceptance inputs"
        ),
    }


def validate_projection_acceptance(
    criteria_path: Path, criteria_sha256: str, evidence_path: Path,
    acceptance_path: Path,
) -> dict[str, object]:
    criteria_path, criteria = load_projection_criteria(criteria_path, criteria_sha256)
    evidence_path = regular(evidence_path, "projection evidence")
    _, identity, observed = projection_measurements(evidence_path)
    expected = expected_projection_acceptance(
        criteria_path, criteria_sha256, criteria, evidence_path, identity, observed,
    )
    acceptance = load_json(regular(acceptance_path, "projection acceptance"),
                           "projection acceptance")
    if acceptance != expected:
        raise ValueError("projection acceptance is not the deterministic criteria result")
    if acceptance.get("pass") is not True:
        raise ValueError("projection acceptance predicates did not pass")
    return acceptance


def _cosh_ratio(numerator: float, denominator: float) -> float:
    # log(cosh(x)) without overflow; all inputs here are nonnegative magnitudes.
    def log_cosh(value: float) -> float:
        absolute = abs(value)
        return absolute + math.log1p(math.exp(-2.0 * absolute)) - math.log(2.0)
    return math.exp(log_cosh(numerator) - log_cosh(denominator))


def c_profile_unit_bulk(y: float, z: float, modes: int = 20) -> float:
    width, height = 2.0, 1.0
    if abs(y) >= width / 2.0 or abs(z) >= height / 2.0:
        return 0.0
    value = 0.0
    bulk = 0.0
    for offset in range(modes):
        n = 2 * offset + 1
        sign = -1.0 if offset % 2 else 1.0
        argument = n * math.pi * width / (2.0 * height)
        transverse = 1.0 - _cosh_ratio(n * math.pi * y / height, argument)
        value += sign * transverse * math.cos(n * math.pi * z / height) / n**3
        bulk += 2.0 / (math.pi * n**4) * (
            1.0 - 2.0 * height * math.tanh(argument) / (n * math.pi * width)
        )
    if bulk <= 0.0:
        raise ValueError("invalid Case-C profile normalization")
    return value / bulk


def exact_profile_velocity(y: float, z: float, modes: int = 256) -> float:
    width, height = 2.0, 1.0
    if abs(y) >= width / 2.0 or abs(z) >= height / 2.0:
        return 0.0
    correction = 0.0
    for offset in range(modes):
        n = 2 * offset + 1
        sign = -1.0 if offset % 2 else 1.0
        k = n * math.pi / height
        ratio = _cosh_ratio(k * y, k * width / 2.0)
        correction += sign * ratio * math.cos(k * z) / n**3
    return 0.5 * (0.25 - z * z - 8.0 / math.pi**3 * correction)


def simpson_weight(index: int, intervals: int) -> int:
    if index in {0, intervals}:
        return 1
    return 4 if index % 2 else 2


def source_record(bundle: dict[str, object], relative: str) -> dict[str, object]:
    rows = bundle.get("tracked_behavior_files")
    if not isinstance(rows, list):
        raise ValueError("source bundle tracked files are malformed")
    matches = [row for row in rows if isinstance(row, dict) and row.get("path") == relative]
    if len(matches) != 1:
        raise ValueError(f"source bundle does not bind {relative}")
    canonical_hash(matches[0].get("sha256"), 64, f"source record {relative}")
    return matches[0]


def verified_c_profile_function(header: Path, expected_sha256: str) -> str:
    header = regular(header, "Case-C implementation header")
    if sha256_file(header) != expected_sha256:
        raise ValueError("Case-C implementation header differs from source bundle")
    source = header.read_text(encoding="utf-8")
    marker = "static double internal_nozzle_poiseuille_unit_bulk"
    start = source.find(marker)
    if start < 0 or source.find(marker, start + 1) >= 0:
        raise ValueError("Case-C profile function is missing or duplicated")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError("Case-C profile function has no body")
    depth = 0
    end = -1
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end < 0:
        raise ValueError("Case-C profile function body is unterminated")
    function = source[start:end]
    compact = " ".join(function.split())
    required_fragments = (
        "for (int n = 1; n <= 39; n += 2)",
        "fabs(yp) >= 0.5*width || fabs(zp) >= 0.5*height",
        "cosh(n*pi*yp/height)/cosh(argument)",
        "cos(n*pi*zp/height)/(nd*nd*nd)",
        "2./(pi*sq(sq(nd)))",
        "return bulk > 0. ? value/bulk : 0.;",
    )
    for fragment in required_fragments:
        if fragment not in compact:
            raise ValueError(f"Case-C source violates the fixed profile contract: {fragment}")
    return hashlib.sha256(function.encode("utf-8")).hexdigest()


def load_profile_authority(
    source_bundle_path: Path, source_bundle_sha256: str,
    reference_artifact_path: Path, reference_artifact_sha256: str,
    reference_module_path: Path, reference_module_sha256: str,
) -> tuple[Path, Path, Path, dict[str, object]]:
    source_bundle = regular(source_bundle_path, "source bundle")
    reference_artifact = regular(reference_artifact_path, "Task02 reference artifact")
    reference_module = regular(reference_module_path, "Task02 reference module")
    for path, expected, label in (
        (source_bundle, source_bundle_sha256, "source bundle"),
        (reference_artifact, reference_artifact_sha256, "Task02 reference artifact"),
        (reference_module, reference_module_sha256, "Task02 reference module"),
    ):
        canonical_hash(expected, 64, f"{label} SHA-256")
        if sha256_file(path) != expected:
            raise ValueError(f"{label} SHA-256 mismatch")
    bundle = load_json(source_bundle, "source bundle")
    if bundle.get("schema") != "internal_nozzle_source_bundle_v1":
        raise ValueError("profile authority requires the canonical source bundle")
    c_record = source_record(
        bundle, "cases/basilisk/internal_nozzle_precursor_start.h",
    )
    module_record = source_record(bundle, "scripts/rectangular_poiseuille_reference.py")
    if module_record.get("sha256") != reference_module_sha256:
        raise ValueError("Task02 reference module is not the source-bundle module")
    reference = load_json(reference_artifact, "Task02 reference artifact")
    exact_keys(reference, {
        "schema", "equation", "boundary_condition", "normalization", "metrics",
        "series_convergence", "conductance_series_convergence",
        "independent_five_point_poisson", "claim_boundary",
    }, "Task02 reference artifact")
    metrics = reference.get("metrics")
    if (reference.get("schema") != "rectangular_poiseuille_reference_v1" or
            not isinstance(metrics, dict) or metrics.get("width") != 2.0 or
            metrics.get("height") != 1.0 or metrics.get("modes") != 256 or
            metrics.get("quadrature_order") != 256):
        raise ValueError("Task02 reference artifact is not the fixed 2:1 high-mode result")
    bulk = finite(metrics.get("bulk_velocity"), "Task02 bulk velocity")
    if bulk <= 0.0:
        raise ValueError("Task02 bulk velocity must be positive")
    repository_root = reference_module.parent.parent
    function_sha256 = verified_c_profile_function(
        repository_root / "cases/basilisk/internal_nozzle_precursor_start.h",
        str(c_record["sha256"]),
    )
    return source_bundle, reference_artifact, reference_module, {
        "bundle": bundle,
        "c_source_sha256": c_record["sha256"],
        "c_profile_function_sha256": function_sha256,
        "bulk_velocity": bulk,
    }


def profile_rows_and_characterization(reference_bulk: float) -> tuple[list[list[object]], dict[str, float]]:
    ny = int(PROFILE_CONFIGURATION["width_intervals"])
    nz = int(PROFILE_CONFIGURATION["height_intervals"])
    dy, dz = 2.0 / ny, 1.0 / nz
    rows: list[list[object]] = []
    weighted_error_squared = 0.0
    weighted_reference_squared = 0.0
    weighted_implementation = 0.0
    total_weight = 0.0
    maximum_error = 0.0
    reference_peak = 0.0
    maximum_wall_velocity = 0.0
    index = 0
    for iy in range(ny + 1):
        y = -1.0 + iy * dy
        for iz in range(nz + 1):
            z = -0.5 + iz * dz
            wall = iy in {0, ny} or iz in {0, nz}
            weight = simpson_weight(iy, ny) * simpson_weight(iz, nz) * dy * dz / 9.0
            implementation = c_profile_unit_bulk(y, z, 20)
            reference = exact_profile_velocity(y, z, 256) / reference_bulk
            error = abs(implementation - reference)
            rows.append([
                index, format(y / 2.0, ".17g"), format(z, ".17g"),
                format(weight, ".17g"), "true" if wall else "false",
                format(implementation, ".17g"), format(reference, ".17g"),
            ])
            total_weight += weight
            weighted_error_squared += weight * error * error
            weighted_reference_squared += weight * reference * reference
            weighted_implementation += weight * implementation
            maximum_error = max(maximum_error, error)
            reference_peak = max(reference_peak, abs(reference))
            if wall:
                maximum_wall_velocity = max(maximum_wall_velocity, abs(implementation))
            index += 1
    return rows, {
        "weighted_relative_l2_to_high_reference": math.sqrt(
            weighted_error_squared / weighted_reference_squared
        ),
        "peak_normalized_linf_to_high_reference": maximum_error / reference_peak,
        "absolute_simpson_bulk_error": abs(weighted_implementation / total_weight - 1.0),
        "exact_wall_no_slip": maximum_wall_velocity,
    }


def write_profile_evidence(path: Path, rows: list[list[object]]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(PROFILE_HEADER)
        writer.writerows(rows)


def expected_profile_acceptance(
    source_bundle: Path, source_bundle_sha256: str, c_source_sha256: str,
    c_profile_function_sha256: str,
    reference_artifact: Path, reference_artifact_sha256: str,
    reference_module: Path, reference_module_sha256: str,
    evidence: Path, characterization: dict[str, float],
) -> dict[str, object]:
    predicates = []
    passed = True
    for metric, limit in PROFILE_LIMITS.items():
        observed = characterization[metric]
        metric_passed = observed == 0.0 if limit == 0.0 else observed <= limit
        passed = passed and metric_passed
        predicates.append({
            "metric": metric,
            "operator": "==" if limit == 0.0 else "<=",
            "observed": observed,
            "limit": limit,
            "passed": metric_passed,
        })
    return {
        "schema": PROFILE_ACCEPTANCE_SCHEMA,
        "assessment_id": "task02-case-c-fixed-series-characterization-v1",
        "classification": "poiseuille_profile_implementation_accepted",
        "acceptance_basis": "fixed_20_odd_mode_vs_task02_256_odd_mode_characterization_v1",
        "source_bundle": {"path": str(source_bundle), "sha256": source_bundle_sha256},
        "case_c_profile_source_sha256": c_source_sha256,
        "case_c_profile_function_sha256": c_profile_function_sha256,
        "task02_reference_artifact": {
            "path": str(reference_artifact), "sha256": reference_artifact_sha256,
        },
        "task02_reference_module": {
            "path": str(reference_module), "sha256": reference_module_sha256,
        },
        "profile_evidence": {"path": evidence.name, "sha256": sha256_file(evidence)},
        "configuration": dict(PROFILE_CONFIGURATION),
        "characterization": characterization,
        "predicates": predicates,
        "pass": passed,
        "claim_boundary": (
            "deterministic implementation/truncation characterization; no physical "
            "validation or adjustable scientific acceptance threshold"
        ),
    }


def validate_profile_acceptance(
    source_bundle_path: Path, source_bundle_sha256: str,
    reference_artifact_path: Path, reference_artifact_sha256: str,
    reference_module_path: Path, reference_module_sha256: str,
    evidence_path: Path, acceptance_path: Path,
) -> dict[str, object]:
    source_bundle, reference_artifact, reference_module, authority = load_profile_authority(
        source_bundle_path, source_bundle_sha256, reference_artifact_path,
        reference_artifact_sha256, reference_module_path, reference_module_sha256,
    )
    evidence = regular(evidence_path, "Poiseuille profile evidence")
    actual_rows = csv_rows(evidence, PROFILE_HEADER, "Poiseuille profile evidence")
    expected_rows, characterization = profile_rows_and_characterization(
        float(authority["bulk_velocity"]),
    )
    if len(actual_rows) != len(expected_rows):
        raise ValueError("Poiseuille profile evidence grid cardinality mismatch")
    for actual, expected in zip(actual_rows, expected_rows):
        if [actual[name] for name in PROFILE_HEADER] != [str(value) for value in expected]:
            raise ValueError("Poiseuille profile evidence is not the fixed deterministic grid")
    expected = expected_profile_acceptance(
        source_bundle, source_bundle_sha256, str(authority["c_source_sha256"]),
        str(authority["c_profile_function_sha256"]),
        reference_artifact, reference_artifact_sha256,
        reference_module, reference_module_sha256, evidence, characterization,
    )
    acceptance = load_json(regular(acceptance_path, "Poiseuille profile acceptance"),
                           "Poiseuille profile acceptance")
    if acceptance != expected:
        raise ValueError("Poiseuille profile acceptance is not the deterministic Task02 result")
    if acceptance.get("pass") is not True:
        raise ValueError("Poiseuille profile implementation exceeds fixed predicates")
    return acceptance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    projection = subparsers.add_parser("projection")
    projection.add_argument("--criteria", type=Path, required=True)
    projection.add_argument("--criteria-sha256", required=True)
    projection.add_argument("--evidence", type=Path, required=True)
    projection.add_argument("--output", type=Path, required=True)
    profile = subparsers.add_parser("profile")
    profile.add_argument("--source-bundle", type=Path, required=True)
    profile.add_argument("--source-bundle-sha256", required=True)
    profile.add_argument("--reference-artifact", type=Path, required=True)
    profile.add_argument("--reference-artifact-sha256", required=True)
    profile.add_argument("--reference-module", type=Path, required=True)
    profile.add_argument("--reference-module-sha256", required=True)
    profile.add_argument("--evidence-output", type=Path, required=True)
    profile.add_argument("--acceptance-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "projection":
        criteria_path, criteria = load_projection_criteria(
            args.criteria, args.criteria_sha256,
        )
        evidence = regular(args.evidence, "projection evidence")
        _, identity, observed = projection_measurements(evidence)
        payload = expected_projection_acceptance(
            criteria_path, args.criteria_sha256, criteria, evidence, identity, observed,
        )
        atomic_json(args.output, payload)
        print(json.dumps(payload, sort_keys=True, allow_nan=False))
        return 0 if payload["pass"] else 1
    source_bundle, reference_artifact, reference_module, authority = load_profile_authority(
        args.source_bundle, args.source_bundle_sha256,
        args.reference_artifact, args.reference_artifact_sha256,
        args.reference_module, args.reference_module_sha256,
    )
    rows, characterization = profile_rows_and_characterization(
        float(authority["bulk_velocity"]),
    )
    write_profile_evidence(args.evidence_output, rows)
    evidence = regular(args.evidence_output, "Poiseuille profile evidence")
    payload = expected_profile_acceptance(
        source_bundle, args.source_bundle_sha256, str(authority["c_source_sha256"]),
        str(authority["c_profile_function_sha256"]),
        reference_artifact, args.reference_artifact_sha256,
        reference_module, args.reference_module_sha256,
        evidence, characterization,
    )
    atomic_json(args.acceptance_output, payload)
    validate_profile_acceptance(
        source_bundle, args.source_bundle_sha256,
        reference_artifact, args.reference_artifact_sha256,
        reference_module, args.reference_module_sha256,
        evidence, args.acceptance_output,
    )
    print(json.dumps(payload, sort_keys=True, allow_nan=False))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
