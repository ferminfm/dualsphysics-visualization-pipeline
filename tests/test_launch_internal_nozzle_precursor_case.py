import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "launch_internal_nozzle_precursor_case.py"
SPEC = importlib.util.spec_from_file_location("bound_launch", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path, role: str = "B") -> argparse.Namespace:
    batch_id = "20260831-internal-nozzle-steady-precursor-regime-audit-r2"
    batch_root = tmp_path / batch_id
    root = batch_root / "cases" / f"case-{role.lower()}"
    root.mkdir(parents=True)
    solver = root / "solver"
    solver.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    solver.chmod(0o700)
    source = root / "source.json"
    reference_module = Path(__file__).resolve().parents[1] / "scripts" / "rectangular_poiseuille_reference.py"
    acceptance_script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_internal_nozzle_acceptance.py"
    profile_header = Path(__file__).resolve().parents[1] / "cases" / "basilisk" / "internal_nozzle_precursor_start.h"
    tracked_paths = (
        "cases/basilisk/rectangular_internal_nozzle_steady_precursor.c",
        "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c",
        "cases/basilisk/internal_nozzle_precursor_start.h",
        "scripts/rectangular_poiseuille_reference.py",
        "scripts/evaluate_internal_nozzle_acceptance.py",
    )
    tracked = []
    for index, path in enumerate(tracked_paths):
        file_sha = digest(reference_module) if path.endswith("rectangular_poiseuille_reference.py") else (
            digest(acceptance_script) if path.endswith("evaluate_internal_nozzle_acceptance.py")
            else digest(profile_header) if path.endswith("internal_nozzle_precursor_start.h")
            else f"{index + 1:064x}"
        )
        tracked.append({"path": path, "git_blob": f"{index + 1:040x}",
                        "git_mode": "100644", "size_bytes": 1, "sha256": file_sha})
    source.write_text(json.dumps({
        "schema": "internal_nozzle_source_bundle_v1", "scientific_commit": "a" * 40,
        "repository_root_name": "fixture", "tracked_behavior_files": tracked,
        "tracked_behavior_file_count": len(tracked),
        "prepared_centered": {"path": "/fixture/centered.h", "size_bytes": 1,
                              "sha256": "b" * 64,
                              "derivation": "exact_hash_gated_transform"},
        "basilisk": {"basilisk_timestep_path": "/fixture/timestep.h",
                     "basilisk_timestep_sha256": "b" * 64,
                     "basilisk_centered_path": "/fixture/base-centered.h",
                     "basilisk_centered_sha256": "b" * 64,
                     "qcc_path": "/fixture/qcc", "qcc_sha256": "b" * 64},
        "source_identity_semantics": "sha256_of_this_complete_manifest_file",
    }, sort_keys=True), encoding="utf-8")
    source_sha = digest(source)
    build_role = "profile_controlled" if role == "C" else "pressure_driven"
    entry = "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c"
    defines = ["INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1"]
    if role == "C":
        defines.append("INTERNAL_NOZZLE_PROFILE_CONTROLLED=1")
    build_manifest = root / "build.json"
    build_manifest.write_text(json.dumps({
        "schema": "internal_nozzle_observable_qcc_build_v1",
        "scientific_commit": "a" * 40, "source_bundle_path": str(source.resolve()),
        "source_bundle_sha256": source_sha, "build_role": build_role,
        "entry_source": entry, "required_defines": defines,
        "compile_identity_semantics":
            "observable_qcc_exact_entry_source_role_defines_and_immutable_inputs",
        "compile_run_id": f"qcc-{role}", "compile_argv": ["qcc", entry],
        "compile_terminal": {"path": "/fixture/terminal.json", "sha256": "d" * 64,
                             "exit_code": 0, "terminal_state": "normal_exit"},
        "binary": {"path": str(solver.resolve()), "size_bytes": solver.stat().st_size,
                   "sha256": digest(solver)}, "verified_input_count": 1,
    }, sort_keys=True), encoding="utf-8")
    schedule = root / "run_schedule_contract.json"
    schedule.write_text(json.dumps({
        "schema": MODULE.SCHEDULE_SCHEMA, "schedule_version": "steady-r2-v1",
        "master_tick_dt": 0.01, "event_time_tolerance": 1e-12,
        "lightweight": {"base_stride": 2, "dense_stride": 1},
        "full_field": {"base_stride": 8, "dense_stride": 4},
        "checkpoint_stride": 6,
        "dense_window": {"start_tick": 2, "end_tick": 12},
    }, sort_keys=True), encoding="utf-8")
    transfer = manifest = report = projection_criteria = None
    profile_evidence = profile_acceptance = None
    profile_evidence_sha = profile_acceptance_sha = None
    manifest_sha = report_sha = projection_criteria_sha = None
    if role != "A":
        transfer = root / "transfer.csv"
        transfer.write_text(
            "x,y,z,level,Delta,cs,f,ux,uy,uz,p\n0,0,0,1,1,1,1,1,0,0,2\n",
            encoding="utf-8",
        )
        history = root / "precursor_history.csv"
        row = {name: "0" for name in MODULE.PRECURSOR_HISTORY_FIELDS}
        row.update({"case_id": "precursor", "t_star": "4", "Q_l": "2",
                    "exit_area": "4", "U_bulk": "0.5", "restart_state": "fresh"})
        with history.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=MODULE.PRECURSOR_HISTORY_FIELDS)
            writer.writeheader()
            writer.writerow(row)
        report = root / "convergence.json"
        report.write_text(json.dumps({
            "schema": "internal_nozzle_precursor_convergence_v1",
            "classification": "precursor_converged", "pass": True,
            "case_id": "precursor",
            "inputs": [{"history": {
                "path": str(history.resolve()),
                "resolved_path": str(history.resolve()),
                "sha256": digest(history),
                "size_bytes": history.stat().st_size,
                "rows": 1,
                "first_t_star": 4.0,
                "last_t_star": 4.0,
            }}],
            "combined_unique_sample_count": 3,
            "window": {"end_t_star": 4.0}, "fixed_scientific_thresholds": {},
            "declared_operational_bounds": {}, "metrics": {}, "auxiliary": {},
            "failures": [], "claim_boundary": "test",
        }, sort_keys=True), encoding="utf-8")
        report_sha = digest(report)
        manifest = root / "transfer.json"
        hashes = {name: "c" * 64 for name in (
            "source_sha256", "producer_unsealed_metadata_sha256",
            "precursor_checkpoint_sha256", "precursor_checkpoint_sidecar_sha256",
            "precursor_checkpoint_closure_sha256", "final_run_contract_sha256",
            "source_table_sha256", "target_template_sha256",
        )}
        manifest.write_text(json.dumps({
            "schema": MODULE.TRANSFER_SCHEMA, "method": MODULE.TRANSFER_METHOD,
            "source_field_sampling": MODULE.TARGET_SAMPLING_METHOD,
            "target_exit_clamp_rule": MODULE.TARGET_CLAMP_RULE,
            "additional_interpolation_by_preparer": False,
            "precursor_convergence_classification": "precursor_converged",
            "source_commit": "a" * 40, "transfer_table_sha256": digest(transfer),
            "precursor_convergence_report_sha256": report_sha,
            "final_history_sha256": digest(history), "coverage_fraction": 1.0,
            "target_leaf_count": 1, "loaded_leaf_count": 1,
            "unused_source_rows": 0, "target_exit_clamp_count": 0, **hashes,
        }, sort_keys=True), encoding="utf-8")
        manifest_sha = digest(manifest)
        projection_criteria = root / "projection-criteria.json"
        acceptance = MODULE.acceptance_module()
        velocity_scale = 0.5
        dimensional_scales = {
            "divergence_l2": velocity_scale / acceptance.PROJECTION_LENGTH_SCALE,
            "divergence_max": velocity_scale / acceptance.PROJECTION_LENGTH_SCALE,
            "velocity_impulse_l2": velocity_scale,
            "cell_pressure_change_l2": acceptance.PROJECTION_PRESSURE_SCALE,
            "projection_pressure_adjustment_l2": acceptance.PROJECTION_PRESSURE_SCALE,
        }
        projection_criteria.write_text(json.dumps({
            "schema": "internal_nozzle_transfer_projection_criteria_v1",
            "criteria_id": "task04-fixed-test", "applicable_case_roles": ["B", "C"],
            "phase_selection": "records_0_and_1_immediate_transfer_projection_only",
            "divergence_convention":
                "basilisk_face_flux_difference_over_Delta;uf_already_contains_face_metric",
            "normalization": {
                "length_scale": acceptance.PROJECTION_LENGTH_SCALE,
                "velocity_scale": velocity_scale,
                "pressure_scale": acceptance.PROJECTION_PRESSURE_SCALE,
            },
            "metrics": {metric: {"aggregation": "max_over_selected_records",
                                  "operator": "<=",
                                  "limit": acceptance.PROJECTION_NORMALIZED_LIMITS[metric] *
                                  dimensional_scales[metric]}
                        for metric in acceptance.PROJECTION_METRICS},
            "claim_boundary": "fixture pre-run criteria",
        }, sort_keys=True), encoding="utf-8")
        projection_criteria_sha = digest(projection_criteria)
    reference_artifact = None
    reference_artifact_sha = reference_module_sha = None
    if role == "C":
        reference_artifact = root / "reference.json"
        reference_artifact.write_text(json.dumps({
            "schema": "rectangular_poiseuille_reference_v1", "equation": "fixture",
            "boundary_condition": "no_slip_all_four_walls",
            "normalization": "width=2,height=1,pressure_gradient=1,viscosity=1",
            "metrics": {"width": 2.0, "height": 1.0, "modes": 256,
                        "quadrature_order": 256, "bulk_velocity": 0.057170419279962276},
            "series_convergence": [], "conductance_series_convergence": [],
            "independent_five_point_poisson": [], "claim_boundary": "fixture",
        }, sort_keys=True), encoding="utf-8")
        reference_artifact_sha = digest(reference_artifact)
        reference_module_sha = digest(reference_module)
        profile_evidence = root / "poiseuille_profile_validation.csv"
        profile_acceptance = root / "poiseuille_profile_acceptance.json"
        acceptance = MODULE.acceptance_module()
        _, _, _, authority = acceptance.load_profile_authority(
            source, source_sha, reference_artifact, reference_artifact_sha,
            reference_module, reference_module_sha,
        )
        rows, characterization = acceptance.profile_rows_and_characterization(
            authority["bulk_velocity"],
        )
        acceptance.write_profile_evidence(profile_evidence, rows)
        profile_evidence_sha = digest(profile_evidence)
        acceptance.atomic_json(profile_acceptance, acceptance.expected_profile_acceptance(
            source.resolve(), source_sha, tracked[2]["sha256"],
            authority["c_profile_function_sha256"],
            reference_artifact.resolve(), reference_artifact_sha,
            reference_module.resolve(), reference_module_sha,
            profile_evidence.resolve(), characterization,
        ))
        profile_acceptance_sha = digest(profile_acceptance)
    supervisor = Path(__file__).resolve().parents[1] / "scripts" / "supervise_internal_nozzle_run.py"
    segment = f"case-{role.lower()}-s0"
    return argparse.Namespace(
        case_role=role, execution_id=f"case-{role.lower()}-execution", segment_id=segment,
        run_id=segment, cwd=root, supervisor=supervisor,
        supervisor_sha256=digest(supervisor), python_executable=sys.executable,
        evidence_dir=root / "supervision" / segment,
        lock_root=batch_root / ".internal-nozzle-one-solver",
        batch_root=batch_root, batch_id=batch_id,
        timeout_seconds=10.0, heartbeat_seconds=0.1,
        source_commit="a" * 40, source_sha256=source_sha,
        source_bundle_manifest=source, source_bundle_manifest_sha256=source_sha,
        build_manifest=build_manifest, build_manifest_sha256=digest(build_manifest),
        schedule=schedule, schedule_sha256=digest(schedule),
        schedule_version="steady-r2-v1", solver_sha256=digest(solver),
        transfer=transfer, transfer_manifest=manifest,
        transfer_manifest_sha256=manifest_sha,
        precursor_convergence_report=report,
        precursor_convergence_report_sha256=report_sha,
        projection_criteria=projection_criteria,
        projection_criteria_sha256=projection_criteria_sha,
        poiseuille_profile_evidence=profile_evidence,
        poiseuille_profile_evidence_sha256=profile_evidence_sha,
        poiseuille_profile_acceptance=profile_acceptance,
        poiseuille_profile_acceptance_sha256=profile_acceptance_sha,
        poiseuille_reference_artifact=reference_artifact,
        poiseuille_reference_artifact_sha256=reference_artifact_sha,
        poiseuille_reference_module=reference_module if role == "C" else None,
        poiseuille_reference_module_sha256=reference_module_sha,
        restore=None, restore_sha256=None, restore_metadata_sha256=None,
        restore_closure_sha256=None, predecessor_segment_id=None,
        output=root / f"scientific_launch_contract.{segment}.json",
        solver_argv=["--", str(solver), "--case-id", f"case-{role.lower()}",
                     "--domain", "full", "--output-dir", str(root)],
    )


