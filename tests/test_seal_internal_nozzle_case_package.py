import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seal_internal_nozzle_case_package.py"
SPEC = importlib.util.spec_from_file_location("case_sealer", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

LAUNCH_FIXTURE_SCRIPT = Path(__file__).with_name(
    "test_launch_internal_nozzle_precursor_case.py"
)
LAUNCH_FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "case_launcher_fixture", LAUNCH_FIXTURE_SCRIPT,
)
LAUNCH_FIXTURE = importlib.util.module_from_spec(LAUNCH_FIXTURE_SPEC)
assert LAUNCH_FIXTURE_SPEC.loader is not None
LAUNCH_FIXTURE_SPEC.loader.exec_module(LAUNCH_FIXTURE)
ACCEPTANCE = LAUNCH_FIXTURE.MODULE.acceptance_module()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[list[object]]) -> None:
    path.write_text(
        ",".join(fields) + "\n" + "".join(",".join(map(str, row)) + "\n" for row in rows),
        encoding="utf-8",
    )


def supervision_record(root: Path, bound: dict[str, object], child_pid: int) -> Path:
    segment = str(bound["segment_id"])
    evidence = root / "supervision" / segment
    evidence.mkdir(parents=True)
    (evidence / "stdout.log").write_text("", encoding="utf-8")
    (evidence / "stderr.log").write_text("", encoding="utf-8")
    launch_inputs = [
        {
            "requested_path": item["path"], "resolved_path": item["path"],
            "size_bytes": Path(item["path"]).stat().st_size,
            "expected_sha256": item["sha256"], "observed_sha256": item["sha256"],
            "verified": True,
        }
        for item in bound["verified_inputs"]
    ]
    terminal_inputs = [
        {**item, "observed_sha256_after": item["observed_sha256"],
         "unchanged_during_run": True}
        for item in launch_inputs
    ]
    common = {
        "schema": "internal_nozzle_supervision_v2", "run_id": segment,
        "execution_id": bound["execution_id"], "segment_id": segment,
        "cwd": str(root), "argv": bound["solver_argv"], "child_pid": child_pid,
        "source_commit": bound["scientific_source_commit"],
        "source_sha256": bound["source_sha256"],
        "command_cwd_sha256": f"{child_pid:064x}",
    }
    (evidence / "launch.json").write_text(
        json.dumps({**common, "verified_inputs": launch_inputs}), encoding="utf-8",
    )
    (evidence / "terminal.json").write_text(json.dumps({
        **common, "verified_inputs": terminal_inputs, "exit_code": 0, "returncode": 0,
        "terminal_state": "normal_exit", "input_identity_changed": False,
        "child_exists_after_wait": False, "stdout_size_bytes": 0, "stderr_size_bytes": 0,
        "stdout_sha256": digest(evidence / "stdout.log"),
        "stderr_sha256": digest(evidence / "stderr.log"),
        "duplicate_lock": str(root / "locks" / f"duplicate-{segment}"),
        "writer_lock": str(
            Path(bound["batch_identity"]["canonical_lock_root"]) / "one-solver.lock"
        ),
    }), encoding="utf-8")
    return evidence


