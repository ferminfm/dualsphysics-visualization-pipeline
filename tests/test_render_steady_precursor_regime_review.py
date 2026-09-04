import csv
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "render_steady_precursor_regime_review.py"
SPEC = importlib.util.spec_from_file_location("steady_visual", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

CASE_COMMIT = "a" * 40
PRECURSOR_COMMIT = "c" * 40
SOURCE_SHA = "b" * 64
DH = 0.13925712636838891
EXIT_X = 15.0 * DH


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, names: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def record(path: Path) -> dict[str, object]:
    return {"path": path.name, "size_bytes": path.stat().st_size, "sha256": digest(path)}


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.reference = root / "reference"
        self.precursor = root / "precursor"
        self.profile = root / "profile-comparison"
        self.cases = {role: root / f"case-{role.lower()}" for role in "ABC"}
        self.comparison = root / "comparison.json"
        self.reference_module = root / "reference_module.py"
        self.output = root / "human-visual-review"
        self._reference()
        self._precursor()
        for role in "ABC":
            self._case(role)
        write_json(self.comparison, {
            "schema": "steady_precursor_matched_comparison_v2",
            "common_horizon": {"master_tick": 40, "t_star": 4.0},
        })

    def _reference(self) -> None:
        self.reference.mkdir()
        write_json(self.reference / "reference.json", {
            "schema": "rectangular_poiseuille_reference_v1",
            "metrics": {"bulk_velocity": 0.5},
        })
        write_csv(self.reference / "long_axis_cut.csv", ["y", "velocity"], [
            {"y": -1 + i / 10, "velocity": max(0, 0.75 * (1 - (-1 + i / 10) ** 2))}
            for i in range(21)
        ])
        write_csv(self.reference / "short_axis_cut.csv", ["z", "velocity"], [
            {"z": -.5 + i / 20, "velocity": max(0, 0.75 * (1 - 4 * (-.5 + i / 20) ** 2))}
            for i in range(21)
        ])
        self.reference_module.write_text(
            "import numpy as np\n"
            "def velocity(y,z,modes=256):\n"
            "    y=np.asarray(y); z=np.asarray(z); return .75*np.maximum(0,1-y*y)*np.maximum(0,1-4*z*z)\n",
            encoding="utf-8",
        )

    def _precursor(self) -> None:
        self.precursor.mkdir()
        history = []
        for i in range(21):
            history.append({
                "case_id": "precursor", "t": i * .01, "t_star": i * .1, "i": i,
                "Q_l": 1 + .01 / (i + 1), "mdot_l": 1, "J_k": 1.3,
                "pressure_drop": 10, "exit_area": 1, "U_bulk": 1,
                "beta": 1.34, "alpha": 2.03, "mass_flow_imbalance": .001,
                "profile_l2_change": -1 if i == 0 else .001 / i,
                "max_ux_change": .001, "mgp_iterations": 2, "mgu_iterations": 3,
                "mgp_residual": 1e-4, "mgu_residual": 1e-6,
                "cell_count": 100, "restart_state": "fresh",
            })
        write_csv(self.precursor / "precursor_history.csv", list(history[0]), history)
        write_csv(self.precursor / "precursor-transfer-cells.csv",
                  ["source_cell_id", "x", "y", "z", "Delta", "cs", "ux", "uy", "uz", "p"],
                  [{"source_cell_id": 0, "x": 1, "y": 0, "z": 0, "Delta": .1,
                    "cs": 1, "ux": 1, "uy": 0, "uz": 0, "p": 5}])
        write_json(self.precursor / "precursor-transfer-unsealed.json", {
            "schema": "internal_nozzle_precursor_unsealed_export_v2",
            "source_commit": PRECURSOR_COMMIT,
        })
        write_json(self.precursor / "precursor-convergence.json", {
            "schema": "internal_nozzle_precursor_convergence_v1", "pass": True,
        })

        self.profile.mkdir()
        write_json(self.profile / "precursor-poiseuille-profile-comparison.json", {
            "schema": "internal_nozzle_precursor_profile_comparison_v1",
            "source_commit": PRECURSOR_COMMIT,
        })
        rows = []
        for index, (y0, z0) in enumerate(((-1, -.5), (0, -.5), (-1, 0), (0, 0))):
            reference = 0.1 + index * .3
            rows.append({
                "plane_label": "near_exit", "plane_dh": 14.5, "plane_x": 2,
                "source_cell_id": index, "x": 2, "y": y0 + .5, "z": z0 + .25,
                "Delta": 1, "cs": 1, "area_weight": .5, "numerical_ux": reference * 1.02,
                "numerical_uy": 0, "numerical_uz": 0,
                "numerical_u_over_bulk": reference * 1.02,
                "reference_cell_average": reference * .5, "reference_normalized": reference,
                "normalized_difference": reference * .02,
                "y_lower": y0, "y_upper": y0 + 1, "z_lower": z0, "z_upper": z0 + .5,
            })
        write_csv(self.profile / "precursor-poiseuille-profile-samples.csv", list(rows[0]), rows)

    def _case(self, role: str) -> None:
        root = self.cases[role]
        (root / "fields").mkdir(parents=True)
        schedule = {
            "schema": "internal_nozzle_launch_schedule_v1",
            "schedule_version": "steady_r2_matched_tstar4_v1",
            "master_tick_dt": 0.1 * DH,
        }
        write_json(root / "run_schedule_contract.json", schedule)
        schedule_sha = digest(root / "run_schedule_contract.json")
        metrics = []
        for tick in range(41):
            metrics.append({
                "case_id": f"case-{role}", "plane_label": "geometric_nozzle_exit",
                "plane_x_Dh": 15, "Q_l": 1 + .01 * tick + .1 * ord(role),
                "J_k_liquid": 1.3 + .01 * tick, "J_p": .2, "J_total": 1.5 + .01 * tick,
                "beta": 1.34, "alpha": 2.03, "actual_time": tick * .1 * DH,
                "master_tick": tick, "case_role": role,
            })
        write_csv(root / "hydraulic_plane_metrics.csv", list(metrics[0]), metrics)
        profiles = []
        manifest_rows = []
        for frame_index, tick in enumerate((0, 20, 40)):
            t = tick * .1 * DH
            field = root / "fields" / f"field_tick_{tick:03d}.csv"
            field_rows = []
            for index, (x, y) in enumerate(((0.1, -.1), (1.0, .1), (2.0, -.05), (3.0, .05))):
                field_rows.append({
                    "case_id": f"case-{role}", "x": x, "y": y, "z": 0,
                    "f": 1 if x < 2.5 else .25, "ux": .1 * (ord(role) - 63) + .01 * tick + index * .02,
                    "p": 10 * (ord(role) - 64) + tick + x, "cs": 1, "Delta": .2,
                    "master_tick": tick, "source_sha256": SOURCE_SHA,
                    "schedule_sha256": schedule_sha,
                })
            write_csv(field, list(field_rows[0]), field_rows)
            manifest_rows.append({
                "case_id": f"case-{role}", "domain_mode": "full", "field_frame_index": frame_index,
                "t": t, "i": tick, "filename": f"fields/{field.name}", "sample_count": len(field_rows),
                "source_sha256": SOURCE_SHA, "schedule_version": schedule["schedule_version"],
                "schedule_sha256": schedule_sha, "master_tick": tick, "target_time": t,
                "actual_time": t,
            })
            for j, (y, z) in enumerate(((-.05, -.02), (.05, -.02), (-.05, .02), (.05, .02))):
                profiles.append({
                    "case_id": f"case-{role}", "t": t, "field_frame_index": frame_index,
                    "i": tick, "plane_label": "geometric_nozzle_exit", "plane_x_Dh": 15,
                    "plane_x": EXIT_X, "x": EXIT_X, "y": y, "z": z, "f": 1,
                    "ux": .1 * (ord(role) - 63) + .01 * tick + j * .02, "uy": 0, "uz": 0,
                    "p": 0, "cs": 1, "level": 8, "Delta": .05,
                    "intersection_area": .0025, "case_role": role,
                })
        write_csv(root / "field_frame_manifest.csv", list(manifest_rows[0]), manifest_rows)
        write_csv(root / "hydraulic_plane_profiles.csv", list(profiles[0]), profiles)
        write_csv(root / "solver_health_metrics.csv", ["case_id", "case_role", "t", "total_grid_cells"], [
            {"case_id": f"case-{role}", "case_role": role, "t": 0, "total_grid_cells": 100}
        ])
        write_json(root / "raw_export_manifest.json", {
            "files": {"field_manifest": "field_frame_manifest.csv"}
        })
        if role in "BC":
            projection = []
            for index, phase in enumerate(("pre_projection_input", "pre_advection_closure",
                                           "post_timestep_projection", "post_timestep_projection")):
                projection.append({
                    "case_id": f"case-{role}", "record_index": index, "phase": phase,
                    "t": 0, "i": index, "divergence_l2": 1e-4 / (index + 1),
                    "divergence_max": 1e-3 / (index + 1), "velocity_impulse_l2": 1e-5,
                    "cell_pressure_change_l2": 1e-4, "projection_pressure_adjustment_l2": 1e-4,
                })
            write_csv(root / "precursor_transfer_projection.csv", list(projection[0]), projection)
            write_json(root / "precursor_transfer_projection_acceptance.json", {"pass": True})
        if role == "C":
            write_csv(root / "poiseuille_profile_validation.csv", ["sample", "value"], [{"sample": 0, "value": 1}])
            write_json(root / "poiseuille_profile_acceptance.json", {"pass": True})

        member_names = [
            "hydraulic_plane_metrics.csv", "hydraulic_plane_profiles.csv",
            "solver_health_metrics.csv", "run_schedule_contract.json", "raw_export_manifest.json",
        ]
        if role in "BC":
            member_names += ["precursor_transfer_projection.csv",
                             "precursor_transfer_projection_acceptance.json"]
        if role == "C":
            member_names += ["poiseuille_profile_validation.csv",
                             "poiseuille_profile_acceptance.json"]
        package = {
            "schema": "sealed_internal_nozzle_case_package_v2", "case_role": role,
            "case_id": f"case-{role}", "run_root": str(root.resolve()),
            "scientific_source_commit": CASE_COMMIT, "source_sha256": SOURCE_SHA,
            "schedule_sha256": schedule_sha, "schedule_version": schedule["schedule_version"],
            "members": {name: record(root / name) for name in member_names},
        }
        write_json(root / "sealed_case_package.json", package)

    def argv(self) -> list[str]:
        values = [
            "--reference-dir", str(self.reference),
            "--reference-module", str(self.reference_module),
            "--precursor-run-root", str(self.precursor),
            "--precursor-profile-dir", str(self.profile),
        ]
        for role in "abc":
            root = self.cases[role.upper()]
            values += [f"--case-{role}-root", str(root),
                       f"--case-{role}-package", str(root / "sealed_case_package.json")]
        values += [
            "--comparison", str(self.comparison), "--master-ticks", "0,20,40",
            "--dh", str(DH), "--exit-x", str(EXIT_X),
            "--expected-case-scientific-commit", CASE_COMMIT,
            "--expected-precursor-scientific-commit", PRECURSOR_COMMIT,
            "--output-root", str(self.output),
        ]
        return values


class VisualReviewTests(unittest.TestCase):
    def test_end_to_end_render_and_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            self.assertEqual(MODULE.main(fixture.argv()), 0)
            manifest = json.loads((fixture.output / "visual-package-manifest.json").read_text())
            self.assertTrue(manifest["global_scales"]["shared_across_cases"])
            self.assertEqual(manifest["selected_master_ticks"], [0, 20, 40])
            self.assertEqual(manifest["matched_case_scientific_commit"], CASE_COMMIT)
            self.assertEqual(manifest["precursor_scientific_commit"], PRECURSOR_COMMIT)
            self.assertTrue(any(
                item["path"] == str(SCRIPT.resolve()) and item["sha256"] == digest(SCRIPT)
                for item in manifest["inputs"]
            ))
            self.assertEqual(manifest["videos"]["status"], "not_generated")
            self.assertEqual(manifest["review_first"], list(MODULE.REVIEW_FIRST))
            self.assertGreaterEqual(manifest["member_count"], 14)
            self.assertEqual(MODULE.main([
                "--validate-only", "--output-root", str(fixture.output),
                "--manifest", str(fixture.output / "visual-package-manifest.json"),
            ]), 0)

    def test_wrong_case_role_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            path = fixture.cases["B"] / "sealed_case_package.json"
            payload = json.loads(path.read_text())
            payload["case_role"] = "A"
            write_json(path, payload)
            with self.assertRaisesRegex(ValueError, "schema/role mismatch"):
                MODULE.main(fixture.argv())

    def test_wrong_precursor_commit_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            argv = fixture.argv()
            index = argv.index("--expected-precursor-scientific-commit") + 1
            argv[index] = "d" * 40
            with self.assertRaisesRegex(ValueError, "precursor metadata identity mismatch"):
                MODULE.main(argv)

    def test_missing_selected_tick_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            path = fixture.cases["C"] / "field_frame_manifest.csv"
            rows = list(csv.DictReader(path.open()))
            write_csv(path, list(rows[0]), [row for row in rows if row["master_tick"] != "20"])
            with self.assertRaisesRegex(ValueError, "missing selected master ticks"):
                MODULE.main(fixture.argv())

    def test_unrelated_tick_set_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            argv = fixture.argv()
            index = argv.index("--master-ticks") + 1
            argv[index] = "0,10,40"
            with self.assertRaisesRegex(ValueError, "exactly master ticks"):
                MODULE.main(argv)

    def test_validate_detects_changed_image(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            MODULE.main(fixture.argv())
            target = fixture.output / MODULE.REVIEW_FIRST[0]
            target.write_bytes(target.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "manifest identity mismatch"):
                MODULE.main([
                    "--validate-only", "--output-root", str(fixture.output),
                    "--manifest", str(fixture.output / "visual-package-manifest.json"),
                ])


if __name__ == "__main__":
    unittest.main()
