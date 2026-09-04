import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_internal_nozzle_precursor_restart.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("compare_precursor_restart", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def closure_report(path: Path) -> dict[str, object]:
    metadata = MODULE.read_metadata(Path(str(path).replace(
        ".prediction-closure-v4", ".meta"
    )))
    return {
        "valid": True,
        "source_sha256": metadata["source_sha256"],
        "schedule_version": MODULE.PRECURSOR_SCHEDULE_VERSION,
        "schedule_sha256": MODULE.PRECURSOR_SCHEDULE_SHA256,
        "iteration": int(metadata["i"]),
        "grid_maxdepth": int(metadata["maxlevel"]),
        "checkpoint_t": float(metadata["t"]), "checkpoint_dt": 0.01,
        "checkpoint_dtmax": 0.02, "timestep_previous": 0.01,
        "domain": [0.0, -1.0, -1.0, 2.0],
    }


def history_row(t: float, iteration: int, restart_state: str) -> dict[str, object]:
    fields = ("case_id", "t", "t_star", "i", *MODULE.HISTORY_FIELDS,
              "restart_state")
    row = {field: 1 for field in fields}
    row.update({"case_id": "precursor", "t": t, "t_star": 2 * t,
                "i": iteration, "restart_state": restart_state})
    return row


def make_run(
    root: Path, rows: list[dict[str, object]], *, target: Path,
    predecessor: Path | None = None, ux: float = 2.0,
) -> Path:
    root.mkdir(parents=True)
    contract = {
        "schema": "internal_nozzle_precursor_run_v1", "case_id": "precursor",
        "geometry_schema": "g1", "geometry_fingerprint": "w2",
        "source_commit": "a" * 40, "source_sha256": "b" * 64,
        "pressure_forcing": 351.48, "density_liquid": 1.0,
        "viscosity_liquid": 1.0, "maxlevel": 7, "baselevel": 4,
        "delta_min_Dh": 0.1, "accepted_physical_L7_delta_Dh": 0.1,
        "dt_cap": 0.02, "metric_stride": 10,
        "target_template": str(target.resolve()),
        "restore_checkpoint": (
            str((predecessor / "precursor-final.dump").resolve())
            if predecessor else "not_applicable"
        ),
        "restore_metadata": (
            str((predecessor / "precursor-final.dump.meta").resolve())
            if predecessor else "not_applicable"
        ),
    }
    (root / "run_contract.json").write_text(json.dumps(contract), encoding="utf-8")
    endpoint = rows[-1]
    (root / "precursor-final.dump").write_bytes(
        f"dump:{endpoint['t']}:{endpoint['i']}".encode("ascii")
    )
    (root / "precursor-final.dump.prediction-closure-v4").write_bytes(
        f"closure:{endpoint['t']}:{endpoint['i']}".encode("ascii")
    )
    metadata = {
        "schema": "internal_nozzle_precursor_checkpoint_v2", "case_id": "precursor",
        "geometry_fingerprint": "w2", "source_commit": "a" * 40,
        "source_sha256": "b" * 64, "maxlevel": "7",
        "pressure_forcing": "351.48", "density_liquid": "1",
        "viscosity_liquid": "1", "t": str(endpoint["t"]),
        "t_star": str(endpoint["t_star"]), "i": str(endpoint["i"]),
        "solver_dt": "0.01", "solver_dtmax": "0.02",
        "timestep_previous": "0.01", "previous_profile_available": "1",
        "prediction_closure_schema": "internal_nozzle_prediction_closure_v4",
        "prediction_closure_state": "precursor-final.dump.prediction-closure-v4",
    }
    (root / "precursor-final.dump.meta").write_text(
        "".join(f"{key}={value}\n" for key, value in metadata.items()), encoding="utf-8")
    cell_fields = ("source_cell_id", *MODULE.CELL_KEY, *MODULE.CELL_FIELDS)
    write_csv(root / "precursor-transfer-cells.csv", cell_fields, [{
        "source_cell_id": 0, "x": 0, "y": 0, "z": 0, "Delta": 0.1,
        "cs": 1, "ux": ux, "uy": 0, "uz": 0, "p": 5,
    }])
    history_fields = ("case_id", "t", "t_star", "i", *MODULE.HISTORY_FIELDS,
                      "restart_state")
    write_csv(root / "precursor_history.csv", history_fields, rows)
    plane_fields = ("case_id", "t", "t_star", "i", "plane_label", "plane_dh",
                    *MODULE.PLANE_FIELDS)
    plane = {field: 1 for field in plane_fields}
    plane.update({"case_id": "precursor", "t": endpoint["t"],
                  "t_star": endpoint["t_star"], "i": endpoint["i"],
                  "plane_label": "near_exit", "plane_dh": 14.5})
    write_csv(root / "precursor_plane_history.csv", plane_fields, [plane])
    return root


def make_triplet(tmp_path: Path, *, restored_ux: float = 2.0) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "target-template.csv"
    target.write_text("x,y,z,level,Delta,cs,f\n", encoding="utf-8")
    continuous = make_run(
        tmp_path / "continuous",
        [history_row(0.0, 0, "fresh"), history_row(0.5, 10, "fresh"),
         history_row(1.0, 20, "fresh")],
        target=target,
    )
    split = make_run(
        tmp_path / "split",
        [history_row(0.0, 0, "fresh"), history_row(0.5, 10, "fresh")],
        target=target,
    )
    restored = make_run(
        tmp_path / "restored",
        [history_row(0.5, 10, "restored"),
         history_row(1.0, 20, "restored")],
        target=target,
        predecessor=split,
        ux=restored_ux,
    )
    return continuous, split, restored


def test_identical_continuous_and_restored_endpoints_pass(tmp_path: Path) -> None:
    continuous, split, restored = make_triplet(tmp_path)
    result = MODULE.compare_runs(continuous, restored, 1e-8, closure_report)
    assert result["passed"] is True
    assert result["restored_predecessor"]["kind"] == "authenticated_fresh_split_checkpoint"
    assert result["restored_predecessor"]["run_directory"] == str(split.resolve())
    assert result["cells"]["overall_maximum"] == 0.0


def test_hydraulic_or_field_difference_fails(tmp_path: Path) -> None:
    continuous, _split, restored = make_triplet(tmp_path, restored_ux=2.1)
    result = MODULE.compare_runs(continuous, restored, 1e-8, closure_report)
    assert result["passed"] is False
    assert result["cells"]["overall_maximum"] > 1e-8


def test_closure_metadata_identity_mismatch_fails(tmp_path: Path) -> None:
    continuous, _split, restored = make_triplet(tmp_path)
    bad = dict(closure_report(
        continuous / "precursor-final.dump.prediction-closure-v4"
    ))
    bad["iteration"] = 19
    with pytest.raises(ValueError, match="closure/metadata mismatch iteration"):
        MODULE.compare_runs(continuous, restored, 1e-8, lambda _path: bad)


def test_missing_predecessor_closure_fails(tmp_path: Path) -> None:
    continuous, split, restored = make_triplet(tmp_path)
    (split / "precursor-final.dump.prediction-closure-v4").unlink()
    with pytest.raises((ValueError, FileNotFoundError), match="nonempty regular|No such file"):
        MODULE.compare_runs(continuous, restored, 1e-8, closure_report)


def test_arbitrary_or_mismatched_split_predecessor_fails(tmp_path: Path) -> None:
    continuous, split, restored = make_triplet(tmp_path)
    (split / "run_contract.json").unlink()
    with pytest.raises(FileNotFoundError):
        MODULE.compare_runs(continuous, restored, 1e-8, closure_report)

    continuous, split, restored = make_triplet(tmp_path / "mismatch")
    rows = list(csv.DictReader((split / "precursor_history.csv").open(
        newline="", encoding="utf-8"
    )))
    rows[-1]["Q_l"] = "1.1"
    write_csv(
        split / "precursor_history.csv",
        ("case_id", "t", "t_star", "i", *MODULE.HISTORY_FIELDS, "restart_state"),
        rows,
    )
    restored_rows = list(csv.DictReader((restored / "precursor_history.csv").open(
        newline="", encoding="utf-8"
    )))
    restored_rows[0]["Q_l"] = "1.1"
    write_csv(
        restored / "precursor_history.csv",
        ("case_id", "t", "t_star", "i", *MODULE.HISTORY_FIELDS, "restart_state"),
        restored_rows,
    )
    with pytest.raises(ValueError, match="differs from continuous trajectory"):
        MODULE.compare_runs(continuous, restored, 1e-8, closure_report)


def test_sidecar_contract_template_and_duplicate_json_fail_closed(tmp_path: Path) -> None:
    continuous, split, restored = make_triplet(tmp_path)
    sidecar = split / "precursor-final.dump.meta"
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace(
            "source_commit=" + "a" * 40, "source_commit=" + "c" * 40
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metadata mismatch source_commit"):
        MODULE.compare_runs(continuous, restored, 1e-8, closure_report)

    continuous, _split, restored = make_triplet(tmp_path / "template")
    other = tmp_path / "other-template.csv"
    other.write_text("different\n", encoding="utf-8")
    contract_path = restored / "run_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["target_template"] = str(other.resolve())
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="do not share one identity"):
        MODULE.compare_runs(continuous, restored, 1e-8, closure_report)

    continuous, _split, restored = make_triplet(tmp_path / "duplicate")
    contract_path = restored / "run_contract.json"
    raw = contract_path.read_text(encoding="utf-8")
    contract_path.write_text(raw[:-1] + ',"case_id":"duplicate"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        MODULE.compare_runs(continuous, restored, 1e-8, closure_report)


def test_precursor_source_uses_keyed_closure_and_bound_sidecar() -> None:
    source = (Path(__file__).resolve().parents[1] / "cases" / "basilisk" /
              "rectangular_internal_nozzle_steady_precursor.c").read_text(encoding="utf-8")
    for token in (
        '#include "internal_nozzle_centered.h"',
        "compile through the hash-gated restartable centered-header preparation path",
        '#include "internal_nozzle_checkpoint_v4.h"',
        "internal_nozzle_precursor_checkpoint_v2",
        "prediction_closure_state=precursor-final.dump.prediction-closure-v4",
        "verify_restored_precursor_identity();",
        "internal_nozzle_restore_prediction_closure_v4(precursor_closure_path);",
        "internal_nozzle_timestep_restore_probe = 1;",
    ):
        assert token in source
    assert '#include "navier-stokes/centered.h"' not in source
    assert "iter != expected_restore_iteration" in source
    assert "iter = expected_restore_iteration" not in source


def test_two_phase_source_projects_homogeneous_transfer_correction_and_binds_closure() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "cases" / "basilisk" /
              "rectangular_internal_nozzle_convergence_visual.c").read_text(
                  encoding="utf-8")
    closure = (root / "cases" / "basilisk" /
               "internal_nozzle_checkpoint_v4.h").read_text(encoding="utf-8")
    pre_centered_event = source.index("event init (i = 0) {")
    centered_include = source.index('#include "internal_nozzle_centered.h"')
    case_init = source.index("event init (t = 0) {")
    post_centered_hook = source.index(
        "static void internal_nozzle_post_centered_init (void) {")
    assert pre_centered_event < centered_include < case_init < post_centered_hook
    assert '"pre_projection_input"' in source
    assert '"post_initial_projection"' in source
    assert "project(uf, pf, alpha, dt" not in source
    assert source.count("internal_nozzle_initial_projection_stats = project") == 1
    assert "internal_nozzle_transfer_projection_correction[left] = dirichlet(0.);" in source
    assert "internal_nozzle_transfer_projection_correction[right] = dirichlet(0.);" in source
    assert "internal_nozzle_transfer_projection_correction[left] = neumann(0.);" in source
    saved = source.index(
        "internal_nozzle_projection_nitermin_before = NITERMIN;", post_centered_hook,
    )
    raised = source.index("NITERMIN = internal_nozzle_projection_nitermin_during;", saved)
    projected = source.index("internal_nozzle_initial_projection_stats = project", raised)
    restored = source.index("NITERMIN = internal_nozzle_projection_nitermin_before;", projected)
    assert saved < raised < projected < restored
    assert "internal_nozzle_projection_nitermin_during = max(NITERMIN, 4);" in source
    assert "TOLERANCE = 1e-5;" in source
    assert "p[left] = dirichlet(pressure_value);" in source
    assert "p[left] = neumann(0.);" in source
    assert "p[right] = dirichlet(0.);" in source
    assert "centered_gradient(p, g);" in source
    assert "native_restore_iteration != found_iteration" in source
    assert "solver_dtmax=%.17g" in source
    assert "grid_maxdepth=%d" in source
    assert "ERROR duplicate two-phase checkpoint metadata key" in source
    assert "ERROR unknown or malformed two-phase checkpoint metadata key" in source
    # A continue inside the macro's do/while would only continue that inner
    # loop and reject every valid metadata line. Recognition is carried to
    # the enclosing fgets loop explicitly.
    parse_start = source.index("#define TWO_PHASE_META_SCAN")
    matched_decl = source.index("int matched_line = 0;", parse_start)
    matched_assignment = source.index("matched_line = 1;", parse_start)
    outer_continue = source.index("if (matched_line)", matched_decl)
    unknown_rejection = source.index(
        "ERROR unknown or malformed two-phase checkpoint metadata key",
        outer_continue,
    )
    assert matched_assignment < matched_decl < outer_continue < unknown_rejection
    # The v7 restart sidecar binds 59 exact keys, including execution,
    # segment, role, solver, predecessor, profile-flow, and cumulative-volume identity.
    assert "seen != ((1ULL << 59) - 1)" in source
    assert "internal_nozzle_verify_prediction_closure_identity_v4" in source
    assert "prediction-closure checkpoint/sidecar/domain identity mismatch" in closure
