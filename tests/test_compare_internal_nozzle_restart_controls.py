import csv
import importlib.util
import tempfile
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_internal_nozzle_restart_controls.py"
SPEC = importlib.util.spec_from_file_location("compare_internal_nozzle_restart_controls", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CompareRestartControlsTests(unittest.TestCase):
    def _field(self, root: Path, name: str, ux: float) -> Path:
        path = root / name
        header = ["t", "i", *MODULE.KEY_FIELDS, *MODULE.STATE_FIELDS]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerow({
                "t": "1.0", "i": "5", "x": "0", "y": "0", "z": "0",
                "level": "7", "Delta": "0.1", "f": "1", "ux": ux,
                "uy": "0", "uz": "0", "p": "2", "cs": "1",
            })
        return path

    def test_identical_field_endpoint_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = MODULE.compare_fields(self._field(root, "a.csv", 3.0), self._field(root, "b.csv", 3.0))
        self.assertEqual(result["matched_rows"], 1)
        self.assertEqual(result["left_only_rows"], 0)
        self.assertEqual(result["right_only_rows"], 0)
        self.assertEqual(result["field_relative_l2_max"], 0.0)

    def test_relative_l2_detects_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = MODULE.compare_fields(self._field(root, "a.csv", 2.0), self._field(root, "b.csv", 2.2))
        self.assertAlmostEqual(result["per_field"]["ux"]["relative_l2"], 0.1)


if __name__ == "__main__":
    unittest.main()
