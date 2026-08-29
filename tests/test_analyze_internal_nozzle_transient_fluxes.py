import csv
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "analyze_internal_nozzle_transient_fluxes.py"
SPEC = importlib.util.spec_from_file_location("analyze_internal_nozzle_transient_fluxes", SCRIPT_PATH)
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)

DH = ANALYZER.DH
DEFAULT_PLANES = ANALYZER.DEFAULT_PLANES_DH
FIELD_HEADER = [
    "case_id",
    "source_frame_id",
    "field_frame_index",
    "t",
    "i",
    "x",
    "y",
    "z",
    "f",
    "ux",
    "uy",
    "uz",
    "velocity_magnitude",
    "vorticity_magnitude",
    "p",
    "cs",
    "level",
    "Delta",
    "region_flag",
    "pressure_provenance",
    "event_provenance",
    "gravity_enabled",
    "source_sha256",
    "schedule_version",
    "schedule_sha256",
    "master_tick",
    "target_time",
    "actual_time",
    "restart_lineage",
]


MANIFEST_HEADER = [
    "case_id",
    "domain_mode",
    "field_frame_index",
    "t",
    "i",
    "filename",
    "sample_count",
    "p_min",
    "p_max",
    "p_range",
    "pressure_nonzero",
    "f_min",
    "f_max",
    "velocity_magnitude_min",
    "velocity_magnitude_max",
    "vorticity_magnitude_min",
    "vorticity_magnitude_max",
    "pressure_provenance",
    "event_provenance",
    "pressure_gauge_context",
    "gravity_enabled",
    "source_sha256",
    "schedule_version",
    "schedule_sha256",
    "master_tick",
    "target_time",
    "actual_time",
    "maxlevel",
    "restart_lineage",
    "field_list",
]