def checkpoint_metadata(
    root: Path, *, index: int, tick: int, segment: str, bound: dict[str, object],
    cumulative: float,
) -> tuple[Path, Path, Path, list[object]]:
    role = str(bound["case_role"])
    modes = MODULE.ROLE_MODES[role]
    dump = root / f"checkpoint-{index}.dump"
    metadata = root / f"checkpoint-{index}.dump.meta"
    closure = root / f"checkpoint-{index}.dump.prediction-closure-v4"
    dump.write_text(f"dump-{index}\n", encoding="utf-8")
    closure.write_text(f"closure-{index}\n", encoding="utf-8")
    metadata.write_text("\n".join([
        "schema=internal_nozzle_checkpoint_metadata_v6",
        f"case_id={bound['case_id']}", f"execution_id={bound['execution_id']}",
        f"segment_id={segment}", f"case_role={role}",
        f"solver_sha256={bound['solver']['sha256']}",
        f"source_sha256={bound['source_sha256']}",
        f"scientific_source_commit={bound['scientific_source_commit']}",
        f"schedule_version={bound['schedule']['schedule_version']}",
        f"schedule_sha256={bound['schedule']['sha256']}", f"master_tick={tick}",
        f"iteration={tick}", f"initial_state={modes['initial_state']}",
        f"inlet_mode={modes['inlet_mode']}",
        f"precursor_pressure_mode={modes['precursor_pressure_mode']}",
        "precursor_transfer_sha256=" + (
            "not_applicable" if role == "A" else str(bound["precursor_transfer"]["sha256"])
        ),
        "cumulative_nozzle_exit_discharge_definition="
        "alias_of_cumulative_nozzle_exit_net_volume",
        f"cumulative_nozzle_exit_net_volume={cumulative}",
        f"cumulative_discharged_liquid_volume={cumulative}",
    ]) + "\n", encoding="utf-8")
    dt = float(bound["schedule"]["master_tick_dt"])
    return dump, metadata, closure, [
        bound["case_id"], "full", index, tick * dt, tick, 6,
        bound["execution_id"], segment, role, bound["solver"]["sha256"], dump,
        "not_applicable" if index == 0 else str(root / f"checkpoint-{index - 1}.dump"),
        bound["source_sha256"], bound["schedule"]["schedule_version"],
        bound["schedule"]["sha256"], tick, tick * dt, tick * dt,
        modes["initial_state"], modes["inlet_mode"], modes["precursor_pressure_mode"],
        "not_applicable" if role == "A" else bound["precursor_transfer"]["sha256"],
        0.5 if role == "C" else "not_applicable",
        bound["scientific_source_commit"], metadata, closure, cumulative, cumulative,
    ]


CHECKPOINT_FIELDS = [
    "case_id", "domain_mode", "checkpoint_index", "t", "i", "maxlevel",
    "execution_id", "segment_id", "case_role", "solver_sha256", "filename",
    "parent_checkpoint", "source_sha256", "schedule_version", "schedule_sha256",
    "master_tick", "target_time", "actual_time", "initial_state", "inlet_mode",
    "precursor_pressure_mode", "precursor_transfer_sha256", "profile_bulk_velocity",
    "scientific_source_commit", "metadata_file", "prediction_closure_state_v4_file",
    "cumulative_nozzle_exit_net_volume", "cumulative_discharged_liquid_volume",
]

HYDRAULIC_FIELDS = [
    "execution_id", "segment_id", "case_role", "case_id", "plane_label", "t",
    "master_tick", "target_time", "actual_time", "Q_l", "liquid_area", "mdot_l",
    "J_k_liquid", "J_k_mixture", "J_p", "J_total",
    "area_weighted_liquid_velocity", "flux_weighted_liquid_velocity",
    "legacy_Q_l_times_area_weighted_velocity", "I2_liquid", "I3_liquid",
    "beta", "alpha", "momentum_equivalent_velocity",
    "cumulative_nozzle_exit_discharge", "cumulative_nozzle_exit_net_volume",
    "cumulative_discharged_liquid_volume",
    "cumulative_nozzle_exit_discharge_definition",
]


def hydraulic_row(bound: dict[str, object], segment: str, tick: int) -> list[object]:
    time = tick * float(bound["schedule"]["master_tick_dt"])
    return [
        bound["execution_id"], segment, bound["case_role"], bound["case_id"],
        "geometric_nozzle_exit", time, tick, time, time, 1, 1, 1, 1, 1, 1, 2,
        1, 1, 1, 1, 1, 1, 1, 1, time, time, time,
        "alias_of_cumulative_nozzle_exit_net_volume",
    ]


