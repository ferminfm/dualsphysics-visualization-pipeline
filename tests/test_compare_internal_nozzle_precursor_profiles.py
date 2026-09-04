import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "compare_internal_nozzle_precursor_profiles.py"
)
SPEC = importlib.util.spec_from_file_location("precursor_profile_comparison", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

REFERENCE = Path(
    os.environ.get(
        "POISEUILLE_REFERENCE_SCRIPT",
        str(Path(__file__).resolve().parents[1] / "scripts" / "rectangular_poiseuille_reference.py"),
    )
)
SOURCE_COMMIT = "a" * 40
SOURCE_SHA256 = "b" * 64


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, fields, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def rewrite_csv(path: Path, mutate) -> None:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    mutate(rows)
    write_csv(path, fields, rows)


def file_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "resolved_path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def make_fixture(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "terminal-segment"
    root.mkdir()
    reference = MODULE.load_reference(REFERENCE.resolve())
    area0 = math.pi * (1.0 / 12.0) ** 2
    width0 = math.sqrt(2.0 * area0)
    height0 = 0.5 * width0
    hydraulic_diameter = 2.0 * width0 * height0 / (width0 + height0)
    domain_size = 15.0 * hydraulic_diameter
    t_value = 2.0
    t_star = t_value / hydraulic_diameter
    iteration = 42
    cells = []
    plane_history = []
    source_cell_id = 0
    for label, plane_dh in MODULE.PLANES:
        width, height = MODULE.local_dimensions(plane_dh, hydraulic_diameter)
        delta = height / 4.0
        flow = 0.0
        second = 0.0
        third = 0.0
        for iy in range(8):
            y0 = -0.5 * width + iy * delta
            y1 = y0 + delta
            for iz in range(4):
                z0 = -0.5 * height + iz * delta
                z1 = z0 + delta
                cell = MODULE.Cell(
                    source_cell_id, plane_dh * hydraulic_diameter,
                    0.5 * (y0 + y1), 0.5 * (z0 + z1), delta, 1.0,
                    0.0, 0.0, 0.0, 10.0,
                )
                rectangle = MODULE.Rectangle(cell, y0, y1, z0, z1, delta * delta)
                ux = 3.0 * MODULE.reference_cell_average(
                    reference, rectangle, width=width, height=height, modes=64, order=8,
                )
                cells.append({
                    "source_cell_id": source_cell_id,
                    "x": f"{cell.x:.17g}",
                    "y": f"{cell.y:.17g}",
                    "z": f"{cell.z:.17g}",
                    "Delta": f"{delta:.17g}",
                    "cs": "1",
                    "ux": f"{ux:.17g}",
                    "uy": "0",
                    "uz": "0",
                    "p": "10",
                })
                flow += delta * delta * ux
                second += delta * delta * ux * ux
                third += delta * delta * ux * ux * ux
                source_cell_id += 1
        area = width * height
        plane_history.append({
            "case_id": "steady_precursor_w2",
            "t": f"{t_value:.17g}",
            "t_star": f"{t_star:.17g}",
            "i": str(iteration),
            "plane_label": label,
            "plane_dh": f"{plane_dh:.17g}",
            "area": f"{area:.17g}",
            "Q_l": f"{flow:.17g}",
            "mdot_l": f"{flow:.17g}",
            "J_k": f"{second:.17g}",
            "pressure_mean": "10",
            "beta": f"{second * area / (flow * flow):.17g}",
            "alpha": f"{third * area * area / (flow * flow * flow):.17g}",
        })
    cells_path = root / "precursor-transfer-cells.csv"
    write_csv(cells_path, MODULE.CELL_FIELDS, cells)
    plane_path = root / "precursor_plane_history.csv"
    write_csv(plane_path, MODULE.PLANE_HISTORY_FIELDS, plane_history)
    history = root / "precursor_history.csv"
    history.write_text("case_id,t,t_star\nsteady_precursor_w2,2,1.5\n", encoding="utf-8")
    sidecar = root / "precursor-final.dump.meta"
    checkpoint = root / "precursor-final.dump"
    checkpoint.write_bytes(b"native-checkpoint-fixture")
    closure = root / "precursor-final.dump.prediction-closure-v4"
    closure.write_bytes(b"prediction-closure-fixture")
    sidecar.write_text(
        "schema=internal_nozzle_precursor_checkpoint_v2\n"
        "case_id=steady_precursor_w2\n"
        f"geometry_fingerprint={MODULE.GEOMETRY_FINGERPRINT}\n"
        f"source_commit={SOURCE_COMMIT}\n"
        f"source_sha256={SOURCE_SHA256}\n"
        "maxlevel=7\n"
        "pressure_forcing=351.48\n"
        "density_liquid=1\n"
        "viscosity_liquid=1\n"
        f"t={t_value:.17g}\n"
        f"t_star={t_star:.17g}\n"
        f"i={iteration}\n"
        "solver_dt=0.001\n"
        "solver_dtmax=0.001\n"
        "timestep_previous=0.001\n"
        "previous_profile_available=1\n"
        "prediction_closure_schema=internal_nozzle_prediction_closure_v4\n"
        "prediction_closure_state=precursor-final.dump.prediction-closure-v4\n",
        encoding="utf-8",
    )
    run_contract = root / "run_contract.json"
    delta_min_dh = MODULE.INTERNAL_LENGTH_DH / (1 << 7)
    run_contract.write_text(json.dumps({
        "schema": MODULE.RUN_SCHEMA,
        "case_id": "steady_precursor_w2",
        "geometry_fingerprint": MODULE.GEOMETRY_FINGERPRINT,
        "source_commit": SOURCE_COMMIT,
        "source_sha256": SOURCE_SHA256,
        "pressure_forcing": 351.48,
        "density_liquid": 1.0,
        "viscosity_liquid": 1.0,
        "maxlevel": 7,
        "delta_min_Dh": delta_min_dh,
    }, sort_keys=True) + "\n", encoding="utf-8")
    producer = root / "precursor-transfer-unsealed.json"
    producer.write_text(json.dumps({
        "schema": MODULE.PRODUCER_SCHEMA,
        "case_id": "steady_precursor_w2",
        "geometry_fingerprint": MODULE.GEOMETRY_FINGERPRINT,
        "source_commit": SOURCE_COMMIT,
        "source_sha256": SOURCE_SHA256,
        "checkpoint_file": checkpoint.name,
        "checkpoint_metadata_file": sidecar.name,
        "prediction_closure_file": closure.name,
        "cells_file": cells_path.name,
        "history_file": history.name,
        "cell_count": len(cells),
        "domain_size": domain_size,
        "maxlevel": 7,
        "delta_min_Dh": delta_min_dh,
        "pressure_forcing": 351.48,
        "density_liquid": 1.0,
        "viscosity_liquid": 1.0,
        "t": t_value,
        "t_star": t_star,
        "field_state": "post_projection_terminal_native_checkpoint",
    }, sort_keys=True) + "\n", encoding="utf-8")
    convergence = tmp_path / "precursor-convergence.json"
    convergence.write_text(json.dumps({
        "schema": MODULE.CONVERGENCE_SCHEMA,
        "classification": "precursor_converged",
        "pass": True,
        "case_id": "steady_precursor_w2",
        "window": {"end_t_star": t_star},
        "failures": [],
        "metrics": {
            name: {"pass": True} for name in ("Q_l", "J_k", "pressure_drop")
        },
        "auxiliary": {"tests": {"all_declared_checks": True}},
        "inputs": [{
            "history": file_record(history),
            "run_contract": file_record(run_contract),
            "terminal_checkpoint": {
                "dump": file_record(checkpoint),
                "metadata": file_record(sidecar),
                "prediction_closure": file_record(closure),
                "validated_identity": {
                    "case_id": "steady_precursor_w2",
                    "source_commit": SOURCE_COMMIT,
                    "source_sha256": SOURCE_SHA256,
                    "t": t_value,
                    "t_star": t_star,
                    "i": iteration,
                    "schedule_version": MODULE.SCHEDULE_VERSION,
                    "schedule_sha256": MODULE.SCHEDULE_SHA256,
                },
            },
        }],
    }, sort_keys=True) + "\n", encoding="utf-8")
    metrics = reference.reference_metrics(
        width=2.0, height=1.0, pressure_gradient=1.0, viscosity=1.0,
        modes=64, quadrature_order=64,
    )
    selected_series = {
        "modes": 64,
        "flow_rate": metrics["flow_rate"],
        "beta": metrics["beta"],
        "alpha": metrics["alpha"],
        "centerline_to_bulk": metrics["centerline_to_bulk"],
    }
    reference_report = tmp_path / "reference.json"
    reference_report.write_text(json.dumps({
        "schema": MODULE.REFERENCE_SCHEMA,
        "equation": "mu*(d2u_dy2+d2u_dz2)=dp_dx; pressure_gradient=-dp_dx>0",
        "boundary_condition": "no_slip_all_four_walls",
        "normalization": "width=2,height=1,pressure_gradient=1,viscosity=1",
        "metrics": metrics,
        "series_convergence": [selected_series],
        "independent_five_point_poisson": [
            reference.finite_difference_metrics(8),
            reference.finite_difference_metrics(16),
        ],
        "claim_boundary": "mathematical_and_numerical_reference_not_physical_validation",
    }, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "root": root,
        "producer": producer,
        "convergence": convergence,
        "cells": cells_path,
        "plane_history": plane_path,
        "reference": REFERENCE.resolve(),
        "reference_report": reference_report,
    }


def kwargs(fixture: dict[str, object]) -> dict[str, object]:
    return {
        "producer_metadata": fixture["producer"],
        "convergence_report": fixture["convergence"],
        "plane_history": fixture["plane_history"],
        "reference_script": fixture["reference"],
        "reference_report": fixture["reference_report"],
        "expected_source_commit": SOURCE_COMMIT,
        "expected_source_sha256": SOURCE_SHA256,
        "expected_producer_sha256": sha256(fixture["producer"]),
        "expected_cells_sha256": sha256(fixture["cells"]),
        "expected_plane_history_sha256": sha256(fixture["plane_history"]),
        "expected_convergence_sha256": sha256(fixture["convergence"]),
        "expected_reference_sha256": sha256(fixture["reference"]),
        "expected_reference_report_sha256": sha256(fixture["reference_report"]),
        "modes": 64,
        "reference_quadrature_order": 64,
        "cell_quadrature_order": 8,
    }


def test_exact_profile_passes_integrity_and_emits_classification_inputs(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    payload, samples = MODULE.analyze(**kwargs(fixture))
    assert payload["schema"] == MODULE.SCHEMA
    assert payload["checks"] == {
        "converged_terminal_state_bound": True,
        "input_hashes_stable": True,
        "all_declared_planes_present": True,
        "leaf_partitions_close": True,
        "plane_history_metric_identities": True,
        "checkpoint_and_convergence_lineage_bound": True,
        "source_bundle_identity_bound": True,
        "task02_reference_artifact_bound": True,
        "reference_no_slip": True,
        "numerical_wall_adjacent_coverage": True,
    }
    assert len(payload["planes"]) == 5
    assert len(samples) == 160
    for plane in payload["planes"]:
        assert plane["profile_comparison"]["bulk_normalized_weighted_l2"] < 2e-7
        assert max(plane["numerical"]["terminal_history_identity_errors"].values()) < 2e-11
        assert plane["exact_reference"]["wall_velocity_max_abs"] == 0.0
        assert plane["symmetry"]["y"]["normalized_weighted_l2"] < 1e-7
    output = tmp_path / "comparison-output"
    MODULE.write_outputs(output, payload, samples)
    assert (output / "precursor-poiseuille-profile-comparison.json").stat().st_size > 0
    assert (output / "precursor-poiseuille-profile-samples.csv").stat().st_size > 0


def test_expected_hash_is_mandatory_and_fail_closed(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    arguments = kwargs(fixture)
    arguments["expected_cells_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="cell export SHA-256 mismatch"):
        MODULE.analyze(**arguments)


def test_source_bundle_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    producer = json.loads(fixture["producer"].read_text(encoding="utf-8"))
    producer["source_sha256"] = "c" * 64
    fixture["producer"].write_text(json.dumps(producer, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="producer metadata mismatch: source_sha256"):
        MODULE.analyze(**kwargs(fixture))


def test_checkpoint_sidecar_requires_complete_bound_identity(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    sidecar = fixture["root"] / "precursor-final.dump.meta"
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace(
            f"source_sha256={SOURCE_SHA256}\n", ""
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="incompatible exact key set"):
        MODULE.analyze(**kwargs(fixture))


def test_plane_history_wrong_case_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    rewrite_csv(
        fixture["plane_history"],
        lambda rows: [row.__setitem__("case_id", "other_case") for row in rows],
    )
    with pytest.raises(ValueError, match="wrong case_id"):
        MODULE.analyze(**kwargs(fixture))


@pytest.mark.parametrize("field", ["mdot_l", "J_k", "pressure_mean", "beta", "alpha"])
def test_every_terminal_plane_metric_identity_is_enforced(
    tmp_path: Path, field: str,
) -> None:
    fixture = make_fixture(tmp_path)
    def alter(rows):
        rows[-1][field] = str(float(rows[-1][field]) + 1.0)
    rewrite_csv(fixture["plane_history"], alter)
    with pytest.raises(ValueError, match=rf"reconstructed {field} mismatch"):
        MODULE.analyze(**kwargs(fixture))


def test_convergence_terminal_checkpoint_provenance_is_required(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    report = json.loads(fixture["convergence"].read_text(encoding="utf-8"))
    del report["inputs"][-1]["terminal_checkpoint"]
    fixture["convergence"].write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="lacks terminal-checkpoint provenance"):
        MODULE.analyze(**kwargs(fixture))


def test_reference_artifact_settings_are_hash_bound_and_recomputed(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    report = json.loads(fixture["reference_report"].read_text(encoding="utf-8"))
    report["metrics"]["modes"] = 32
    fixture["reference_report"].write_text(
        json.dumps(report, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="reference setting modes mismatch"):
        MODULE.analyze(**kwargs(fixture))


def test_missing_leaf_is_rejected_by_partition_closure(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    rewrite_csv(fixture["cells"], lambda rows: rows.pop())
    producer = json.loads(fixture["producer"].read_text(encoding="utf-8"))
    producer["cell_count"] -= 1
    fixture["producer"].write_text(json.dumps(producer, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not tile aperture"):
        MODULE.analyze(**kwargs(fixture))


def test_duplicate_leaf_geometry_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    def duplicate(rows):
        row = dict(rows[0])
        row["source_cell_id"] = str(len(rows))
        rows.append(row)
    rewrite_csv(fixture["cells"], duplicate)
    producer = json.loads(fixture["producer"].read_text(encoding="utf-8"))
    producer["cell_count"] += 1
    fixture["producer"].write_text(json.dumps(producer, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicates a leaf geometry"):
        MODULE.analyze(**kwargs(fixture))


def test_terminal_plane_flow_mismatch_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    def alter(rows):
        rows[-1]["Q_l"] = str(float(rows[-1]["Q_l"]) * 1.01)
    rewrite_csv(fixture["plane_history"], alter)
    with pytest.raises(ValueError, match="reconstructed Q_l mismatch"):
        MODULE.analyze(**kwargs(fixture))


@pytest.mark.parametrize("classification,passed", [("not_converged", False), ("precursor_converged", False)])
def test_nonpassing_convergence_is_rejected(
    tmp_path: Path, classification: str, passed: bool,
) -> None:
    fixture = make_fixture(tmp_path)
    report = json.loads(fixture["convergence"].read_text(encoding="utf-8"))
    report["classification"] = classification
    report["pass"] = passed
    fixture["convergence"].write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="internally consistent passing"):
        MODULE.analyze(**kwargs(fixture))


def test_reference_symlink_is_rejected_even_with_matching_hash(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    link = tmp_path / "reference-link.py"
    link.symlink_to(fixture["reference"])
    arguments = kwargs(fixture)
    arguments["reference_script"] = link
    arguments["expected_reference_sha256"] = sha256(fixture["reference"])
    with pytest.raises(ValueError, match="must not be a symlink"):
        MODULE.analyze(**arguments)


def test_asymmetry_is_reported_without_assigning_scientific_class(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    increment = 0.2
    target_id = 128
    changed_area = None
    old_velocity = None
    def alter_cells(rows):
        nonlocal changed_area, old_velocity
        row = next(item for item in rows if int(item["source_cell_id"]) == target_id)
        old_velocity = float(row["ux"])
        row["ux"] = str(old_velocity + increment)
        changed_area = float(row["Delta"]) ** 2
    rewrite_csv(fixture["cells"], alter_cells)
    assert changed_area is not None
    assert old_velocity is not None
    def alter_history(rows):
        row = next(item for item in rows if item["plane_label"] == "near_exit")
        area = float(row["area"])
        old_flow = float(row["Q_l"])
        old_second = float(row["J_k"])
        old_third = float(row["alpha"]) * old_flow**3 / area**2
        new_velocity = old_velocity + increment
        new_flow = old_flow + increment * changed_area
        new_second = old_second + (new_velocity**2 - old_velocity**2) * changed_area
        new_third = old_third + (new_velocity**3 - old_velocity**3) * changed_area
        row["Q_l"] = row["mdot_l"] = f"{new_flow:.17g}"
        row["J_k"] = f"{new_second:.17g}"
        row["beta"] = f"{new_second * area / new_flow**2:.17g}"
        row["alpha"] = f"{new_third * area**2 / new_flow**3:.17g}"
    rewrite_csv(fixture["plane_history"], alter_history)
    payload, _ = MODULE.analyze(**kwargs(fixture))
    near_exit = next(item for item in payload["planes"] if item["plane_label"] == "near_exit")
    assert near_exit["symmetry"]["y"]["normalized_weighted_l2"] > 0.0
    assert payload["classification_inputs"]["scientific_classification"] == "not_assigned_by_reducer"


def test_output_directory_is_write_once(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    payload, samples = MODULE.analyze(**kwargs(fixture))
    output = tmp_path / "comparison-output"
    MODULE.write_outputs(output, payload, samples)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        MODULE.write_outputs(output, payload, samples)
