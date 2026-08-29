import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "classify_internal_nozzle_stationarity.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("stationarity", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def metric(slope, robust, drift):
    return {
        "relative_slope_percent_per_tstar": slope,
        "robust_relative_slope_percent_per_tstar": robust,
        "end_to_end_relative_drift_percent": drift,
    }


def window(slope, drift):
    return {
        "status": "available",
        "metrics": {name: metric(slope, slope, drift) for name in MODULE.REQUIRED},
    }


class StationarityClassificationTests(unittest.TestCase):
    def test_quasi_steady_requires_all_core_metrics(self):
        result, _ = MODULE.classify(window(0.4, 0.8), window(2.0, 4.0), "unresolved")
        self.assertEqual(result, "operational_quasi_steady")
        candidate = window(0.4, 0.8)
        candidate["metrics"]["J_total"] = metric(0.6, 0.4, 0.8)
        result, _ = MODULE.classify(candidate, window(0.7, 4.0), "unresolved")
        self.assertEqual(result, "persistent_transient_unresolved")

    def test_approaching_requires_half_slope_reduction(self):
        result, _ = MODULE.classify(window(1.0, 2.0), window(4.0, 8.0), "identified")
        self.assertEqual(result, "approaching_quasi_steady")
        result, _ = MODULE.classify(window(2.1, 4.2), window(4.0, 8.0), "identified")
        self.assertEqual(result, "persistent_transient_mechanism_identified")

    def test_insufficient_coverage(self):
        result, _ = MODULE.classify({"status": "insufficient"}, window(1.0, 2.0), "unresolved")
        self.assertEqual(result, "insufficient")


if __name__ == "__main__":
    unittest.main()