@pytest.mark.parametrize("role", "ABC")
def test_role_specific_identity_and_schedule_are_injected(tmp_path: Path, role: str) -> None:
    args = fixture(tmp_path, role)
    payload = MODULE.build_contract(args)
    argv = payload["solver_argv"]
    assert MODULE.required_solver_option(argv, "--execution-id") == args.execution_id
    assert MODULE.required_solver_option(argv, "--segment-id") == args.segment_id
    assert MODULE.required_solver_option(argv, "--case-role") == role
    assert MODULE.required_solver_option(argv, "--schedule-tick-dt") == "0.01"
    if role == "A":
        assert "--precursor-transfer" not in argv
    else:
        assert MODULE.required_solver_option(argv, "--precursor-transfer") == str(args.transfer.resolve())
        assert payload["precursor_bulk_target"]["bulk_velocity"] == 0.5
    if role == "C":
        assert MODULE.required_solver_option(argv, "--profile-bulk-velocity") == "0.5"
        assert payload["poiseuille_profile_validation"]["pass"] is True


def test_schedule_and_convergence_tampering_fail_closed(tmp_path: Path) -> None:
    args = fixture(tmp_path)
    args.schedule.write_text("{}", encoding="utf-8")
    args.schedule_sha256 = digest(args.schedule)
    with pytest.raises(ValueError, match="schedule"):
        MODULE.build_contract(args)


