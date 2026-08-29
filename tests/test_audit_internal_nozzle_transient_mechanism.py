from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_internal_nozzle_transient_mechanism.py"
SPEC = importlib.util.spec_from_file_location("transient_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TransientAuditTests(unittest.TestCase):
    def test_ols_recovers_linear_series(self) -> None:
        result = MODULE.ols([(float(x), 3.0 - 0.25 * x) for x in range(8)])
        self.assertAlmostEqual(result["slope"], -0.25)
        self.assertAlmostEqual(result["robust_slope"], -0.25)
        self.assertAlmostEqual(result["r_squared"], 1.0)
        self.assertEqual(result["monotone_with_fitted_trend_fraction"], 1.0)

    def test_model_audit_does_not_invent_linear_asymptote(self) -> None:
        result = MODULE.fit_models([(float(x), 10.0 - 0.2 * x) for x in range(20)])
        self.assertFalse(result["finite_asymptote_identified"])
        self.assertIn(result["preferred_by_aicc"], {"linear", "piecewise_linear"})

    def test_end_to_end_synthetic_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.csv"
            planes = root / "planes.csv"
            output = root / "audit.json"
            series = root / "series.csv"
            raw_fields = [
                "case_id", "t", "exit_flow", "mean_exit_velocity", "liquid_volume",
                "cumulative_liquid_inflow", "interface_proxy", "active_front_Dh", "restart_lineage",
            ]
            with raw.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=raw_fields)
                writer.writeheader()
                for index in range(20):
                    t = 0.1 * index
                    writer.writerow({
                        "case_id": "synthetic", "t": t,
                        "exit_flow": 2.0 * (1.0 - 0.01 * t),
                        "mean_exit_velocity": 1.0 - 0.01 * t,
                        "liquid_volume": 1.0 + 0.02 * t,
                        "cumulative_liquid_inflow": 0.02 * t,
                        "interface_proxy": 1.0 + t,
                        "active_front_Dh": t,
                        "restart_lineage": "fresh" if index < 10 else "generation-1",
                    })
            plane_fields = [
                "case_id", "t", "plane_x_Dh", "fluid_area", "liquid_area", "Q_l",
                "mdot_l", "mdot_mix", "liquid_kinetic_momentum_flux",
                "mixture_kinetic_momentum_flux", "pressure_contribution", "J_total",
                "area_weighted_liquid_velocity", "flux_weighted_liquid_velocity",
                "area_mean_pressure", "forcing_to_plane_pressure_drop",
                "legacy_Q_l_times_area_weighted_velocity", "restart_lineage",
            ]
            with planes.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=plane_fields)
                writer.writeheader()
                for index in range(20):
                    t = 0.1 * index
                    q = 1.0 - 0.01 * t
                    for plane in (0.5, 14.5, 15.0, 15.25):
                        writer.writerow({
                            "case_id": "synthetic", "t": t, "plane_x_Dh": plane,
                            "fluid_area": 1.0, "liquid_area": 1.0, "Q_l": q,
                            "mdot_l": q, "mdot_mix": q,
                            "liquid_kinetic_momentum_flux": q * q,
                            "mixture_kinetic_momentum_flux": q * q,
                            "pressure_contribution": 2.0 if plane == 0.5 else 0.1,
                            "J_total": q * q + (2.0 if plane == 0.5 else 0.1),
                            "area_weighted_liquid_velocity": q,
                            "flux_weighted_liquid_velocity": q,
                            "area_mean_pressure": 350.0 if plane == 0.5 else 1.0,
                            "forcing_to_plane_pressure_drop": 1.0 if plane == 0.5 else 350.0,
                            "legacy_Q_l_times_area_weighted_velocity": q * q,
                            "restart_lineage": "fresh",
                        })
            subprocess.run(
                [sys.executable, str(SCRIPT), "--raw-summary", str(raw),
                 "--plane-metrics", str(planes), "--output", str(output),
                 "--series-output", str(series)],
                check=True,
            )
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["schema"], "internal_nozzle_transient_mechanism_audit_v1")
            self.assertEqual(result["baseline_validity"], "retained")
            self.assertAlmostEqual(
                result["evidence"]["legacy_exit_flow_double_layer_bias"]["median_legacy_to_true_Q_ratio"],
                2.0,
            )
            self.assertTrue(series.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
