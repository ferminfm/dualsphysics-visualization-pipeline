import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_steady_precursor_cases.py"
SPEC = importlib.util.spec_from_file_location("compare_precursor", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def verified(path: Path) -> dict[str, object]:
    value = digest(path)
    return {
        "resolved_path": str(path.resolve()),
        "expected_sha256": value,
        "observed_sha256": value,
        "observed_sha256_after": value,
        "verified": True,
        "unchanged_during_run": True,
    }


def write_schedule(root: Path) -> tuple[Path, str]:
    path = root / "run_schedule_contract.json"
    path.write_text(json.dumps({
        "schema": MODULE.SCHEDULE_CONTRACT_SCHEMA,
        "schedule_version": "steady-r2-v2",
        "master_tick_dt": 1.0,
        "event_time_tolerance": 1e-12,
        "lightweight": {"base_stride": 1, "dense_stride": 1},
        "full_field": {"base_stride": 1, "dense_stride": 1},
        "checkpoint_stride": 2,
        "dense_window": {"start_tick": 0, "end_tick": 8},
    }, sort_keys=True), encoding="utf-8")
    return path, digest(path)


def runtime_payload(root: Path, role: str, schedule_sha: str,
                    source_sha: str, solver_sha: str,
                    transfer_sha: str) -> dict[str, object]:
    mode = MODULE.CASE_MODES[role]
    argv = [
        str((root / "solver").resolve()), "--output-dir", str(root.resolve()),
        "--source-sha", source_sha, "--source-commit", "d" * 40,
        "--schedule-version", "steady-r2-v2", "--schedule-sha", schedule_sha,
    ]
    if role in "BC":
        argv.extend([
            "--precursor-transfer", str((root / "precursor-transfer.json").resolve()),
            "--precursor-transfer-sha256", transfer_sha,
        ])
    return {
        "schema": MODULE.RUNTIME_CONTRACT_SCHEMA,
        "execution_id": f"execution-{role}", "segment_id": f"segment-{role}-001",
        "case_role": role, "case_id": f"case-{role}", "run_root": str(root.resolve()),
        "domain_mode": "full", **mode, "exit_velocity_imposed": False,
        "precursor_transfer_sha256": transfer_sha,
        "source_sha256": source_sha, "scientific_source_commit": "d" * 40,
        "solver_sha256": solver_sha, "schedule_version": "steady-r2-v2",
        "schedule_sha256": schedule_sha, "solver_argv": argv,
        "prerequisites": dict(MODULE.ROLE_PREREQUISITES[role]),
    }


def write_case(path: Path, role: str, slope: float, values=None) -> None:
    fields = [
        "execution_id", "segment_id", "case_id", "master_tick", "target_time",
        "actual_time", "t", "plane_label", "maxlevel", "Q_l", "mdot_l",
        "area_weighted_liquid_velocity", "flux_weighted_liquid_velocity",
        "J_k_liquid", "J_p", "J_total", "forcing_to_plane_pressure_drop",
        "liquid_area", "beta", "alpha", "momentum_equivalent_velocity",
        "cumulative_discharged_liquid_volume",
        "cumulative_nozzle_exit_net_volume", "initial_state", "inlet_mode",
        "precursor_pressure_mode", "precursor_transfer_sha256",
    ]
    mode = MODULE.CASE_MODES[role]
    series = values if values is not None else [10.0 + slope * step for step in range(9)]
    positive_cumulative = 0.0
    net_cumulative = 0.0
    previous_q = None
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for step, q in enumerate(series):
            if previous_q is not None:
                positive_cumulative += 0.5 * (max(previous_q, 0.0) + max(q, 0.0))
                net_cumulative += 0.5 * (previous_q + q)
            writer.writerow({
                "execution_id": f"execution-{role}",
                "segment_id": f"segment-{role}-001", "case_id": f"case-{role}",
                "master_tick": step, "target_time": format(float(step), ".17g"),
                "actual_time": format(float(step), ".17g"), "t": format(float(step), ".17g"),
                "plane_label": "geometric_nozzle_exit", "maxlevel": 8,
                "Q_l": q, "mdot_l": q,
                "area_weighted_liquid_velocity": q,
                "flux_weighted_liquid_velocity": 1.1 * q,
                "J_k_liquid": 2.0 * abs(q), "J_p": 1.0,
                "J_total": 2.0 * abs(q) + 1.0,
                "forcing_to_plane_pressure_drop": 3.0, "liquid_area": 2.0,
                "beta": 1.3, "alpha": 2.0,
                "momentum_equivalent_velocity": abs(q),
                "cumulative_discharged_liquid_volume": positive_cumulative,
                "cumulative_nozzle_exit_net_volume": net_cumulative,
                "initial_state": mode["initial_state"], "inlet_mode": mode["inlet_mode"],
                "precursor_pressure_mode": mode["precursor_pressure_mode"],
                "precursor_transfer_sha256": (
                    "not_applicable" if role == "A" else
                    hashlib.sha256(b"common precursor transfer\n").hexdigest()
                ),
            })
            previous_q = q


def write_run(root: Path, role: str, slope: float = -0.05, values=None) -> tuple[Path, Path]:
    root.mkdir()
    source = root / "source-bundle.json"
    source.write_text("common source bundle\n", encoding="utf-8")
    solver = root / "solver"
    solver.write_bytes(("solver-" + role).encode())
    transfer = root / "precursor-transfer.json"
    transfer.write_text("common precursor transfer\n", encoding="utf-8")
    schedule, schedule_sha = write_schedule(root)
    source_sha, solver_sha = digest(source), digest(solver)
    transfer_sha = "not_applicable" if role == "A" else digest(transfer)
    runtime = runtime_payload(
        root, role, schedule_sha, source_sha, solver_sha, transfer_sha,
    )
    runtime_path = root / MODULE.RUNTIME_CONTRACT_MEMBER
    runtime_path.write_text(json.dumps(runtime, sort_keys=True), encoding="utf-8")

    mode = MODULE.CASE_MODES[role]
    raw = {
        "schema": "internal_nozzle_raw_export_v1",
        "execution_id": f"execution-{role}", "segment_id": f"segment-{role}-001",
        "case_id": f"case-{role}", "domain_mode": "full", **mode,
        "precursor_transfer_sha256": transfer_sha, "exit_velocity_imposed": False,
        "source_sha256": source_sha, "scientific_source_commit": "d" * 40,
        "schedule_version": "steady-r2-v2", "schedule_sha256": schedule_sha,
        "maxlevel": 8, "diagnostic_dt": 1.0, "master_tick_dt": 1.0,
        "geometry": {"W": 2.0, "H": 1.0, "Dh": 1.0, "A0": 2.0,
                     "nozzle_exit_x": 15.0},
        "files": {
            "hydraulic_plane_metrics": "hydraulic_plane_metrics.csv",
            "hydraulic_plane_profiles": "hydraulic_plane_profiles.csv",
            "solver_health_metrics": "solver_health_metrics.csv",
            "initialization_contract": "initialization_contract.json",
        },
    }
    (root / "raw_export_manifest.json").write_text(
        json.dumps(raw, sort_keys=True), encoding="utf-8",
    )
    (root / "initialization_contract.json").write_text(json.dumps({
        "schema": "internal_nozzle_initialization_v1",
        "execution_id": f"execution-{role}", "segment_id": f"segment-{role}-001",
        "initial_state": mode["initial_state"], "inlet_mode": mode["inlet_mode"],
        "precursor_pressure_mode": mode["precursor_pressure_mode"],
        "transfer_sha256": transfer_sha, "native_restore_unchanged": True,
    }, sort_keys=True), encoding="utf-8")
    metrics = root / "hydraulic_plane_metrics.csv"
    write_case(metrics, role, slope, values)
    for name in (
        "hydraulic_plane_profiles.csv", "solver_health_metrics.csv",
        "checkpoint_index.csv", "visual_pipeline_case_summary.csv",
    ):
        (root / name).write_text("header\n", encoding="utf-8")
    (root / "checkpoint_manifest.json").write_text("{}\n", encoding="utf-8")
    if role in "BC":
        (root / "precursor_transfer_projection.csv").write_text("header\n", encoding="utf-8")

    supervision = root / "supervision"
    supervision.mkdir()
    stdout, stderr = supervision / "stdout.log", supervision / "stderr.log"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    verified_inputs = [verified(source), verified(solver), verified(schedule)]
    if role in "BC":
        verified_inputs.append(verified(transfer))
    common = {
        "run_id": f"segment-{role}-001", "execution_id": f"execution-{role}",
        "segment_id": f"segment-{role}-001", "cwd": str(root.resolve()),
        "argv": runtime["solver_argv"], "child_pid": 123,
        "source_commit": "d" * 40, "source_sha256": source_sha,
        "verified_inputs": verified_inputs,
    }
    launch, terminal = supervision / "launch.json", supervision / "terminal.json"
    launch.write_text(json.dumps(common, sort_keys=True), encoding="utf-8")
    terminal.write_text(json.dumps({
        **common, "exit_code": 0, "terminal_state": "normal_exit",
        "input_identity_changed": False, "child_exists_after_wait": False,
        "stdout_size_bytes": 0, "stderr_size_bytes": 0,
        "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr),
    }, sort_keys=True), encoding="utf-8")
    names = list(MODULE.REQUIRED_PACKAGE_MEMBERS)
    if role in "BC":
        names.append("precursor_transfer_projection.csv")
    members = {name: record(root, root / name) for name in names}
    package = {
        "schema": MODULE.PACKAGE_SCHEMA, "execution_id": f"execution-{role}",
        "final_segment_id": f"segment-{role}-001", "case_role": role,
        "case_id": f"case-{role}", "run_root": str(root.resolve()),
        "source_sha256": source_sha, "scientific_source_commit": "d" * 40,
        "solver_sha256": solver_sha, "schedule_version": "steady-r2-v2",
        "schedule_sha256": schedule_sha, "precursor_transfer_sha256": transfer_sha,
        "runtime_contract_sha256": digest(runtime_path),
        "runtime_contract": members[MODULE.RUNTIME_CONTRACT_MEMBER], "members": members,
        "validated_evidence": dict(MODULE.ROLE_PREREQUISITES[role]),
        "supervision": [{
            "directory": "supervision", "run_id": f"segment-{role}-001",
            "execution_id": f"execution-{role}", "segment_id": f"segment-{role}-001",
            "exit_code": 0, "launch": record(root, launch),
            "terminal": record(root, terminal), "stdout": record(root, stdout),
            "stderr": record(root, stderr),
        }],
    }
    package_path = root / "sealed_case_package.json"
    package_path.write_text(json.dumps(package, sort_keys=True), encoding="utf-8")
    return metrics, package_path


def refresh_package(package_path: Path) -> None:
    root = package_path.parent
    package = json.loads(package_path.read_text(encoding="utf-8"))
    runtime_path = root / MODULE.RUNTIME_CONTRACT_MEMBER
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    package.update({
        "runtime_contract_sha256": digest(runtime_path),
        "runtime_contract": record(root, runtime_path),
        "source_sha256": runtime["source_sha256"],
        "scientific_source_commit": runtime["scientific_source_commit"],
        "solver_sha256": runtime["solver_sha256"],
        "schedule_version": runtime["schedule_version"],
        "schedule_sha256": runtime["schedule_sha256"],
        "precursor_transfer_sha256": runtime["precursor_transfer_sha256"],
    })
    for name in package["members"]:
        package["members"][name] = record(root, root / name)
    package["runtime_contract"] = package["members"][MODULE.RUNTIME_CONTRACT_MEMBER]
    package_path.write_text(json.dumps(package, sort_keys=True), encoding="utf-8")


def inputs(tmp_path: Path, slopes=(-0.2, -0.05, -0.05), values=None):
    paths, packages = {}, {}
    for role, slope in zip("ABC", slopes):
        role_values = None if values is None else values[role]
        paths[role], packages[role] = write_run(tmp_path / role, role, slope, role_values)
    return paths, packages


def test_v2_contracts_and_actual_bracketed_matches(tmp_path: Path):
    paths, packages = inputs(tmp_path)
    result = MODULE.compare(paths, packages, 1.0)
    assert result["schema"] == "steady_precursor_matched_comparison_v2"
    assert result["contract_compatibility"]["status"] == "compatible"
    assert result["precursor_effect_candidate"] == "PRECURSOR_MATERIALLY_REDUCES_TRANSIENT"
    assert result["common_horizon"]["master_tick"] == 8
    for coordinate in (
        "cumulative_discharged_liquid_volume_normalized",
        "cumulative_nozzle_exit_net_volume_normalized", "Q_l", "J_k_liquid", "J_total",
    ):
        match = result["matched_states"][coordinate]
        assert match["status"] == "matched_unique"
        assert "B_minus_A" in match["pairwise_differences"]


def test_all_trends_are_truncated_to_exact_common_tick(tmp_path: Path):
    values = {
        "A": [10.0] * 9,
        "B": [10.0] * 7 + [100.0, 200.0],
        "C": [10.0] * 7,
    }
    paths, packages = inputs(tmp_path, values=values)
    result = MODULE.compare(paths, packages, 1.0)
    assert result["common_horizon"]["master_tick"] == 6
    assert result["stationarity"]["B"]["end_t_star"] == 6.0
    assert result["common_horizon"]["case_disposition"]["B"][
        "right_truncated_to_common_horizon"
    ] is True


def test_role_prerequisites_and_package_runtime_binding_fail_closed(tmp_path: Path):
    paths, packages = inputs(tmp_path)
    runtime_path = packages["B"].parent / MODULE.RUNTIME_CONTRACT_MEMBER
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["prerequisites"]["precursor_convergence_verified"] = False
    runtime_path.write_text(json.dumps(runtime, sort_keys=True), encoding="utf-8")
    refresh_package(packages["B"])
    with pytest.raises(ValueError, match="role prerequisite matrix mismatch"):
        MODULE.compare(paths, packages, 1.0)


def test_case_a_cannot_smuggle_precursor_transfer_in_argv(tmp_path: Path):
    paths, packages = inputs(tmp_path)
    runtime_path = packages["A"].parent / MODULE.RUNTIME_CONTRACT_MEMBER
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["solver_argv"].extend(["--precursor-transfer", "/tmp/wrong"])
    runtime_path.write_text(json.dumps(runtime, sort_keys=True), encoding="utf-8")
    supervision = packages["A"].parent / "supervision"
    for name in ("launch.json", "terminal.json"):
        payload = json.loads((supervision / name).read_text(encoding="utf-8"))
        payload["argv"] = runtime["solver_argv"]
        (supervision / name).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    refresh_package(packages["A"])
    package = json.loads(packages["A"].read_text(encoding="utf-8"))
    for item in package["supervision"]:
        item["launch"] = record(packages["A"].parent, supervision / "launch.json")
        item["terminal"] = record(packages["A"].parent, supervision / "terminal.json")
    packages["A"].write_text(json.dumps(package, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="must not name a precursor transfer"):
        MODULE.compare(paths, packages, 1.0)


def test_tick_precision_mismatch_fails(tmp_path: Path):
    paths, packages = inputs(tmp_path)
    rows = list(csv.DictReader(paths["B"].open(newline="", encoding="utf-8")))
    rows[3]["target_time"] = "3.0000001"
    with paths["B"].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    refresh_package(packages["B"])
    with pytest.raises(ValueError, match="inconsistent with master_tick"):
        MODULE.compare(paths, packages, 1.0)


def test_signed_net_and_monotone_positive_discharge_are_distinct(tmp_path: Path):
    metrics, package = write_run(tmp_path / "A", "A", values=[1.0, -1.0, -1.0])
    contract = MODULE.read_package(package, "A")
    rows, provenance = MODULE.load(metrics, 1.0, "A", contract)
    assert rows[-1]["cumulative_discharged_liquid_volume"] == pytest.approx(0.5)
    assert rows[-1]["cumulative_nozzle_exit_net_volume"] == pytest.approx(-1.0)
    assert provenance["signed_net_coordinate"].startswith("integral(Q_l")


def test_positive_discharge_coordinate_cannot_decrease(tmp_path: Path):
    metrics, package = write_run(tmp_path / "A", "A", values=[1.0, 1.0, 1.0])
    rows = list(csv.DictReader(metrics.open(newline="", encoding="utf-8")))
    rows[2]["cumulative_discharged_liquid_volume"] = "0.25"
    with metrics.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    refresh_package(package)
    contract = MODULE.read_package(package, "A")
    with pytest.raises(ValueError, match="cumulative discharged liquid volume decreased"):
        MODULE.load(metrics, 1.0, "A", contract)


def test_uncertainty_overlap_is_not_equivalence_without_predeclaration():
    def metric(slope, uncertainty):
        return {"robust_relative_slope_percent_per_t_star": slope,
                "relative_slope_95_uncertainty_percent_per_t_star": uncertainty}

    trends = {
        "A": {"classification": "TRANSIENT",
              "metrics": {name: metric(-2.0, 0.8) for name in MODULE.CORE}},
        "B": {"classification": "TRANSIENT",
              "metrics": {name: metric(-0.9, 0.8) for name in MODULE.CORE}},
        "C": {"classification": "TRANSIENT",
              "metrics": {name: metric(-0.9, 0.8) for name in MODULE.CORE}},
    }
    times = {role: {"sustained_from_t_star": None} for role in "ABC"}
    effect, evidence = MODULE.classify(trends, times)
    assert effect == "MIXED_OR_UNRESOLVED"
    assert evidence["equivalence_basis"].startswith("none")


def test_stationarity_requires_one_t_star_sustained_dwell():
    rows = [
        {"t_star": step * 0.25,
         **{name: (10.0 - step if step < 8 else 2.0) for name in MODULE.CORE}}
        for step in range(21)
    ]
    result = MODULE.time_to_stationarity(rows)
    assert result["status"] == "reached_and_sustained"
    assert result["observed_through_t_star"] - result["sustained_from_t_star"] >= 1.0
    censored = MODULE.time_to_stationarity(rows[:-3])
    assert censored["status"] == "right_censored_unresolved"
    assert censored["censoring_disposition"] == "right_censored_stationarity_unresolved"


def test_every_core_metric_must_pass_stationarity_gate():
    rows = []
    for step in range(5):
        row = {"t_star": float(step), **{name: 10.0 for name in MODULE.CORE}}
        row["J_total"] = 10.0 - step
        rows.append(row)
    result = MODULE.window_trends(rows)
    assert result["classification"] == "TRANSIENT"
    assert set(result["metrics"]) == set(MODULE.CORE)


def interpolation_rows(values: list[float]) -> list[dict[str, float]]:
    rows = []
    for index, value in enumerate(values):
        rows.append({
            "master_tick": index, "t": float(index), "target_time": float(index),
            "actual_time": float(index), "t_star": float(index),
            "cumulative_discharged_liquid_volume": float(index),
            "cumulative_discharged_liquid_volume_normalized": float(index),
            "cumulative_nozzle_exit_net_volume": float(index),
            "cumulative_nozzle_exit_net_volume_normalized": float(index),
            **{name: value for name in MODULE.METRICS},
        })
    return rows


def test_exact_hits_and_all_crossings_are_enumerated_and_ambiguous():
    rows = interpolation_rows([1.0, 2.0, 0.0, 2.0])
    candidates = MODULE.interpolation_candidates(rows, "Q_l", 1.0)
    assert [item["kind"] for item in candidates] == [
        "exact_sample", "linear_interpolation", "linear_interpolation",
    ]
    assert MODULE.interpolate(rows, "Q_l", 1.0) is None
    series = {role: rows for role in "ABC"}
    match = MODULE.matched_state(series, "Q_l")
    assert match["status"] == "ambiguous_bracket"
    assert "no root is selected" in match["ambiguity"]


def test_package_and_metrics_must_be_same_sealed_directory(tmp_path: Path):
    paths, packages = inputs(tmp_path)
    copied = tmp_path / "copied.csv"
    copied.write_bytes(paths["B"].read_bytes())
    paths["B"] = copied
    with pytest.raises(ValueError, match="not the contracted run member"):
        MODULE.compare(paths, packages, 1.0)


def test_member_hash_binding_rejects_post_seal_mutation(tmp_path: Path):
    paths, packages = inputs(tmp_path)
    with paths["A"].open("a", encoding="utf-8") as stream:
        stream.write("post-seal mutation\n")
    with pytest.raises(ValueError, match="packaged file identity mismatch"):
        MODULE.compare(paths, packages, 1.0)
