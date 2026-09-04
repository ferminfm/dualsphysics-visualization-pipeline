import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "analyze_internal_nozzle_precursor_convergence.py"
)
SPEC = importlib.util.spec_from_file_location("precursor_convergence", SCRIPT)
sys.path.insert(0, str(SCRIPT.parent))
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


FIELDNAMES = [
    "case_id", "t", "t_star", "i", "Q_l", "mdot_l", "J_k",
    "pressure_drop", "exit_area", "U_bulk", "beta", "alpha",
    "mass_flow_imbalance", "profile_l2_change", "max_ux_change",
    "mgp_iterations", "mgu_iterations", "mgp_residual", "mgu_residual",
    "cell_count", "restart_state",
]


def stable_row(t_star: float, *, restart_state: str = "fresh") -> dict[str, object]:
    q = 1.0
    jk = 2.0
    pressure = 10.0
    return {
        "case_id": "precursor_w2",
        "t": t_star * 0.139257126368389,
        "t_star": t_star,
        "i": round(t_star * 100),
        "Q_l": q,
        "mdot_l": q,
        "J_k": jk,
        "pressure_drop": pressure,
        "exit_area": 2.0,
        "U_bulk": q / 2.0,
        "beta": 1.3,
        "alpha": 2.0,
        "mass_flow_imbalance": 0.001,
        "profile_l2_change": -1.0 if t_star == 0.0 else 0.001,
        "max_ux_change": 1e-5,
        "mgp_iterations": 4,
        "mgu_iterations": 3,
        "mgp_residual": 1e-8,
        "mgu_residual": 2e-8,
        "cell_count": 1000,
        "restart_state": restart_state,
    }


