import csv
import importlib.util
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_internal_nozzle_precursor_transfer.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("prepare_transfer", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write(path: Path, fields: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def closure_report(_path: Path) -> dict[str, object]:
    return {
        "source_sha256": "c" * 64,
        "iteration": 400,
        "grid_maxdepth": 7,
        "checkpoint_t": 0.557028505473556,
        "checkpoint_dt": 0.001,
        "checkpoint_dtmax": 0.001,
        "timestep_previous": 0.001,
    }


def convergence_fixture(
    tmp_path: Path, source: Path, target: Path
) -> tuple[Path, Path, Path]:
    checkpoint = tmp_path / "precursor-final.dump"
    checkpoint.write_bytes(b"native checkpoint")
    history = tmp_path / "precursor_history.csv"
    history.write_text("terminal history\n", encoding="utf-8")
    contract = tmp_path / "run_contract.json"
    contract.write_text(json.dumps({
        "source_commit": "a" * 40,
        "source_sha256": "c" * 64,
        "case_id": "precursor_w2",
        "geometry_fingerprint": "w2-geometry",
        "target_template": str(target.resolve()),
    }), encoding="utf-8")
    Path(str(checkpoint) + ".prediction-closure-v4").write_bytes(b"closure")
    Path(str(checkpoint) + ".meta").write_text(
        "schema=internal_nozzle_precursor_checkpoint_v2\n"
        "case_id=precursor_w2\n"
        "geometry_fingerprint=w2-geometry\n"
        f"source_commit={'a' * 40}\n"
        f"source_sha256={'c' * 64}\n"
        "maxlevel=7\n"
        "t=0.557028505473556\n"
        "t_star=4\n"
        "i=400\n"
        "solver_dt=0.001\n"
        "solver_dtmax=0.001\n"
        "timestep_previous=0.001\n"
        "prediction_closure_schema=internal_nozzle_prediction_closure_v4\n"
        "prediction_closure_state=precursor-final.dump.prediction-closure-v4\n",
        encoding="utf-8",
    )
    report = tmp_path / "convergence.json"
    report.write_text(json.dumps({
        "schema": "internal_nozzle_precursor_convergence_v1",
        "classification": "precursor_converged",
        "pass": True,
        "case_id": "precursor_w2",
        "window": {"end_t_star": 4.0},
        "inputs": [{
            "history": {"resolved_path": str(history.resolve()), "sha256": digest(history)},
            "run_contract": {"resolved_path": str(contract.resolve()), "sha256": digest(contract)},
        }],
    }), encoding="utf-8")
    with source.open(newline="", encoding="utf-8") as stream:
        source_rows = list(csv.DictReader(stream))
    producer = tmp_path / "precursor-transfer-unsealed.json"
    producer.write_text(json.dumps({
        "schema": MODULE.UNSEALED_SCHEMA,
        "case_id": "precursor_w2",
        "geometry_fingerprint": "w2-geometry",
        "source_commit": "a" * 40,
        "source_sha256": "c" * 64,
        "checkpoint_file": "precursor-final.dump",
        "checkpoint_metadata_file": "precursor-final.dump.meta",
        "prediction_closure_file": "precursor-final.dump.prediction-closure-v4",
        "target_template": str(target.resolve()),
        "target_samples_file": "precursor-target-samples.csv",
        "target_sampling_method": MODULE.TARGET_SAMPLING_METHOD,
        "target_sample_columns": list(MODULE.SOURCE_FIELDS),
        "target_exit_clamp_rule": MODULE.TARGET_CLAMP_RULE,
        "target_exit_coordinate": 1.0,
        "target_sample_count": len(source_rows),
        "target_exit_clamp_count": sum(
            row.get("exit_clamped") == "1" for row in source_rows
        ),
        "domain_size": 1.0,
        "t": 0.557028505473556,
        "t_star": 4.0,
        "field_state": "post_projection_terminal_native_checkpoint",
    }), encoding="utf-8")
    return checkpoint, report, producer


def test_exact_join_and_manifest(tmp_path: Path):
    target = tmp_path / "target.csv"
    source = tmp_path / "precursor-target-samples.csv"
    output = tmp_path / "transfer.csv"
    manifest = tmp_path / "manifest.json"
    write(target, MODULE.TARGET_FIELDS, [(0.5, 0.25, 0.25, 2, 0.25, 1, 1), (0.75, 0.25, 0.25, 2, 0.25, 1, 1)])
    write(source, MODULE.SOURCE_FIELDS, [
        (0.75, 0.25, 0.25, 2, 0.25, 1, 1, 0.75, 0, 2, 0, 0, 8),
        (0.5, 0.25, 0.25, 2, 0.25, 1, 1, 0.5, 0, 1, 0, 0, 9),
    ])
    checkpoint, report, producer = convergence_fixture(tmp_path, source, target)
    payload = MODULE.prepare(
        source, target, output, manifest, "a" * 40, checkpoint, report,
        producer, closure_report,
    )
    assert payload["coverage_fraction"] == 1.0
    assert payload["producer_unsealed_metadata_sha256"] == digest(producer)
    assert payload["target_exit_clamp_count"] == 0
    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["ux"] for row in rows] == ["1", "2"]
    assert len(payload["transfer_table_sha256"]) == 64


def test_missing_and_duplicate_rows_fail_closed(tmp_path: Path):
    target = tmp_path / "target.csv"
    source = tmp_path / "precursor-target-samples.csv"
    write(target, MODULE.TARGET_FIELDS, [(0.5, 0.25, 0.25, 2, 0.25, 1, 1)])
    write(source, MODULE.SOURCE_FIELDS, [
        (0.75, 0.25, 0.25, 2, 0.25, 1, 1, 0.75, 0, 2, 0, 0, 8),
        (0.75, 0.25, 0.25, 2, 0.25, 1, 1, 0.75, 0, 2, 0, 0, 8),
    ])
    checkpoint, report, producer = convergence_fixture(tmp_path, source, target)
    try:
        MODULE.prepare(
            source, target, tmp_path / "o.csv", tmp_path / "m.json",
            "a" * 40, checkpoint, report, producer, closure_report,
        )
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate source key accepted")


def test_unconverged_or_stale_evidence_fails_closed(tmp_path: Path):
    target = tmp_path / "target.csv"
    source = tmp_path / "precursor-target-samples.csv"
    write(target, MODULE.TARGET_FIELDS, [(0.5, 0.25, 0.25, 2, 0.25, 1, 1)])
    write(source, MODULE.SOURCE_FIELDS, [
        (0.5, 0.25, 0.25, 2, 0.25, 1, 1, 0.5, 0, 1, 0, 0, 9),
    ])
    checkpoint, report, producer = convergence_fixture(tmp_path, source, target)
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["pass"] = False
    payload["classification"] = "not_converged"
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="passing convergence"):
        MODULE.prepare(
            source, target, tmp_path / "o.csv", tmp_path / "m.json",
            "a" * 40, checkpoint, report, producer, closure_report,
        )

    checkpoint, report, producer = convergence_fixture(tmp_path, source, target)
    (tmp_path / "precursor_history.csv").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after classification"):
        MODULE.prepare(
            source, target, tmp_path / "o2.csv", tmp_path / "m2.json",
            "a" * 40, checkpoint, report, producer, closure_report,
        )