def make_run(requested_root: Path, role: str = "B") -> tuple[Path, Path]:
    args = LAUNCH_FIXTURE.fixture(requested_root, role)
    root = args.cwd.resolve()
    bound = LAUNCH_FIXTURE.MODULE.build_contract(args)
    segment = str(bound["segment_id"])
    execution = str(bound["execution_id"])
    case = str(bound["case_id"])
    modes = MODULE.ROLE_MODES[role]
    source_sha = str(bound["source_sha256"])
    solver_sha = str(bound["solver"]["sha256"])
    schedule_sha = str(bound["schedule"]["sha256"])
    schedule_dt = float(bound["schedule"]["master_tick_dt"])
    transfer_sha = (
        "not_applicable" if role == "A" else str(bound["precursor_transfer"]["sha256"])
    )
    (root / f"scientific_launch_contract.{segment}.json").write_text(
        json.dumps(bound), encoding="utf-8",
    )

    runtime = {
        "schema": "internal_nozzle_scientific_runtime_v1", "execution_id": execution,
        "segment_id": segment, "case_role": role, "case_id": case,
        "solver_sha256": solver_sha, "source_sha256": source_sha,
        "scientific_source_commit": bound["scientific_source_commit"],
        "schedule_sha256": schedule_sha, "precursor_transfer_sha256": transfer_sha,
        "density_liquid": 1.0, "initial_state": modes["initial_state"],
        "inlet_mode": modes["inlet_mode"],
        "precursor_pressure_mode": modes["precursor_pressure_mode"],
    }
    if role != "A":
        bulk = bound["precursor_bulk_target"]
        runtime.update({
            "precursor_convergence_sha256": bulk["convergence_report_sha256"],
            "precursor_history_sha256": bulk["history_sha256"],
            "precursor_target_derivation": bulk["derivation"],
            "precursor_target_Q_l": bulk["terminal_Q_l"],
            "precursor_target_liquid_area": bulk["terminal_liquid_area"],
            "precursor_target_bulk_velocity": bulk["bulk_velocity"],
            "precursor_target_velocity_tolerance": bulk["absolute_consistency_tolerance"],
        })
    (root / f"scientific_runtime_contract.{segment}.json").write_text(
        json.dumps(runtime), encoding="utf-8",
    )
    init = {**runtime, "schema": "internal_nozzle_initialization_v2",
            "transfer_sha256": transfer_sha, "native_restore_unchanged": True}
    if role == "C":
        init.update({
            "profile_bulk_velocity": 0.5, "profile_discrete_unit_bulk": 0.5,
            "profile_normalization": 2.0, "profile_achieved_bulk_velocity": 0.5,
            "profile_target_absolute_error": 0.0,
            "profile_numerical_tolerance": 64 * sys.float_info.epsilon,
            "poiseuille_profile_validation_passed": True,
        })
    (root / f"initialization_contract.{segment}.json").write_text(
        json.dumps(init), encoding="utf-8",
    )

    final_tick = 2
    final_time = final_tick * schedule_dt
    raw = {
        "schema": "internal_nozzle_raw_export_v1", "execution_id": execution,
        "segment_id": segment, "case_id": case, "domain_mode": "full", **modes,
        "exit_velocity_imposed": False, "source_sha256": source_sha,
        "scientific_source_commit": bound["scientific_source_commit"],
        "schedule_version": bound["schedule"]["schedule_version"],
        "schedule_sha256": schedule_sha, "precursor_transfer_sha256": transfer_sha,
        "end_time": final_time, "diagnostic_dt": schedule_dt,
        "master_tick_dt": schedule_dt, "maxlevel": 6,
        "geometry": {"W": 1, "H": 1, "Dh": 1, "A0": 1, "nozzle_exit_x": 1},
        "completion": {"reached_end_time": True, "stable_flag": True,
                       "mass_balance_passed": True},
        "cumulative_nozzle_exit_discharge": final_time,
        "cumulative_nozzle_exit_net_volume": final_time,
        "cumulative_discharged_liquid_volume": final_time,
        "cumulative_nozzle_exit_discharge_definition":
            "alias_of_cumulative_nozzle_exit_net_volume",
        "files": {"hydraulic_plane_metrics": "hydraulic_plane_metrics.csv",
                  "hydraulic_plane_profiles": "hydraulic_plane_profiles.csv",
                  "solver_health_metrics": "solver_health_metrics.csv",
                  "initialization_contract": "initialization_contract.json"},
    }
    (root / "raw_export_manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    write_csv(root / "hydraulic_plane_metrics.csv", HYDRAULIC_FIELDS,
              [hydraulic_row(bound, segment, tick) for tick in range(final_tick + 1)])
    profile_fields = ["execution_id", "segment_id", "case_role", "case_id", "plane_label",
                      "t", "x", "y", "z", "f", "ux", "p"]
    write_csv(root / "hydraulic_plane_profiles.csv", profile_fields, [
        [execution, segment, role, case, plane, final_time, 1, 0, 0, 1, 1, 0]
        for plane in ("upstream_plenum", "pre_contraction", "post_contraction",
                      "mid_straight", "geometric_nozzle_exit")
    ])
    health_fields = ["execution_id", "segment_id", "case_role", "case_id", "t", "i",
                     "dt", "grid_maxdepth", "total_grid_cells", "mgp_i", "maxlevel"]
    write_csv(root / "solver_health_metrics.csv", health_fields,
              [[execution, segment, role, case, final_time, final_tick, schedule_dt,
                6, 10, 1, 6]])

    if role != "A":
        projection = root / "precursor_transfer_projection.csv"
        projection_rows = []
        for index, phase in enumerate(ACCEPTANCE.PROJECTION_PHASES):
            stats = ([4, 1.0, 0.001, 2, 2, 4, 2, 100]
                     if index == ACCEPTANCE.PROJECTION_SELECTED_INDEX else
                     ["not_applicable"] * len(ACCEPTANCE.PROJECTION_STATS))
            metrics = [99.0, 99.0, 0, 0, 0] if index == 0 else [0, 0, 0, 0, 0]
            times = [0, 0, 0, schedule_dt]
            iterations = [0, 0, 0, 1]
            projection_rows.append([
                case, index, phase, times[index], iterations[index], *metrics, 1,
                *stats,
                modes["initial_state"], modes["inlet_mode"],
                modes["precursor_pressure_mode"], transfer_sha, execution, segment, role,
            ])
        write_csv(projection, list(ACCEPTANCE.PROJECTION_HEADER), projection_rows)
        criteria_path, criteria = ACCEPTANCE.load_projection_criteria(
            args.projection_criteria, args.projection_criteria_sha256,
        )
        _, identity, observed = ACCEPTANCE.projection_measurements(projection)
        acceptance = ACCEPTANCE.expected_projection_acceptance(
            criteria_path, args.projection_criteria_sha256, criteria,
            projection, identity, observed,
        )
        (root / "precursor_transfer_projection_acceptance.json").write_text(
            json.dumps(acceptance), encoding="utf-8",
        )

    dump, _, _, checkpoint_row = checkpoint_metadata(
        root, index=0, tick=final_tick, segment=segment, bound=bound,
        cumulative=final_time,
    )
    write_csv(root / "checkpoint_index.csv", CHECKPOINT_FIELDS, [checkpoint_row])
    (root / "checkpoint_manifest.json").write_text(json.dumps({
        "schema": "internal_nozzle_checkpoint_manifest_v1", "execution_id": execution,
        "final_segment_id": segment, "case_role": role, "case_id": case,
        "checkpoint_count": 1, "latest_checkpoint_file": str(dump),
    }), encoding="utf-8")
    (root / "visual_pipeline_case_summary.csv").write_text(
        "case_id\n" + case + "\n", encoding="utf-8",
    )
    return root, supervision_record(root, bound, 100)


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        rows = list(reader)
    return rows[0], rows[1:]


