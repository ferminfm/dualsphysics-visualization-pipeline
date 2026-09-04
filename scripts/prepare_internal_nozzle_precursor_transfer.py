#!/usr/bin/env python3
"""Create a complete target-grid precursor transfer table.

No additional interpolation is performed here.  The precursor exporter uses
Basilisk interpolation to sample the accepted two-phase target leaf centers;
this tool then joins those samples exactly and fails closed on missing,
duplicate, nonfinite, or off-grid rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable, Iterable

from validate_internal_nozzle_checkpoint_v4 import validate as validate_closure_v4

TARGET_FIELDS = ("x", "y", "z", "level", "Delta", "cs", "f")
TRANSFER_FIELDS = TARGET_FIELDS + ("ux", "uy", "uz", "p")
SOURCE_FIELDS = TARGET_FIELDS + (
    "source_sample_x", "exit_clamped", "ux", "uy", "uz", "p",
)
UNSEALED_SCHEMA = "internal_nozzle_precursor_unsealed_export_v2"
TARGET_SAMPLING_METHOD = (
    "basilisk_interpolate_at_target_leaf_center_or_strict_outlet_"
    "straddle_internal_limit_v2"
)
TARGET_CLAMP_RULE = (
    "clamp_only_when_target_leaf_strictly_straddles_geometric_outlet"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(row: dict[str, str], names: Iterable[str], context: str) -> None:
    for name in names:
        try:
            value = float(row[name])
        except (KeyError, ValueError) as error:
            raise ValueError(f"{context}: invalid {name}") from error
        if not math.isfinite(value):
            raise ValueError(f"{context}: nonfinite {name}")


def key(row: dict[str, str], context: str) -> tuple[object, ...]:
    finite(row, ("x", "y", "z", "Delta", "cs", "f"), context)
    try:
        level = int(row["level"])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{context}: invalid level") from error
    if (level < 0 or float(row["Delta"]) <= 0.0 or
            not 0.0 < float(row["cs"]) <= 1.0 or
            not 0.0 < float(row["f"]) <= 1.0):
        raise ValueError(f"{context}: invalid grid geometry")
    return (
        level,
        float(row["x"]).hex(),
        float(row["y"]).hex(),
        float(row["z"]).hex(),
        float(row["Delta"]).hex(),
        float(row["cs"]).hex(),
        float(row["f"]).hex(),
    )


def read_rows(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if (
            reader.fieldnames is None
            or len(reader.fieldnames) != len(set(reader.fieldnames))
            or tuple(reader.fieldnames) != required
        ):
            raise ValueError(f"{path}: expected exact fields {','.join(required)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: no data rows")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{path}: row width does not match exact header")
    return rows


def regular_file(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError(f"{label} must be a nonempty regular non-symlink file")
    return resolved


def load_json(path: Path, label: str) -> dict[str, object]:
    resolved = regular_file(path, label)
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        payload: dict[str, object] = {}
        for key_name, value in pairs:
            if key_name in payload:
                raise ValueError(f"duplicate JSON key: {key_name}")
            payload[key_name] = value
        return payload
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label} JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def read_key_value_metadata(path: Path, label: str) -> dict[str, str]:
    resolved = regular_file(path, label)
    values: dict[str, str] = {}
    for number, line in enumerate(
        resolved.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if "=" not in line:
            raise ValueError(f"{label}: malformed line {number}")
        name, value = line.split("=", 1)
        if not name or name in values:
            raise ValueError(f"{label}: duplicate/empty key at line {number}")
        values[name] = value
    return values


def exact_local_member(
    metadata_path: Path, value: object, expected: Path, label: str,
) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(f"{label} must be a relative producer member")
    member = Path(value)
    if member.name != value or value in {".", ".."}:
        raise ValueError(f"{label} must be a single canonical filename")
    candidate = regular_file(metadata_path.parent / member, label)
    if candidate != regular_file(expected, label):
        raise ValueError(f"{label} does not identify the supplied producer member")
    return candidate


def exact_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def verified_convergence_identity(
    report_path: Path, source: Path, target: Path, checkpoint: Path,
    source_commit: str,
    closure_validator: Callable[[Path], dict[str, object]],
) -> dict[str, object]:
    report = load_json(report_path, "convergence report")
    if (
        report.get("schema") != "internal_nozzle_precursor_convergence_v1"
        or report.get("pass") is not True
        or report.get("classification") != "precursor_converged"
    ):
        raise ValueError("precursor transfer requires a passing convergence report")
    inputs = report.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("convergence report has no verified segment inputs")
    for item in inputs:
        if not isinstance(item, dict):
            raise ValueError("malformed convergence input record")
        for key in ("history", "run_contract"):
            record = item.get(key)
            if not isinstance(record, dict):
                raise ValueError(f"missing convergence {key} provenance")
            path_value, expected_hash = record.get("resolved_path"), record.get("sha256")
            if not isinstance(path_value, str) or not isinstance(expected_hash, str):
                raise ValueError(f"malformed convergence {key} provenance")
            current = regular_file(Path(path_value), f"convergence {key}")
            if sha256(current) != expected_hash:
                raise ValueError(f"convergence {key} changed after classification")
    final = inputs[-1]
    final_history = Path(str(final["history"]["resolved_path"]))
    final_contract_path = Path(str(final["run_contract"]["resolved_path"]))
    final_contract = load_json(final_contract_path, "final precursor run contract")
    if (
        final_contract.get("source_commit") != source_commit
        or final_contract.get("case_id") != report.get("case_id")
    ):
        raise ValueError("convergence/source identity does not match requested transfer")
    source_resolved = regular_file(source, "precursor source table")
    checkpoint_resolved = regular_file(checkpoint, "precursor checkpoint")
    if source_resolved.parent != final_history.parent or checkpoint_resolved.parent != final_history.parent:
        raise ValueError("transfer table and checkpoint must belong to the final converged segment")
    if source_resolved.name != "precursor-target-samples.csv" or checkpoint_resolved.name != "precursor-final.dump":
        raise ValueError("transfer inputs are not the canonical precursor products")
    target_resolved = regular_file(target, "target template")
    contract_template = final_contract.get("target_template")
    if not isinstance(contract_template, str) or contract_template == "not_applicable":
        raise ValueError("final precursor contract has no target-template identity")
    try:
        contract_template_resolved = Path(contract_template).resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError("final precursor target template no longer exists") from error
    if contract_template_resolved != target_resolved:
        raise ValueError("requested target template differs from the converged precursor contract")
    sidecar = Path(str(checkpoint_resolved) + ".meta")
    regular_file(sidecar, "precursor checkpoint sidecar")
    closure = regular_file(
        Path(str(checkpoint_resolved) + ".prediction-closure-v4"),
        "precursor prediction closure",
    )
    metadata = read_key_value_metadata(sidecar, "precursor checkpoint sidecar")
    if (
        metadata.get("schema") != "internal_nozzle_precursor_checkpoint_v2"
        or metadata.get("case_id") != report.get("case_id")
        or not isinstance(metadata.get("geometry_fingerprint"), str)
        or metadata.get("geometry_fingerprint")
        != final_contract.get("geometry_fingerprint")
        or metadata.get("source_commit") != source_commit
        or metadata.get("source_sha256") != final_contract.get("source_sha256")
        or metadata.get("prediction_closure_schema")
        != "internal_nozzle_prediction_closure_v4"
        or metadata.get("prediction_closure_state")
        != "precursor-final.dump.prediction-closure-v4"
    ):
        raise ValueError("precursor checkpoint sidecar does not match convergence identity")
    closure_report = closure_validator(closure)
    expected_closure = {
        "source_sha256": metadata.get("source_sha256"),
        "iteration": int(metadata["i"]),
        "grid_maxdepth": int(metadata["maxlevel"]),
    }
    for key_name, expected_value in expected_closure.items():
        if closure_report.get(key_name) != expected_value:
            raise ValueError(f"precursor closure/sidecar mismatch: {key_name}")
    for key_name, metadata_key in (
        ("checkpoint_t", "t"),
        ("checkpoint_dt", "solver_dt"),
        ("checkpoint_dtmax", "solver_dtmax"),
        ("timestep_previous", "timestep_previous"),
    ):
        if not math.isclose(
            float(closure_report[key_name]),
            float(metadata[metadata_key]),
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError(f"precursor closure/sidecar mismatch: {key_name}")
    try:
        checkpoint_t_star = float(metadata["t_star"])
        converged_t_star = float(report["window"]["end_t_star"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("missing terminal time identity") from error
    if not math.isfinite(checkpoint_t_star) or checkpoint_t_star != converged_t_star:
        raise ValueError("checkpoint terminal time does not match convergence endpoint")
    return {
        "report": report,
        "case_id": report.get("case_id"),
        "geometry_fingerprint": metadata.get("geometry_fingerprint"),
        "source_sha256": metadata.get("source_sha256"),
        "checkpoint_t": float(metadata["t"]),
        "checkpoint_t_star": checkpoint_t_star,
        "report_sha256": sha256(regular_file(report_path, "convergence report")),
        "checkpoint_sha256": sha256(checkpoint_resolved),
        "checkpoint_sidecar_sha256": sha256(sidecar),
        "checkpoint_closure_sha256": sha256(closure),
        "final_history_sha256": sha256(final_history),
        "final_run_contract_sha256": sha256(final_contract_path),
    }


def verified_producer_metadata(
    metadata_path: Path,
    source: Path,
    target: Path,
    checkpoint: Path,
    source_commit: str,
    convergence: dict[str, object],
) -> dict[str, object]:
    resolved_metadata = regular_file(metadata_path, "producer unsealed metadata")
    resolved_source = regular_file(source, "precursor source table")
    if resolved_metadata.parent != resolved_source.parent:
        raise ValueError("producer metadata and sample table must share a directory")
    metadata_sha256 = sha256(resolved_metadata)
    metadata = load_json(resolved_metadata, "producer unsealed metadata")
    expected_scalars = {
        "schema": UNSEALED_SCHEMA,
        "case_id": convergence["case_id"],
        "geometry_fingerprint": convergence["geometry_fingerprint"],
        "source_commit": source_commit,
        "source_sha256": convergence["source_sha256"],
        "target_sampling_method": TARGET_SAMPLING_METHOD,
        "target_exit_clamp_rule": TARGET_CLAMP_RULE,
        "field_state": "post_projection_terminal_native_checkpoint",
    }
    for name, expected in expected_scalars.items():
        if metadata.get(name) != expected:
            raise ValueError(f"producer metadata mismatch: {name}")
    if metadata.get("target_sample_columns") != list(SOURCE_FIELDS):
        raise ValueError("producer metadata mismatch: target_sample_columns")
    exact_local_member(
        resolved_metadata, metadata.get("checkpoint_file"), checkpoint,
        "producer checkpoint",
    )
    exact_local_member(
        resolved_metadata, metadata.get("checkpoint_metadata_file"),
        Path(str(checkpoint) + ".meta"), "producer checkpoint sidecar",
    )
    exact_local_member(
        resolved_metadata, metadata.get("prediction_closure_file"),
        Path(str(checkpoint) + ".prediction-closure-v4"),
        "producer prediction closure",
    )
    exact_local_member(
        resolved_metadata, metadata.get("target_samples_file"), source,
        "producer target samples",
    )
    target_value = metadata.get("target_template")
    if (
        not isinstance(target_value, str)
        or target_value == "not_applicable"
        or not Path(target_value).is_absolute()
    ):
        raise ValueError("producer metadata has no absolute target template")
    if regular_file(Path(target_value), "producer target template") != regular_file(
        target, "target template"
    ):
        raise ValueError("producer target template differs from requested target")
    try:
        outlet = float(metadata["target_exit_coordinate"])
        domain_size = float(metadata["domain_size"])
        checkpoint_t = float(metadata["t"])
        checkpoint_t_star = float(metadata["t_star"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("producer metadata has malformed numeric identity") from error
    if (
        not all(math.isfinite(value) for value in (
            outlet, domain_size, checkpoint_t, checkpoint_t_star,
        ))
        or outlet <= 0.0
        or not math.isclose(outlet, domain_size, rel_tol=0.0, abs_tol=1e-15)
        or not math.isclose(
            checkpoint_t, float(convergence["checkpoint_t"]),
            rel_tol=0.0, abs_tol=1e-15,
        )
        or not math.isclose(
            checkpoint_t_star, float(convergence["checkpoint_t_star"]),
            rel_tol=0.0, abs_tol=1e-15,
        )
    ):
        raise ValueError("producer metadata time/domain identity mismatch")
    sample_count = exact_int(metadata.get("target_sample_count"),
                             "target_sample_count")
    clamp_count = exact_int(metadata.get("target_exit_clamp_count"),
                            "target_exit_clamp_count")
    if sample_count <= 0 or clamp_count < 0 or clamp_count > sample_count:
        raise ValueError("producer metadata has invalid sample/clamp counts")
    if sha256(resolved_metadata) != metadata_sha256:
        raise ValueError("producer metadata changed during sealing")
    return {
        "path": str(resolved_metadata),
        "sha256": metadata_sha256,
        "outlet_x": outlet,
        "sample_count": sample_count,
        "clamp_count": clamp_count,
    }


def validate_sample_provenance(
    rows: list[dict[str, str]], producer: dict[str, object],
) -> None:
    outlet = float(producer["outlet_x"])
    observed_clamps = 0
    for number, row in enumerate(rows, start=2):
        finite(row, ("source_sample_x", "ux", "uy", "uz", "p"),
               f"source row {number}")
        try:
            exit_clamped = int(row["exit_clamped"])
        except (KeyError, ValueError) as error:
            raise ValueError(f"source row {number}: invalid exit_clamped") from error
        if str(exit_clamped) != row["exit_clamped"] or exit_clamped not in (0, 1):
            raise ValueError(f"source row {number}: exit_clamped must be 0 or 1")
        target_x = float(row["x"])
        delta = float(row["Delta"])
        sample_x = float(row["source_sample_x"])
        if exit_clamped:
            observed_clamps += 1
            lower, upper = target_x - 0.5 * delta, target_x + 0.5 * delta
            if (
                target_x < outlet
                or not (lower < outlet and upper > outlet)
                or sample_x.hex() != math.nextafter(outlet, 0.0).hex()
            ):
                raise ValueError(
                    f"source row {number}: invalid outlet-straddle clamp provenance"
                )
        elif target_x >= outlet or sample_x.hex() != target_x.hex():
            raise ValueError(
                f"source row {number}: unclamped sample does not use target center"
            )
    if len(rows) != producer["sample_count"]:
        raise ValueError("producer target sample count does not match table")
    if observed_clamps != producer["clamp_count"]:
        raise ValueError("producer target clamp count does not match table")


def prepare(source: Path, target: Path, output: Path, manifest: Path,
            source_commit: str, checkpoint: Path,
            convergence_report: Path, producer_metadata: Path,
            closure_validator: Callable[[Path], dict[str, object]] = validate_closure_v4,
            ) -> dict[str, object]:
    destinations = (
        output, manifest, output.with_suffix(output.suffix + ".tmp"),
        manifest.with_suffix(manifest.suffix + ".tmp"),
    )
    resolved_destinations = tuple(path.resolve() for path in destinations)
    if len(set(resolved_destinations)) != len(resolved_destinations):
        raise ValueError("transfer output and temporary paths must be distinct")
    for destination in destinations:
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"refusing to overwrite transfer output: {destination}")
    if len(source_commit) != 40 or any(c not in "0123456789abcdefABCDEF" for c in source_commit):
        raise ValueError("source commit must be 40 hexadecimal characters")
    convergence = verified_convergence_identity(
        convergence_report, source, target, checkpoint, source_commit,
        closure_validator,
    )
    producer = verified_producer_metadata(
        producer_metadata, source, target, checkpoint, source_commit,
        convergence,
    )
    source_input_sha256 = sha256(regular_file(source, "precursor source table"))
    target_input_sha256 = sha256(regular_file(target, "target template"))
    source_rows = read_rows(source, SOURCE_FIELDS)
    target_rows = read_rows(target, TARGET_FIELDS)
    validate_sample_provenance(source_rows, producer)
    indexed: dict[tuple[object, ...], dict[str, str]] = {}
    for number, row in enumerate(source_rows, 2):
        finite(row, ("ux", "uy", "uz", "p"), f"source row {number}")
        row_key = key(row, f"source row {number}")
        if row_key in indexed:
            raise ValueError(f"duplicate source target-grid key at row {number}")
        indexed[row_key] = row

    joined: list[dict[str, str]] = []
    seen: set[tuple[object, ...]] = set()
    for number, target_row in enumerate(target_rows, 2):
        row_key = key(target_row, f"target row {number}")
        if row_key in seen:
            raise ValueError(f"duplicate target-grid key at row {number}")
        seen.add(row_key)
        try:
            source_row = indexed[row_key]
        except KeyError as error:
            raise ValueError(f"missing precursor value for target row {number}") from error
        joined.append({name: source_row[name] if name in ("ux", "uy", "uz", "p")
                       else target_row[name] for name in TRANSFER_FIELDS})

    if len(indexed) != len(joined):
        raise ValueError("precursor source contains unused target-grid rows")
    if sha256(source) != source_input_sha256 or sha256(target) != target_input_sha256:
        raise ValueError("transfer input changed during sealing")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=TRANSFER_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(joined)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output)
    payload: dict[str, object] = {
        "schema": "internal_nozzle_exact_target_transfer_v1",
        "method": "exact_target_leaf_join_of_precursor_interpolated_samples",
        "source_field_sampling": (
            TARGET_SAMPLING_METHOD
        ),
        "target_exit_clamp_rule": TARGET_CLAMP_RULE,
        "producer_unsealed_metadata_path": producer["path"],
        "producer_unsealed_metadata_sha256": producer["sha256"],
        "target_exit_coordinate": producer["outlet_x"],
        "target_exit_clamp_count": producer["clamp_count"],
        "additional_interpolation_by_preparer": False,
        "source_commit": source_commit,
        "source_sha256": convergence["source_sha256"],
        "precursor_checkpoint_sha256": convergence["checkpoint_sha256"],
        "precursor_checkpoint_sidecar_sha256": convergence["checkpoint_sidecar_sha256"],
        "precursor_checkpoint_closure_sha256": convergence["checkpoint_closure_sha256"],
        "precursor_convergence_report_sha256": convergence["report_sha256"],
        "precursor_convergence_classification": "precursor_converged",
        "final_history_sha256": convergence["final_history_sha256"],
        "final_run_contract_sha256": convergence["final_run_contract_sha256"],
        "source_table_sha256": source_input_sha256,
        "target_template_sha256": target_input_sha256,
        "transfer_table_sha256": sha256(output),
        "target_leaf_count": len(target_rows),
        "loaded_leaf_count": len(joined),
        "coverage_fraction": 1.0,
        "unused_source_rows": len(source_rows) - len(joined),
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest = manifest.with_suffix(manifest.suffix + ".tmp")
    with temporary_manifest.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_manifest, manifest)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--precursor-source", type=Path, required=True)
    parser.add_argument("--target-template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--precursor-checkpoint", type=Path, required=True)
    parser.add_argument("--convergence-report", type=Path, required=True)
    parser.add_argument("--producer-metadata", type=Path, required=True)
    args = parser.parse_args()
    payload = prepare(args.precursor_source, args.target_template, args.output,
                      args.manifest, args.source_commit, args.precursor_checkpoint,
                      args.convergence_report, args.producer_metadata)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
