from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_internal_nozzle_instrumentation as validator  # noqa: E402


class InstrumentationValidatorTests(unittest.TestCase):
    def make_fixture(self, pressure_range: float = 4.0) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "fields").mkdir()
        contract = {
            "schema": "internal_nozzle_post_projection_fields_v2",
            "pressure_provenance": validator.PRESSURE_PROVENANCE,
            "event_provenance": validator.EVENT_PROVENANCE,
            "gravity_enabled": False,
            "instrumentation_changes_solver_state": False,
        }
        (root / "field_export_contract.json").write_text(json.dumps(contract), encoding="utf-8")
        field_name = "fields/field_t000000.000000_i0000000_f0000.csv"
        columns = [
            "case_id", "source_frame_id", "field_frame_index", "t", "i", "x", "y", "z", "f",
            "ux", "uy", "uz", "velocity_magnitude", "vorticity_magnitude", "p", "cs", "level",
            "Delta", "region_flag", "pressure_provenance", "event_provenance", "gravity_enabled",
        ]
        with (root / field_name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerow({key: "0" for key in columns} | {"pressure_provenance": validator.PRESSURE_PROVENANCE, "event_provenance": validator.EVENT_PROVENANCE})
        manifest_columns = [
            "case_id", "domain_mode", "field_frame_index", "t", "i", "filename", "sample_count",
            "p_min", "p_max", "p_range", "pressure_nonzero", "f_min", "f_max",
            "velocity_magnitude_min", "velocity_magnitude_max", "vorticity_magnitude_min",
            "vorticity_magnitude_max", "pressure_provenance", "event_provenance",
            "pressure_gauge_context", "gravity_enabled",
        ]
        with (root / "field_frame_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=manifest_columns)
            writer.writeheader()
            writer.writerow({
                "case_id": "fixture", "domain_mode": "full", "field_frame_index": 0, "t": 0, "i": 0,
                "filename": field_name, "sample_count": 1, "p_min": 0, "p_max": pressure_range,
                "p_range": pressure_range, "pressure_nonzero": int(pressure_range > 1e-12), "f_min": 0,
                "f_max": 1, "velocity_magnitude_min": 0, "velocity_magnitude_max": 1,
                "vorticity_magnitude_min": 0, "vorticity_magnitude_max": 1,
                "pressure_provenance": validator.PRESSURE_PROVENANCE,
                "event_provenance": validator.EVENT_PROVENANCE,
                "pressure_gauge_context": "outlet_dirichlet_zero_gauge", "gravity_enabled": 0,
            })
        (root / "raw_frame_summary.csv").write_text("case_id,t,frame_index,i\nfixture,0,0,0\n", encoding="utf-8")
        return root

    def test_valid_runtime_pressure_fixture_passes(self) -> None:
        result = validator.validate_run(self.make_fixture(), False, False)
        self.assertTrue(result["passed"])
        self.assertEqual(result["pressure_decision"], "valid_runtime_nonzero")

    def test_zero_range_pressure_fixture_blocks(self) -> None:
        result = validator.validate_run(self.make_fixture(0.0), False, False)
        self.assertFalse(result["passed"])
        self.assertEqual(result["pressure_decision"], "blocked")


if __name__ == "__main__":
    unittest.main()