def test_convergence_history_summary_tampering_fails_closed(tmp_path: Path) -> None:
    args = fixture(tmp_path)
    report = json.loads(args.precursor_convergence_report.read_text(encoding="utf-8"))
    report["inputs"][-1]["history"]["rows"] = 2
    args.precursor_convergence_report.write_text(json.dumps(report), encoding="utf-8")
    report_sha = digest(args.precursor_convergence_report)
    args.precursor_convergence_report_sha256 = report_sha
    manifest = json.loads(args.transfer_manifest.read_text(encoding="utf-8"))
    manifest["precursor_convergence_report_sha256"] = report_sha
    args.transfer_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    args.transfer_manifest_sha256 = digest(args.transfer_manifest)
    with pytest.raises(ValueError, match="row count mismatch"):
        MODULE.build_contract(args)


def test_projection_criteria_cannot_inflate_fixed_normalized_limit(tmp_path: Path) -> None:
    args = fixture(tmp_path)
    payload = json.loads(args.projection_criteria.read_text(encoding="utf-8"))
    payload["metrics"]["divergence_l2"]["limit"] = 1.0e9
    args.projection_criteria.write_text(json.dumps(payload), encoding="utf-8")
    args.projection_criteria_sha256 = digest(args.projection_criteria)
    with pytest.raises(ValueError, match="fixed normalized limit"):
        MODULE.build_contract(args)


