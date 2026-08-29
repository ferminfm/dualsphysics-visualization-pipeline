import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).parents[1] / "scripts" / "render_internal_nozzle_transient_review.py"
SPEC = importlib.util.spec_from_file_location("render_review", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class VisualReviewTests(unittest.TestCase):
    def test_validate_records_decodable_nonempty_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "review.png"
            Image.new("RGB", (300, 200), "blue").save(image)
            manifest = MODULE.validate([image], root)
            self.assertEqual(manifest["member_count"], 1)
            self.assertEqual(manifest["members"][0]["width"], 300)
            self.assertEqual(len(manifest["members"][0]["sha256"]), 64)

    def test_dedupe_prefers_latest_same_time_and_plane(self):
        first = {"t": "1", "plane_x_Dh": "15", "value": "old"}
        second = {"t": "1.0", "plane_x_Dh": "15.0", "value": "new"}
        result = MODULE.dedupe([first, second], ("t", "plane_x_Dh"))
        self.assertEqual(result[0]["value"], "new")

    def test_control_plot_accepts_comparison_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comparison = root / "comparison.json"
            comparison.write_text(json.dumps({
                "fields": {"per_field": {
                    "f": {"relative_l2": 0.0},
                    "ux": {"relative_l2": 1e-8},
                }}
            }), encoding="utf-8")
            products = MODULE.plot_control(comparison, root)
            self.assertEqual(len(products), 1)
            self.assertGreater(products[0].stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