def write_history(
    path: Path,
    rows: list[dict[str, object]],
    *,
    restore_from: Path | None = None,
    target_template: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    contract_path = path.with_suffix(path.suffix + ".contract.json")
    existing_contract = (
        json.loads(contract_path.read_text(encoding="utf-8"))
        if contract_path.exists() else {}
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    if target_template is None and existing_contract.get("target_template"):
        target_template = Path(existing_contract["target_template"])
    target_template = target_template or path.parent / "target-template.csv"
    target_template.write_text("target\n", encoding="utf-8")
    if restore_from is None and existing_contract.get("restore_checkpoint") not in {
        None, "not_applicable"
    }:
        restore_checkpoint = existing_contract["restore_checkpoint"]
        restore_metadata = existing_contract["restore_metadata"]
    else:
        restore_checkpoint = (
            str((restore_from / "precursor-final.dump").resolve())
            if restore_from else "not_applicable"
        )
        restore_metadata = (
            str((restore_from / "precursor-final.dump.meta").resolve())
            if restore_from else "not_applicable"
        )
    contract = {
        "schema": "internal_nozzle_precursor_run_v1",
        "case_id": rows[0]["case_id"],
        "geometry_fingerprint": "w2-test-geometry-v1",
        "source_commit": "a" * 40,
        "source_sha256": "b" * 64,
        "pressure_forcing": 351.48,
        "density_liquid": 1.0,
        "viscosity_liquid": 1.0,
        "maxlevel": 7,
        "delta_min_Dh": 0.1171875,
        "restore_checkpoint": restore_checkpoint,
        "restore_metadata": restore_metadata,
        "target_template": str(target_template.resolve()),
    }
    contract_path.write_text(
        json.dumps(contract), encoding="utf-8"
    )
    checkpoint = path.parent / "precursor-final.dump"
    checkpoint.write_bytes(b"checkpoint")
    (path.parent / "precursor-final.dump.prediction-closure-v4").write_bytes(
        f"closure:{rows[-1]['t']}:{rows[-1]['i']}".encode("ascii")
    )
    metadata = {
        "schema": "internal_nozzle_precursor_checkpoint_v2",
        "case_id": contract["case_id"],
        "geometry_fingerprint": contract["geometry_fingerprint"],
        "source_commit": contract["source_commit"],
        "source_sha256": contract["source_sha256"],
        "maxlevel": str(contract["maxlevel"]),
        "pressure_forcing": str(contract["pressure_forcing"]),
        "density_liquid": str(contract["density_liquid"]),
        "viscosity_liquid": str(contract["viscosity_liquid"]),
        "t": str(rows[-1]["t"]),
        "t_star": str(rows[-1]["t_star"]),
        "i": str(rows[-1]["i"]),
        "solver_dt": "0.01",
        "solver_dtmax": "0.02",
        "timestep_previous": "0.01",
        "previous_profile_available": "1",
        "prediction_closure_schema": "internal_nozzle_prediction_closure_v4",
        "prediction_closure_state": "precursor-final.dump.prediction-closure-v4",
    }
    (path.parent / "precursor-final.dump.meta").write_text(
        "".join(f"{key}={value}\n" for key, value in metadata.items()),
        encoding="utf-8",
    )


def closure_report(path: Path) -> dict[str, object]:
    metadata = MODULE.read_key_value_file(Path(str(path).replace(
        ".prediction-closure-v4", ".meta"
    )))
    return {
        "valid": True,
        "source_sha256": metadata["source_sha256"],
        "schedule_version": MODULE.PRECURSOR_SCHEDULE_VERSION,
        "schedule_sha256": MODULE.PRECURSOR_SCHEDULE_SHA256,
        "iteration": int(metadata["i"]),
        "grid_maxdepth": int(metadata["maxlevel"]),
        "checkpoint_t": float(metadata["t"]),
        "checkpoint_dt": float(metadata["solver_dt"]),
        "checkpoint_dtmax": float(metadata["solver_dtmax"]),
        "timestep_previous": float(metadata["timestep_previous"]),
        "domain": [0.0, -1.0, -1.0, 2.0],
    }


def stable_segments(tmp_path: Path) -> tuple[Path, Path]:
    first = tmp_path / "segment-001" / "precursor_history.csv"
    second = tmp_path / "segment-002" / "precursor_history.csv"
    target = tmp_path / "target-template.csv"
    write_history(
        first,
        [stable_row(index * 0.25) for index in range(9)],
        target_template=target,
    )
    rows = [stable_row(2.0, restart_state="restored")]
    rows.extend(stable_row(2.0 + index * 0.25, restart_state="restored")
                for index in range(1, 9))
    write_history(
        second,
        rows,
        restore_from=first.parent,
        target_template=target,
    )
    return first, second


def bounds(**overrides: object) -> object:
    values = {
        "max_pressure_iterations": 8,
        "max_velocity_iterations": 8,
        "max_pressure_residual": 1e-6,
        "max_velocity_residual": 1e-6,
        "max_cell_range_fraction": 0.01,
    }
    values.update(overrides)
    return MODULE.OperationalBounds(**values)


def test_precursor_source_prevents_duplicate_terminal_metric_rows():
    root = Path(__file__).resolve().parents[1]
    source = (root / "cases" / "basilisk" /
              "rectangular_internal_nozzle_steady_precursor.c").read_text(
                  encoding="utf-8")
    metric_event = source.split("event precursor_metrics", 1)[1].split(
        "event logfile", 1)[0]
    terminal_event = source.split("event end (t = end_time)", 1)[1]
    assert "i == 0 || i % metric_stride == 0" in metric_event
    assert "last_metric_iteration != i" in metric_event
    assert "last_metric_iteration != i" in terminal_event


def analyze(paths: tuple[Path, ...], **overrides: object) -> dict[str, object]:
    arguments = {
        "contracts": tuple(path.with_suffix(path.suffix + ".contract.json") for path in paths),
        "window_t_star": 2.0,
        "maximum_gap_t_star": 0.26,
        "minimum_samples": 6,
        "bounds": bounds(),
        "closure_validator": closure_report,
    }
    arguments.update(overrides)
    return MODULE.analyze(paths, **arguments)


def test_sequential_segments_and_exact_boundary_duplicate_converge(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    result = analyze((first, second))
    assert result["classification"] == "precursor_converged"
    assert result["pass"] is True
    assert result["combined_unique_sample_count"] == 17
    assert result["window"]["sample_count"] == 9
    assert result["metrics"]["Q_l"]["pass"] is True
    assert result["metrics"]["J_k"]["pass"] is True
    assert result["metrics"]["pressure_drop"]["pass"] is True
    assert all(result["auxiliary"]["tests"].values())
    assert len(result["inputs"][0]["history"]["sha256"]) == 64
    assert len(result["inputs"][0]["run_contract"]["sha256"]) == 64
    assert len(result["inputs"][0]["terminal_checkpoint"]["dump"]["sha256"]) == 64


def test_q_drift_above_exact_point_one_percent_limit_fails(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    rows = list(csv.DictReader(second.open(newline="", encoding="utf-8")))
    for row in rows:
        progress = (float(row["t_star"]) - 2.0) / 2.0
        row["Q_l"] = str(1.0 - 0.002 * progress)
    write_history(second, rows)
    result = analyze((first, second))
    assert result["pass"] is False
    assert result["metrics"]["Q_l"]["pass"] is False
    assert result["metrics"]["Q_l"]["limit"] == 0.001


def test_unresolved_trend_fails_even_when_endpoints_match(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    rows = list(csv.DictReader(second.open(newline="", encoding="utf-8")))
    for index, row in enumerate(rows):
        if index == len(rows) - 1:
            row["Q_l"] = "1.0"
        else:
            row["Q_l"] = str(1.0 + 0.0005 * index)
    write_history(second, rows)
    result = analyze((first, second))
    metric = result["metrics"]["Q_l"]
    assert abs(metric["signed_end_to_end_relative_drift"]) <= 0.001
    assert metric["pass"] is False
    assert (
        not metric["tests"]["ordinary_projected_relative_trend"]
        or not metric["tests"]["robust_projected_relative_trend"]
    )


def test_small_smooth_monotonic_trend_fails_noise_gate(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    rows = list(csv.DictReader(second.open(newline="", encoding="utf-8")))
    for index, row in enumerate(rows):
        row["Q_l"] = str(1.0 - index * 1e-6)
    write_history(second, rows)
    metric = analyze((first, second))["metrics"]["Q_l"]
    assert metric["tests"]["end_to_end_relative_drift"] is True
    assert metric["tests"]["ordinary_projected_relative_trend"] is True
    assert metric["tests"]["robust_projected_relative_trend"] is True
    assert metric["tests"]["no_unresolved_monotonic_trend"] is False
    assert metric["pass"] is False


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("profile_l2_change", "0.0051", "consecutive_normalized_profile_l2"),
        ("mass_flow_imbalance", "0.0051", "mass_flow_imbalance"),
        ("mgp_iterations", "9", "pressure_iterations_bounded"),
        ("mgu_iterations", "9", "velocity_iterations_bounded"),
        ("mgp_residual", "2e-6", "pressure_residual_bounded"),
        ("mgu_residual", "2e-6", "velocity_residual_bounded"),
        ("cell_count", "1020", "cell_population_bounded"),
    ],
)
def test_profile_mass_solver_and_cell_bounds_fail_closed(
    tmp_path: Path, field: str, value: str, failure: str
):
    first, second = stable_segments(tmp_path)
    rows = list(csv.DictReader(second.open(newline="", encoding="utf-8")))
    rows[-1][field] = value
    write_history(second, rows)
    result = analyze((first, second))
    assert result["pass"] is False
    assert result["auxiliary"]["tests"][failure] is False


def test_mismatched_shared_segment_boundary_is_rejected(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    rows = list(csv.DictReader(second.open(newline="", encoding="utf-8")))
    rows[0]["J_k"] = "9"
    write_history(second, rows)
    with pytest.raises(ValueError, match="boundary duplicate"):
        analyze((first, second))


def test_mismatched_segment_contract_is_rejected(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    contract_path = second.with_suffix(second.suffix + ".contract.json")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["source_commit"] = "c" * 40
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="one physical/source identity"):
        analyze((first, second))


def test_segment_gap_and_non_colocated_contract_are_rejected(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    rows = list(csv.DictReader(second.open(newline="", encoding="utf-8")))
    rows[0]["t"] = str(float(rows[0]["t"]) + 0.01)
    rows[0]["t_star"] = str(float(rows[0]["t_star"]) + 0.01)
    write_history(second, rows)
    with pytest.raises(ValueError, match="exactly continue"):
        analyze((first, second))

    first, second = stable_segments(tmp_path / "other")
    moved = tmp_path / "detached-contract.json"
    moved.write_bytes(second.with_suffix(second.suffix + ".contract.json").read_bytes())
    with pytest.raises(ValueError, match="same directory"):
        MODULE.analyze(
            (first, second),
            contracts=(first.with_suffix(first.suffix + ".contract.json"), moved),
            window_t_star=2.0,
            maximum_gap_t_star=0.26,
            minimum_samples=6,
            bounds=bounds(),
            closure_validator=closure_report,
        )


def test_full_sidecar_closure_and_template_identity_fail_closed(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    sidecar = second.parent / "precursor-final.dump.meta"
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace(
            "source_commit=" + "a" * 40, "source_commit=" + "c" * 40
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metadata mismatch source_commit"):
        analyze((first, second))

    first, second = stable_segments(tmp_path / "closure")
    with pytest.raises(ValueError, match="prediction closure mismatch schedule_sha256"):
        analyze(
            (first, second),
            closure_validator=lambda path: {
                **closure_report(path), "schedule_sha256": "d" * 64,
            },
        )

    first, second = stable_segments(tmp_path / "template")
    different = tmp_path / "different-target.csv"
    different.write_text("different\n", encoding="utf-8")
    rows = list(csv.DictReader(second.open(newline="", encoding="utf-8")))
    write_history(second, rows, restore_from=first.parent, target_template=different)
    with pytest.raises(ValueError, match="one physical/source identity"):
        analyze((first, second))


def test_production_closure_parser_rejects_unauthenticated_bytes(tmp_path: Path):
    first, second = stable_segments(tmp_path)
    with pytest.raises(ValueError, match="truncated header"):
        MODULE.analyze(
            (first, second),
            contracts=(
                first.with_suffix(first.suffix + ".contract.json"),
                second.with_suffix(second.suffix + ".contract.json"),
            ),
            window_t_star=2.0,
            maximum_gap_t_star=0.26,
            minimum_samples=6,
            bounds=bounds(),
        )


def test_window_gap_and_unavailable_profile_are_rejected(tmp_path: Path):
    history = tmp_path / "gapped.csv"
    rows = [stable_row(value) for value in (0.0, 1.0, 2.0, 2.25, 3.5, 3.75, 4.0)]
    write_history(history, rows)
    with pytest.raises(ValueError, match="sampling gap"):
        analyze((history,), minimum_samples=5)

    rows = [stable_row(index * 0.25) for index in range(17)]
    rows[-1]["profile_l2_change"] = -1.0
    write_history(tmp_path / "bad-profile.csv", rows)
    with pytest.raises(ValueError, match="unavailable profile"):
        analyze((tmp_path / "bad-profile.csv",))


def test_cli_persists_nonconvergence_and_fails_by_default(tmp_path: Path, monkeypatch):
    first, second = stable_segments(tmp_path)
    rows = list(csv.DictReader(second.open(newline="", encoding="utf-8")))
    rows[-1]["mass_flow_imbalance"] = "0.006"
    write_history(second, rows)
    output = tmp_path / "result.json"
    command = [
        "--history", str(first),
        "--history", str(second),
        "--run-contract", str(first.with_suffix(first.suffix + ".contract.json")),
        "--run-contract", str(second.with_suffix(second.suffix + ".contract.json")),
        "--window-t-star", "2",
        "--maximum-gap-t-star", "0.26",
        "--minimum-samples", "6",
        "--max-pressure-iterations", "8",
        "--max-velocity-iterations", "8",
        "--max-pressure-residual", "1e-6",
        "--max-velocity-residual", "1e-6",
        "--max-cell-range-fraction", "0.01",
        "--output", str(output),
    ]
    monkeypatch.setattr(MODULE, "validate_closure_v4", closure_report)
    assert MODULE.main(command) == 3
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["classification"] == "not_converged"
    assert "mass_flow_imbalance" in payload["failures"]


def test_duplicate_columns_nonfinite_and_symlink_are_rejected(tmp_path: Path):
    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text("case_id,t,t_star,t_star\na,0,0,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate columns"):
        MODULE.read_segment(duplicate, 0)

    history = tmp_path / "nonfinite.csv"
    rows = [stable_row(0.0), stable_row(0.25)]
    rows[1]["Q_l"] = "nan"
    write_history(history, rows)
    with pytest.raises(ValueError, match="not finite"):
        MODULE.read_segment(history, 0)

    target = tmp_path / "target.csv"
    write_history(target, [stable_row(0.0), stable_row(0.25)])
    link = tmp_path / "link.csv"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="non-symlink"):
        MODULE.read_segment(link, 0)