def test_projection_velocity_scale_must_equal_precursor_bulk_state(tmp_path: Path) -> None:
    args = fixture(tmp_path)
    payload = json.loads(args.projection_criteria.read_text(encoding="utf-8"))
    payload["normalization"]["velocity_scale"] = 0.6
    acceptance = MODULE.acceptance_module()
    scales = {
        "divergence_l2": 0.6 / acceptance.PROJECTION_LENGTH_SCALE,
        "divergence_max": 0.6 / acceptance.PROJECTION_LENGTH_SCALE,
        "velocity_impulse_l2": 0.6,
        "cell_pressure_change_l2": acceptance.PROJECTION_PRESSURE_SCALE,
        "projection_pressure_adjustment_l2": acceptance.PROJECTION_PRESSURE_SCALE,
    }
    for metric, scale in scales.items():
        payload["metrics"][metric]["limit"] = (
            acceptance.PROJECTION_NORMALIZED_LIMITS[metric] * scale
        )
    args.projection_criteria.write_text(json.dumps(payload), encoding="utf-8")
    args.projection_criteria_sha256 = digest(args.projection_criteria)
    with pytest.raises(ValueError, match="does not equal precursor Q/A"):
        MODULE.build_contract(args)
    args = fixture(tmp_path / "second")
    args.precursor_convergence_report_sha256 = "0" * 64
    with pytest.raises(ValueError, match="convergence report SHA-256"):
        MODULE.build_contract(args)