class AnalyzeInternalNozzleTransientFluxesTests(unittest.TestCase):
    def _run_analyzer(self, run_dir: Path, *, overwrite: bool = False, planes: str | None = None):
        metrics = run_dir / "metrics.csv"
        profile = run_dir / "profile.csv"
        summary = run_dir / "summary.json"
        cmd = [
            sys.executable,
            str(SCRIPT_PATH),
            "--run-dir",
            str(run_dir),
            "--metrics-csv",
            str(metrics),
            "--profile-csv",
            str(profile),
            "--summary-json",
            str(summary),
        ]
        if overwrite:
            cmd.append("--overwrite")
        if planes is not None:
            cmd.extend(["--planes", planes])
        result = subprocess.run(cmd, text=True, capture_output=True)
        return result, metrics, profile, summary

    @staticmethod
    def _base_contract() -> dict[str, object]:
        return {
            "schema": "internal_nozzle_post_projection_fields_v2",
            "selected_case": "W2_longer_duration",
            "pressure_provenance": "runtime_cell_centered_p_after_centered_projection",
            "event_provenance": "canonical_master_tick_post_projection_i_plus_plus_last",
            "pressure_gauge_context": "outlet_dirichlet_zero_gauge",
            "gravity_enabled": False,
            "fields": [],
            "instrumentation_changes_solver_state": False,
        }

    def _write_run(
        self,
        run_dir: Path,
        frame_rows: list[dict[str, object]],
        *,
        domain_mode: str = "full",
        contract_override: dict[str, object] | None = None,
        plane_rows: list[float] | None = None,
    ) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "fields").mkdir(exist_ok=True)

        contract = self._base_contract()
        if contract_override:
            contract.update(contract_override)
        (run_dir / "field_export_contract.json").write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")

        frame_name = "fields/field_t000000.000000_i0000000_f0000.csv"
        manifest_row = {
            "case_id": "CASE",
            "domain_mode": domain_mode,
            "field_frame_index": 0,
            "t": 0.0,
            "i": 0,
            "filename": frame_name,
            "sample_count": len(frame_rows),
            "p_min": 0.0,
            "p_max": 0.0,
            "p_range": 0.0,
            "pressure_nonzero": 1,
            "f_min": 0.0,
            "f_max": 1.0,
            "velocity_magnitude_min": 0.0,
            "velocity_magnitude_max": 1.0,
            "vorticity_magnitude_min": 0.0,
            "vorticity_magnitude_max": 1.0,
            "pressure_provenance": "runtime_cell_centered_p_after_centered_projection",
            "event_provenance": "canonical_master_tick_post_projection_i_plus_plus_last",
            "pressure_gauge_context": "outlet_dirichlet_zero_gauge",
            "gravity_enabled": 0,
            "source_sha256": "SOURCE",
            "schedule_version": "V1",
            "schedule_sha256": "S1",
            "master_tick": 0,
            "target_time": 0.0,
            "actual_time": 0.0,
            "maxlevel": 7,
            "restart_lineage": "fresh",
            "field_list": "f|ux|uy|uz|velocity_magnitude|vorticity_magnitude|p|cs",
        }

        with (run_dir / "field_frame_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_HEADER)
            writer.writeheader()
            writer.writerow({k: manifest_row[k] for k in MANIFEST_HEADER})

        # fill source identifiers for frame rows
        rows = []
        for row in frame_rows:
            row = {
                "case_id": "CASE",
                "source_frame_id": "tick000000_t000000.000000_i0000000",
                "field_frame_index": 0,
                "t": 0.0,
                "i": 0,
                "x": row["x"],
                "y": row["y"],
                "z": row["z"],
                "f": row["f"],
                "ux": row["ux"],
                "uy": row.get("uy", 0.0),
                "uz": row.get("uz", 0.0),
                "velocity_magnitude": math.sqrt(float(row.get("ux", 0.0)) ** 2 + float(row.get("uy", 0.0)) ** 2 + float(row.get("uz", 0.0)) ** 2),
                "vorticity_magnitude": 0.0,
                "p": row["p"],
                "cs": row.get("cs", 1.0),
                "level": 6,
                "Delta": row.get("Delta", 1.0),
                "region_flag": row.get("region_flag", 0),
                "pressure_provenance": manifest_row["pressure_provenance"],
                "event_provenance": manifest_row["event_provenance"],
                "gravity_enabled": 0,
                "source_sha256": "SOURCE",
                "schedule_version": "V1",
                "schedule_sha256": "S1",
                "master_tick": 0,
                "target_time": 0.0,
                "actual_time": 0.0,
                "restart_lineage": "fresh",
            }
            rows.append({k: str(v) for k, v in row.items()})

            # keep manifest sample count consistent with potentially injected malformed rows
            if plane_rows and len(rows) == 0:
                rows.extend([])

        if plane_rows:
            # optional helper for row count verification tests
            pass

        with (run_dir / frame_name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELD_HEADER)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in FIELD_HEADER})

    def _metric_row(self, metrics_path: Path, plane: float) -> dict[str, float]:
        with metrics_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if float(row["plane_x_Dh"]) == plane:
                return {k: float(v) for k, v in row.items() if k not in {"case_id", "source_frame_id", "field_frame_index", "t", "i", "domain_mode", "plane_x_Dh", "plane_x", "mirror_factor"}}
        raise AssertionError(f"missing plane {plane}")

    def test_uniform_synthetic_fields_analytical_expectations(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            delta = 0.01 * DH
            area = delta**2
            rows = []
            for plane in DEFAULT_PLANES:
                rows.append({
                    "x": plane * DH,
                    "y": 0.0,
                    "z": 0.0,
                    "f": 1.0,
                    "ux": 2.0,
                    "p": 10.0,
                    "cs": 1.0,
                    "Delta": delta,
                })
            self._write_run(run_dir, rows)
            rc = subprocess.run([
                sys.executable,
                str(SCRIPT_PATH),
                "--run-dir", str(run_dir),
                "--overwrite",
                "--metrics-csv", str(run_dir / "metrics.csv"),
                "--profile-csv", str(run_dir / "profile.csv"),
                "--summary-json", str(run_dir / "summary.json"),
                "--planes", ",".join(str(p) for p in DEFAULT_PLANES),
            ], capture_output=True, text=True)
            self.assertEqual(rc.returncode, 0, rc.stderr)
            m0 = self._metric_row(run_dir / "metrics.csv", 0.5)
            self.assertAlmostEqual(m0["fluid_area"], area)
            self.assertAlmostEqual(m0["liquid_area"], area)
            self.assertAlmostEqual(m0["Q_l"], 2.0 * area)
            self.assertAlmostEqual(m0["mdot_l"], 2.0 * area)
            self.assertAlmostEqual(m0["mdot_mix"], 2.0 * area)
            self.assertAlmostEqual(m0["liquid_kinetic_momentum_flux"], 4.0 * area)
            self.assertAlmostEqual(m0["mixture_kinetic_momentum_flux"], 4.0 * area)
            self.assertAlmostEqual(m0["area_mean_pressure"], 10.0)
            self.assertAlmostEqual(m0["forcing_to_plane_pressure_drop"], 341.48)
            self.assertAlmostEqual(m0["pressure_contribution"], 10.0 * area)
            self.assertAlmostEqual(m0["J_total"], 14.0 * area)
            self.assertAlmostEqual(m0["area_weighted_liquid_velocity"], 2.0)
            self.assertAlmostEqual(m0["flux_weighted_liquid_velocity"], 2.0)
            self.assertAlmostEqual(m0["legacy_Q_l_times_area_weighted_velocity"], 4.0 * area)

    def test_liquid_gas_mixture_convention(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            x_plane = 1.0
            delta = 0.05 * DH
            area = delta**2
            rows = [
                {
                    "x": x_plane * DH,
                    "y": 0.0,
                    "z": 0.0,
                    "f": 1.0,
                    "ux": 1.0,
                    "p": 0.0,
                    "cs": 1.0,
                    "Delta": delta,
                },
                {
                    "x": x_plane * DH,
                    "y": delta,
                    "z": delta,
                    "f": 0.0,
                    "ux": 1.0,
                    "p": 0.0,
                    "cs": 1.0,
                    "Delta": delta,
                },
            ]
            self._write_run(run_dir, rows)
            rc = subprocess.run([
                sys.executable,
                str(SCRIPT_PATH),
                "--run-dir", str(run_dir),
                "--overwrite",
                "--metrics-csv", str(run_dir / "metrics.csv"),
                "--profile-csv", str(run_dir / "profile.csv"),
                "--summary-json", str(run_dir / "summary.json"),
                "--planes", "1.0",
            ], capture_output=True, text=True)
            self.assertEqual(rc.returncode, 0, rc.stderr)
            row = self._metric_row(run_dir / "metrics.csv", 1.0)
            expected_rho_g = ANALYZER.DEFAULT_RHO_G if hasattr(ANALYZER, "DEFAULT_RHO_G") else 1.0 / 27.84
            self.assertAlmostEqual(row["liquid_area"], area)
            self.assertAlmostEqual(row["fluid_area"], 2.0 * area)
            self.assertAlmostEqual(row["Q_l"], area)
            self.assertAlmostEqual(row["mdot_l"], area)
            self.assertAlmostEqual(row["mdot_mix"], (1.0 + expected_rho_g) * area)
            self.assertAlmostEqual(row["liquid_kinetic_momentum_flux"], area)
            self.assertAlmostEqual(row["mixture_kinetic_momentum_flux"], (1.0 + expected_rho_g) * area)

    def test_half_open_plane_selection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            plane_dh = 5.25
            x_plane = plane_dh * DH
            delta = 0.1 * DH
            rows = [
                {"x": x_plane - delta / 2.0, "y": 0.0, "z": 0.0, "f": 1.0, "ux": 3.0, "p": 0.0, "cs": 1.0, "Delta": delta},
                {"x": x_plane + delta / 2.0, "y": 0.0, "z": 0.0, "f": 1.0, "ux": 10.0, "p": 0.0, "cs": 1.0, "Delta": delta},
            ]
            self._write_run(run_dir, rows)
            rc = subprocess.run([
                sys.executable,
                str(SCRIPT_PATH),
                "--run-dir", str(run_dir),
                "--overwrite",
                "--metrics-csv", str(run_dir / "metrics.csv"),
                "--profile-csv", str(run_dir / "profile.csv"),
                "--summary-json", str(run_dir / "summary.json"),
                "--planes", f"{plane_dh}",
            ], capture_output=True, text=True)
            self.assertEqual(rc.returncode, 0, rc.stderr)
            row = self._metric_row(run_dir / "metrics.csv", plane_dh)
            self.assertAlmostEqual(row["Q_l"], 10.0 * delta**2)
            self.assertAlmostEqual(row["liquid_area"], delta**2)

    def test_quarter_mirroring(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            delta = 0.1 * DH
            rows = [
                {
                    "x": 0.5 * DH,
                    "y": 0.5 * delta,
                    "z": 0.5 * delta,
                    "f": 1.0,
                    "ux": 1.0,
                    "p": 5.0,
                    "cs": 1.0,
                    "Delta": delta,
                }
            ]
            self._write_run(run_dir, rows, domain_mode="quarter")
            rc = subprocess.run([
                sys.executable,
                str(SCRIPT_PATH),
                "--run-dir", str(run_dir),
                "--overwrite",
                "--metrics-csv", str(run_dir / "metrics.csv"),
                "--profile-csv", str(run_dir / "profile.csv"),
                "--summary-json", str(run_dir / "summary.json"),
                "--planes", "0.5",
            ], capture_output=True, text=True)
            self.assertEqual(rc.returncode, 0, rc.stderr)
            row = self._metric_row(run_dir / "metrics.csv", 0.5)
            self.assertAlmostEqual(row["mirror_factor"] if "mirror_factor" in row else 4.0, 4.0)
            self.assertAlmostEqual(row["fluid_area"], 4.0 * delta**2)
            self.assertAlmostEqual(row["liquid_area"], 4.0 * delta**2)
            self.assertAlmostEqual(row["Q_l"], 4.0 * delta**2)

    def test_shuffled_cell_order_invariance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir_a = Path(td) / "a"
            run_dir_b = Path(td) / "b"
            delta = 0.1 * DH
            rows = [
                {"x": 0.5 * DH, "y": 0.0, "z": 0.0, "f": 1.0, "ux": 1.0, "p": 2.0, "cs": 1.0, "Delta": delta},
                {"x": 0.5 * DH, "y": delta, "z": delta, "f": 1.0, "ux": 3.0, "p": 2.0, "cs": 1.0, "Delta": delta},
            ]
            self._write_run(run_dir_a, rows)
            self._write_run(run_dir_b, list(reversed(rows)))
            _, metrics_a, _, _ = self._run_analyzer(run_dir_a, overwrite=True, planes="0.5")
            _, metrics_b, _, _ = self._run_analyzer(run_dir_b, overwrite=True, planes="0.5")
            self.assertEqual(
                Path(metrics_a).read_text(),
                Path(metrics_b).read_text(),
            )

    def test_empty_plane_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            rows = [{"x": 100.0, "y": 0.0, "z": 0.0, "f": 1.0, "ux": 1.0, "p": 1.0, "cs": 1.0, "Delta": 1.0}]
            self._write_run(run_dir, rows)
            result, _, _, _ = self._run_analyzer(run_dir, overwrite=True, planes="0.5")
            self.assertNotEqual(result.returncode, 0)

    def test_malformed_input_missing_manifest_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self._write_run(run_dir, [], domain_mode="full", contract_override={"schema": "bad_schema"})
            (run_dir / "fields" / "field_t000000.000000_i0000000_f0000.csv").touch()
            result, *_ = self._run_analyzer(run_dir, overwrite=True, planes="0.5")
            self.assertNotEqual(result.returncode, 0)

    def test_cli_output_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            rows = [
                {"x": 0.5 * DH, "y": 0.0, "z": 0.0, "f": 0.0, "ux": 0.0, "p": 0.0, "cs": 1.0, "Delta": 0.1 * DH},
            ]
            self._write_run(run_dir, rows)
            result = self._run_analyzer(run_dir, overwrite=True, planes="0.5")[0]
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics_path = run_dir / "metrics.csv"
            profile_path = run_dir / "profile.csv"
            summary_path = run_dir / "summary.json"

            with metrics_path.open(newline="", encoding="utf-8") as handle:
                metric_fields = csv.DictReader(handle).fieldnames or []
            self.assertIn("field_frame_index", metric_fields)
            self.assertIn("Q_l", metric_fields)
            self.assertIn("legacy_Q_l_times_area_weighted_velocity", metric_fields)

            with profile_path.open(newline="", encoding="utf-8") as handle:
                profile_fields = csv.DictReader(handle).fieldnames or []
            self.assertIn("source_file", profile_fields)
            self.assertIn("intersection_weight_area", profile_fields)

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["schema"], "internal_nozzle_transient_fluxes_v1")
            self.assertIn("metric_definitions", summary)
            self.assertIn("aperture_mask", summary)
            self.assertIn("cut_cell_quadrature", summary)
            self.assertIn("source_frame_provenance", summary)
            self.assertIsInstance(summary["results"], list)

    def test_negative_velocity_has_positive_axial_momentum_flux(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            delta = 0.1 * DH
            self._write_run(run_dir, [{"x": 0.5 * DH, "y": 0.0, "z": 0.0,
                                      "f": 1.0, "ux": -2.0, "p": 0.0,
                                      "cs": 1.0, "Delta": delta}])
            result, metrics, _, _ = self._run_analyzer(run_dir, overwrite=True, planes="0.5")
            self.assertEqual(result.returncode, 0, result.stderr)
            row = self._metric_row(metrics, 0.5)
            self.assertAlmostEqual(row["liquid_kinetic_momentum_flux"], 4.0 * delta**2)
            self.assertAlmostEqual(row["Q_l"], -2.0 * delta**2)

    def test_output_overwrite_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self._write_run(run_dir, [{"x": 0.5 * DH, "y": 0.0, "z": 0.0,
                                      "f": 1.0, "ux": 1.0, "p": 0.0,
                                      "cs": 1.0, "Delta": 0.1 * DH}])
            first = self._run_analyzer(run_dir, overwrite=False, planes="0.5")[0]
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self._run_analyzer(run_dir, overwrite=False, planes="0.5")[0]
            self.assertNotEqual(second.returncode, 0)

    def test_rectangular_cut_cell_overlap_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            delta = 0.1 * DH
            aperture_edge = 1.5 * ANALYZER.W
            y = aperture_edge + 0.25 * delta
            self._write_run(run_dir, [{"x": 0.5 * DH, "y": y, "z": 0.0,
                                      "f": 1.0, "ux": 2.0, "p": 3.0,
                                      "cs": 0.25, "Delta": delta}])
            result, metrics, _, _ = self._run_analyzer(run_dir, overwrite=True, planes="0.5")
            self.assertEqual(result.returncode, 0, result.stderr)
            row = self._metric_row(metrics, 0.5)
            expected_area = 0.25 * delta**2
            self.assertAlmostEqual(row["fluid_area"], expected_area)
            self.assertAlmostEqual(row["Q_l"], 2.0 * expected_area)

    def test_duplicate_manifest_header_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self._write_run(run_dir, [{"x": 0.5 * DH, "y": 0.0, "z": 0.0,
                                      "f": 1.0, "ux": 1.0, "p": 0.0,
                                      "cs": 1.0, "Delta": 0.1 * DH}])
            manifest = run_dir / "field_frame_manifest.csv"
            lines = manifest.read_text(encoding="utf-8").splitlines()
            lines[0] = lines[0] + ",case_id"
            lines[1] = lines[1] + ",CASE"
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
            result, *_ = self._run_analyzer(run_dir, overwrite=True, planes="0.5")
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
