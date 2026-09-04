import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_internal_nozzle_acceptance.py"
SPEC = importlib.util.spec_from_file_location("projection_acceptance", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_criteria(root: Path) -> tuple[Path, str]:
    velocity = 0.1427080945921512
    scales = {
        "divergence_l2": velocity / MODULE.PROJECTION_LENGTH_SCALE,
        "divergence_max": velocity / MODULE.PROJECTION_LENGTH_SCALE,
        "velocity_impulse_l2": velocity,
        "cell_pressure_change_l2": MODULE.PROJECTION_PRESSURE_SCALE,
        "projection_pressure_adjustment_l2": MODULE.PROJECTION_PRESSURE_SCALE,
    }
    path = root / "criteria.json"
    path.write_text(json.dumps({
        "schema": MODULE.PROJECTION_CRITERIA_SCHEMA,
        "criteria_id": "task04-projection-v2-test",
        "applicable_case_roles": ["B", "C"],
        "phase_selection": MODULE.PROJECTION_SELECTION,
        "divergence_convention": MODULE.PROJECTION_DIVERGENCE,
        "normalization": {
            "length_scale": MODULE.PROJECTION_LENGTH_SCALE,
            "velocity_scale": velocity,
            "pressure_scale": MODULE.PROJECTION_PRESSURE_SCALE,
        },
        "metrics": {
            metric: {
                "aggregation": "selected_named_record",
                "operator": "<=",
                "limit": MODULE.PROJECTION_NORMALIZED_LIMITS[metric] * scale,
            }
            for metric, scale in scales.items()
        },
        "claim_boundary": "test-only immutable projection criteria",
    }, sort_keys=True), encoding="utf-8")
    return path, digest(path)


def make_evidence(root: Path) -> Path:
    path = root / "projection.csv"
    common = {
        "case_id": "case-b", "initial_state": "precursor_start",
        "inlet_mode": "pressure_driven", "precursor_pressure_mode": "transferred",
        "transfer_sha256": "a" * 64, "execution_id": "exec-b",
        "segment_id": "segment-b", "case_role": "B", "fluid_volume": "1",
    }
    rows = []
    for index, phase in enumerate(MODULE.PROJECTION_PHASES):
        row = {
            **common, "record_index": str(index), "phase": phase,
            "t": "0" if index < 3 else "0.001", "i": "0" if index < 3 else "1",
            "divergence_l2": "99" if index == 0 else "0",
            "divergence_max": "99" if index == 0 else "0",
            "velocity_impulse_l2": "0", "cell_pressure_change_l2": "0",
            "projection_pressure_adjustment_l2": "0",
        }
        for key in MODULE.PROJECTION_STATS:
            row[key] = "not_applicable"
        if index == MODULE.PROJECTION_SELECTED_INDEX:
            row.update({
                "projection_iterations": "4", "projection_residual_before": "1",
                "projection_residual_after": "0.001", "projection_nrelax": "2",
                "projection_nitermin_before": "2", "projection_nitermin_during": "4",
                "projection_nitermin_after": "2", "projection_nitermax": "100",
            })
        rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MODULE.PROJECTION_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_raw_unprojected_context_is_not_an_acceptance_input(tmp_path: Path) -> None:
    criteria, criteria_sha = make_criteria(tmp_path)
    criteria_path, payload = MODULE.load_projection_criteria(criteria, criteria_sha)
    evidence = make_evidence(tmp_path)
    _, identity, observed = MODULE.projection_measurements(evidence)
    result = MODULE.expected_projection_acceptance(
        criteria_path, criteria_sha, payload, evidence, identity, observed,
    )
    assert result["pass"] is True
    assert result["selected_record_indices"] == [1]
    assert result["context_record_indices"] == [0, 2, 3]
    assert all(predicate["observed"] == 0 for predicate in result["predicates"])


def test_selected_projection_metric_above_fixed_limit_fails(tmp_path: Path) -> None:
    criteria, criteria_sha = make_criteria(tmp_path)
    criteria_path, payload = MODULE.load_projection_criteria(criteria, criteria_sha)
    evidence = make_evidence(tmp_path)
    rows = list(csv.DictReader(evidence.open(newline="", encoding="utf-8")))
    rows[1]["divergence_max"] = "1"
    with evidence.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MODULE.PROJECTION_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    _, identity, observed = MODULE.projection_measurements(evidence)
    result = MODULE.expected_projection_acceptance(
        criteria_path, criteria_sha, payload, evidence, identity, observed,
    )
    assert result["pass"] is False


@pytest.mark.parametrize("value", ["3", "5", "true", "not_applicable"])
def test_selected_projection_solver_stats_fail_closed(tmp_path: Path, value: str) -> None:
    evidence = make_evidence(tmp_path)
    rows = list(csv.DictReader(evidence.open(newline="", encoding="utf-8")))
    rows[1]["projection_nitermin_during"] = value
    with evidence.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MODULE.PROJECTION_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="projection"):
        MODULE.projection_measurements(evidence)


def test_context_record_cannot_carry_solver_stats(tmp_path: Path) -> None:
    evidence = make_evidence(tmp_path)
    rows = list(csv.DictReader(evidence.open(newline="", encoding="utf-8")))
    rows[0]["projection_iterations"] = "4"
    with evidence.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MODULE.PROJECTION_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="context record"):
        MODULE.projection_measurements(evidence)


def test_stale_selection_and_changed_limit_fail_closed(tmp_path: Path) -> None:
    criteria, _ = make_criteria(tmp_path)
    payload = json.loads(criteria.read_text(encoding="utf-8"))
    payload["phase_selection"] = "records_0_and_1_immediate_transfer_projection_only"
    criteria.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="semantic mismatch"):
        MODULE.load_projection_criteria(criteria, digest(criteria))
    payload["phase_selection"] = MODULE.PROJECTION_SELECTION
    payload["metrics"]["divergence_l2"]["limit"] *= 2
    criteria.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="fixed normalized limit"):
        MODULE.load_projection_criteria(criteria, digest(criteria))