def test_main_runs_strict_v2_supervision(tmp_path: Path) -> None:
    args = fixture(tmp_path)
    argv = [
        "--case-role", args.case_role, "--execution-id", args.execution_id,
        "--segment-id", args.segment_id, "--run-id", args.run_id,
        "--supervisor", str(args.supervisor), "--supervisor-sha256", args.supervisor_sha256,
        "--cwd", str(args.cwd), "--evidence-dir", str(args.evidence_dir),
        "--lock-root", str(args.lock_root), "--batch-root", str(args.batch_root),
        "--batch-id", args.batch_id, "--timeout-seconds", "10",
        "--source-commit", args.source_commit, "--source-sha256", args.source_sha256,
        "--source-bundle-manifest", str(args.source_bundle_manifest),
        "--source-bundle-manifest-sha256", args.source_bundle_manifest_sha256,
        "--build-manifest", str(args.build_manifest),
        "--build-manifest-sha256", args.build_manifest_sha256,
        "--schedule", str(args.schedule), "--schedule-sha256", args.schedule_sha256,
        "--schedule-version", args.schedule_version, "--solver-sha256", args.solver_sha256,
        "--transfer", str(args.transfer), "--transfer-manifest", str(args.transfer_manifest),
        "--transfer-manifest-sha256", args.transfer_manifest_sha256,
        "--precursor-convergence-report", str(args.precursor_convergence_report),
        "--precursor-convergence-report-sha256", args.precursor_convergence_report_sha256,
        "--projection-criteria", str(args.projection_criteria),
        "--projection-criteria-sha256", args.projection_criteria_sha256,
        "--output", str(args.output), "--", *args.solver_argv[1:],
    ]
    assert MODULE.main(argv) == 0
    terminal = json.loads((args.evidence_dir / "terminal.json").read_text())
    assert terminal["execution_id"] == args.execution_id
    assert terminal["segment_id"] == terminal["run_id"] == args.segment_id


def test_case_c_rejects_unbound_profile_acceptance(tmp_path: Path) -> None:
    args = fixture(tmp_path, "C")
    acceptance = json.loads(args.poiseuille_profile_acceptance.read_text())
    acceptance["predicates"][0]["observed"] = 0.5
    args.poiseuille_profile_acceptance.write_text(json.dumps(acceptance))
    args.poiseuille_profile_acceptance_sha256 = digest(args.poiseuille_profile_acceptance)
    with pytest.raises(ValueError, match="deterministic Task02 result"):
        MODULE.build_contract(args)
