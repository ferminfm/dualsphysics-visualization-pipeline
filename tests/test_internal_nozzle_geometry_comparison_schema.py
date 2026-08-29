import json
import unittest
from pathlib import Path

import jsonschema


SCHEMA = Path(__file__).parents[1] / "docs/contracts/internal_nozzle_geometry_comparison_v1.schema.json"


class GeometryComparisonSchemaTests(unittest.TestCase):
    def test_minimal_valid_record(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        record = {
            "schema": "internal_nozzle_geometry_comparison_v1",
            "provenance": {
                "scientific_commit": "1" * 40,
                "configuration_sha256": "2" * 64,
                "domain_mode": "full",
                "checkpoint_generation": 1,
                "frame_id": "frame-1",
            },
            "geometry": {
                "family": "rectangular",
                "area": 1.0,
                "hydraulic_diameter": 1.0,
                "major": 2.0,
                "minor": 1.0,
                "aspect_ratio": 2.0,
            },
            "coordinates": {"t_star": 1.0, "cumulative_discharge_over_A0Dh": 0.5},
            "hydraulics": {"Q_l": 1.0, "mdot_l": 1.0, "J_k": 1.0,
                            "J_p": 1.0, "J_total": 2.0, "pressure_drop": 1.0},
            "observations": [],
            "resolution_uncertainty": "l7_only_resolution_sensitive",
            "claim_boundary": "transient comparison only",
        }
        jsonschema.Draft202012Validator(schema).validate(record)

    def test_missing_true_flux_is_rejected(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        required = schema["properties"]["hydraulics"]["required"]
        self.assertIn("J_k", required)
        self.assertIn("J_total", required)


if __name__ == "__main__":
    unittest.main()