def test_clamp_requires_straddling_leaf_and_exact_producer_metadata(tmp_path: Path):
    target = tmp_path / "target.csv"
    source = tmp_path / "precursor-target-samples.csv"
    write(target, MODULE.TARGET_FIELDS, [(1.2, 0, 0, 3, 0.1, 1, 0.5)])
    write(source, MODULE.SOURCE_FIELDS, [
        (1.2, 0, 0, 3, 0.1, 1, 0.5, math.nextafter(1.0, 0.0), 1,
         2, 0, 0, 0),
    ])
    checkpoint, report, producer = convergence_fixture(tmp_path, source, target)
    with pytest.raises(ValueError, match="outlet-straddle"):
        MODULE.prepare(
            source, target, tmp_path / "o.csv", tmp_path / "m.json",
            "a" * 40, checkpoint, report, producer, closure_report,
        )

    target.unlink()
    source.unlink()
    producer.unlink()
    write(target, MODULE.TARGET_FIELDS, [(1.0, 0, 0, 3, 0.1, 1, 0.5)])
    write(source, MODULE.SOURCE_FIELDS, [
        (1.0, 0, 0, 3, 0.1, 1, 0.5, math.nextafter(1.0, 0.0), 1,
         2, 0, 0, 0),
    ])
    checkpoint, report, producer = convergence_fixture(tmp_path, source, target)
    metadata = json.loads(producer.read_text(encoding="utf-8"))
    metadata["target_sampling_method"] = "unverified"
    producer.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="target_sampling_method"):
        MODULE.prepare(
            source, target, tmp_path / "o2.csv", tmp_path / "m2.json",
            "a" * 40, checkpoint, report, producer, closure_report,
        )