def add_restart_segment(root: Path, first_evidence: Path) -> Path:
    first_segment = first_evidence.name
    second_segment = first_segment[:-1] + "1"
    bound_path = root / f"scientific_launch_contract.{first_segment}.json"
    bound = json.loads(bound_path.read_text(encoding="utf-8"))
    first_checkpoint = root / "checkpoint-0.dump"
    first_metadata = root / "checkpoint-0.dump.meta"
    first_closure = root / "checkpoint-0.dump.prediction-closure-v4"
    bound["segment_id"] = second_segment
    bound["expected_runtime_contract"] = str(
        root / f"scientific_runtime_contract.{second_segment}.json"
    )
    bound["expected_initialization_contract"] = str(
        root / f"initialization_contract.{second_segment}.json"
    )
    bound["restore"] = {
        "kind": "checkpoint", "predecessor_segment_id": first_segment,
        "checkpoint": {"path": str(first_checkpoint), "sha256": digest(first_checkpoint)},
        "metadata": {"path": str(first_metadata), "sha256": digest(first_metadata)},
        "prediction_closure": {"path": str(first_closure), "sha256": digest(first_closure)},
    }
    position = bound["solver_argv"].index("--segment-id")
    bound["solver_argv"][position + 1] = second_segment
    bound["solver_argv"] += [
        "--restore", str(first_checkpoint), "--restore-sha256", digest(first_checkpoint),
        "--restore-metadata-sha256", digest(first_metadata),
        "--restore-closure-sha256", digest(first_closure),
        "--predecessor-segment-id", first_segment,
    ]
    for label, path in (("restore_checkpoint", first_checkpoint),
                        ("restore_metadata", first_metadata),
                        ("restore_closure", first_closure)):
        bound["verified_inputs"].append({
            "label": label, "path": str(path), "sha256": digest(path),
        })
    bound["supervisor"]["evidence_dir"] = str(root / "supervision" / second_segment)
    supervisor_argv = bound["supervisor_argv"]
    separator = supervisor_argv.index("--")
    for option, value in (
        ("--evidence-dir", str(root / "supervision" / second_segment)),
        ("--segment-id", second_segment),
        ("--run-id", second_segment),
    ):
        position = supervisor_argv[:separator].index(option)
        supervisor_argv[position + 1] = value
    supervisor_argv[separator + 1:] = bound["solver_argv"]
    (root / f"scientific_launch_contract.{second_segment}.json").write_text(
        json.dumps(bound), encoding="utf-8",
    )
    for prefix in ("scientific_runtime_contract", "initialization_contract"):
        payload = json.loads(
            (root / f"{prefix}.{first_segment}.json").read_text(encoding="utf-8")
        )
        payload["segment_id"] = second_segment
        (root / f"{prefix}.{second_segment}.json").write_text(
            json.dumps(payload), encoding="utf-8",
        )

    final_tick = 4
    schedule_dt = float(bound["schedule"]["master_tick_dt"])
    final_time = final_tick * schedule_dt
    raw_path = root / "raw_export_manifest.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw.update({
        "segment_id": second_segment, "end_time": final_time,
        "cumulative_nozzle_exit_discharge": final_time,
        "cumulative_nozzle_exit_net_volume": final_time,
        "cumulative_discharged_liquid_volume": final_time,
    })
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    fields, rows = read_csv(root / "hydraulic_plane_metrics.csv")
    rows.extend(hydraulic_row(bound, second_segment, tick) for tick in (3, 4))
    write_csv(root / "hydraulic_plane_metrics.csv", fields, rows)
    fields, rows = read_csv(root / "solver_health_metrics.csv")
    rows.append([
        bound["execution_id"], second_segment, bound["case_role"], bound["case_id"],
        final_time, final_tick, schedule_dt, 6, 10, 1, 6,
    ])
    write_csv(root / "solver_health_metrics.csv", fields, rows)
    dump, _, _, second_checkpoint_row = checkpoint_metadata(
        root, index=1, tick=final_tick, segment=second_segment, bound=bound,
        cumulative=final_time,
    )
    fields, rows = read_csv(root / "checkpoint_index.csv")
    rows.append(second_checkpoint_row)
    write_csv(root / "checkpoint_index.csv", fields, rows)
    manifest_path = root / "checkpoint_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "final_segment_id": second_segment, "checkpoint_count": 2,
        "latest_checkpoint_file": str(dump),
    })
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return supervision_record(root, bound, 101)


