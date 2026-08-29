import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "summarize_internal_nozzle_corrected_campaign.py"
SPEC = importlib.util.spec_from_file_location("campaign_summary", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CampaignSummaryTests(unittest.TestCase):
    def test_numeric_key_normalizes_equivalent_times(self):
        a = MODULE.numeric_key({"t": "1", "i": "2"}, ("t", "i"))
        b = MODULE.numeric_key({"t": "1.0000000000001", "i": "2"}, ("t", "i"))
        self.assertEqual(a, b)

    def test_write_and_read_csv_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "values.csv"
            values = [{"t": "1", "i": "2"}, {"t": "2", "i": "3"}]
            MODULE.write_csv(path, values)
            self.assertEqual(MODULE.rows(path), values)


if __name__ == "__main__":
    unittest.main()