def test_exact_outlet_center_clamp_is_accepted_and_stripped_from_transfer(tmp_path: Path):
    target = tmp_path / "target.csv"
    source = tmp_path / "precursor-target-samples.csv"
    output = tmp_path / "transfer.csv"
    write(target, MODULE.TARGET_FIELDS, [(1.0, 0, 0, 3, 0.1, 1, 0.5)])
    write(source, MODULE.SOURCE_FIELDS, [
        (1.0, 0, 0, 3, 0.1, 1, 0.5, math.nextafter(1.0, 0.0), 1,
         2, 0, 0, 0),
    ])
    checkpoint, report, producer = convergence_fixture(tmp_path, source, target)
    payload = MODULE.prepare(
        source, target, output, tmp_path / "manifest.json", "a" * 40,
        checkpoint, report, producer, closure_report,
    )
    assert payload["target_exit_clamp_count"] == 1
    with output.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        assert tuple(reader.fieldnames or ()) == MODULE.TRANSFER_FIELDS
        assert len(list(reader)) == 1


def test_exact_headers_and_exporter_contract(tmp_path: Path):
    target = tmp_path / "target.csv"
    source = tmp_path / "precursor-target-samples.csv"
    write(target, MODULE.TARGET_FIELDS + ("unexpected",), [
        (0.5, 0, 0, 2, 0.25, 1, 1, "x"),
    ])
    with pytest.raises(ValueError, match="expected exact fields"):
        MODULE.read_rows(target, MODULE.TARGET_FIELDS)

    target.write_text(
        ",".join(MODULE.TARGET_FIELDS) + "\n0.5,0,0,2,0.25,1,1,extra\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="row width"):
        MODULE.read_rows(target, MODULE.TARGET_FIELDS)

    exporter = (
        Path(__file__).resolve().parents[1] / "cases" / "basilisk" /
        "rectangular_internal_nozzle_steady_precursor.c"
    ).read_text(encoding="utf-8")
    assert "source_sample_x,exit_clamped" in exporter
    assert "does not straddle outlet" in exporter
    assert "INTERNAL_NOZZLE_TARGET_CLAMP_RULE" in exporter


def test_duplicate_producer_metadata_key_fails_closed(tmp_path: Path):
    target = tmp_path / "target.csv"
    source = tmp_path / "precursor-target-samples.csv"
    write(target, MODULE.TARGET_FIELDS, [(0.5, 0, 0, 2, 0.25, 1, 1)])
    write(source, MODULE.SOURCE_FIELDS, [
        (0.5, 0, 0, 2, 0.25, 1, 1, 0.5, 0, 1, 0, 0, 9),
    ])
    checkpoint, report, producer = convergence_fixture(tmp_path, source, target)
    text = producer.read_text(encoding="utf-8")
    producer.write_text(
        text.replace('"schema":', '"schema": "duplicate", "schema":', 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid producer unsealed metadata JSON"):
        MODULE.prepare(
            source, target, tmp_path / "o.csv", tmp_path / "m.json",
            "a" * 40, checkpoint, report, producer, closure_report,
        )