@pytest.mark.parametrize("role", "ABC")
def test_seals_strict_v2_role_package(tmp_path: Path, role: str) -> None:
    root, evidence = make_run(tmp_path / role, role)
    result = MODULE.seal(root, role, [evidence])
    assert result["schema"] == "sealed_internal_nozzle_case_package_v2"
    assert result["execution_id"] == f"case-{role.lower()}-execution"
    assert result["validated_evidence"] == MODULE.ROLE_PREREQUISITES[role]
    assert (root / "scientific_runtime_contract.json").is_file()


def test_rejects_wrong_segment_binding(tmp_path: Path) -> None:
    root, evidence = make_run(tmp_path / "B")
    terminal = json.loads((evidence / "terminal.json").read_text())
    terminal["segment_id"] = "other"
    (evidence / "terminal.json").write_text(json.dumps(terminal))
    with pytest.raises(ValueError, match="segment ID|segment_id mismatch"):
        MODULE.seal(root, "B", [evidence])


def test_rejects_nonmonotone_physical_cumulative(tmp_path: Path) -> None:
    root, evidence = make_run(tmp_path / "B")
    raw = json.loads((root / "raw_export_manifest.json").read_text())
    raw["cumulative_discharged_liquid_volume"] = -1
    (root / "raw_export_manifest.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="cumulative"):
        MODULE.seal(root, "B", [evidence])


def test_rejects_projection_acceptance_not_supported_by_rows(tmp_path: Path) -> None:
    root, evidence = make_run(tmp_path / "B")
    acceptance_path = root / "precursor_transfer_projection_acceptance.json"
    acceptance = json.loads(acceptance_path.read_text())
    acceptance["predicates"][0]["observed"] = 0.5
    acceptance_path.write_text(json.dumps(acceptance))
    with pytest.raises(ValueError, match="deterministic criteria result"):
        MODULE.seal(root, "B", [evidence])


def test_rejects_out_of_order_projection_rows(tmp_path: Path) -> None:
    root, evidence = make_run(tmp_path / "B")
    projection = root / "precursor_transfer_projection.csv"
    lines = projection.read_text().splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    projection.write_text("\n".join(lines) + "\n")
    acceptance_path = root / "precursor_transfer_projection_acceptance.json"
    acceptance = json.loads(acceptance_path.read_text())
    acceptance["projection_evidence"]["sha256"] = digest(projection)
    acceptance_path.write_text(json.dumps(acceptance))
    with pytest.raises(ValueError, match="phase sequence|duplicated/out of order"):
        MODULE.seal(root, "B", [evidence])


def test_rejects_false_case_c_profile_pass(tmp_path: Path) -> None:
    root, evidence = make_run(tmp_path / "C", "C")
    init_path = root / f"initialization_contract.{evidence.name}.json"
    init = json.loads(init_path.read_text())
    init["poiseuille_profile_validation_passed"] = False
    init_path.write_text(json.dumps(init))
    with pytest.raises(ValueError, match="profile pass artifact"):
        MODULE.seal(root, "C", [evidence])


def test_rejects_empty_log_symlink(tmp_path: Path) -> None:
    root, evidence = make_run(tmp_path / "A", "A")
    stdout = evidence / "stdout.log"
    target = root / "empty-target"
    target.write_text("")
    stdout.unlink()
    stdout.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        MODULE.seal(root, "A", [evidence])


def test_restart_chain_binds_immediate_predecessor_checkpoint_hashes(tmp_path: Path) -> None:
    root, first = make_run(tmp_path / "B")
    second = add_restart_segment(root, first)
    result = MODULE.seal(root, "B", [first, second])
    assert result["final_segment_id"] == second.name
    assert [item["segment_id"] for item in result["supervision"]] == [
        first.name, second.name,
    ]


def test_restart_chain_rejects_wrong_checkpoint_hash(tmp_path: Path) -> None:
    root, first = make_run(tmp_path / "B")
    second = add_restart_segment(root, first)
    bound_path = root / f"scientific_launch_contract.{second.name}.json"
    bound = json.loads(bound_path.read_text())
    bound["restore"]["checkpoint"]["sha256"] = "0" * 64
    bound_path.write_text(json.dumps(bound))
    with pytest.raises(ValueError, match="restart does not bind|--restore-sha256"):
        MODULE.seal(root, "B", [first, second])
