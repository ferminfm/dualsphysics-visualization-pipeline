from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from reconstruct_quarter_domain import LABEL, transform_facet  # noqa: E402


class QuarterDomainToolsTest(unittest.TestCase):
    def test_odd_reflection_reverses_winding(self) -> None:
        facet = [(0.0, 1.0, 2.0), (1.0, 1.0, 2.0), (0.0, 2.0, 2.0)]
        self.assertEqual(
            transform_facet(facet, -1, 1),
            [(0.0, -2.0, 2.0), (1.0, -1.0, 2.0), (0.0, -1.0, 2.0)],
        )
        self.assertEqual(
            transform_facet(facet, -1, -1),
            [(0.0, -1.0, -2.0), (1.0, -1.0, -2.0), (0.0, -2.0, -2.0)],
        )

    def test_reconstruction_is_labeled_and_fourfold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            source = tmp / "quarter.facets"
            source.write_text(
                "# domain_mode=quarter\n"
                "0 0 0\n1 0 0\n0 1 1\n\n",
                encoding="utf-8",
            )
            manifest = tmp / "manifest.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "reconstruct_quarter_domain.py"),
                    "--input", str(source),
                    "--output-dir", str(tmp / "out"),
                    "--manifest", str(manifest),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(result["persistent_label"], LABEL)
            self.assertFalse(result["independent_full_domain_physics"])
            self.assertEqual(result["records"][0]["reconstructed_facet_count"], 4)

    def test_basilisk_source_uses_reflection_not_periodic_radial_bcs(self) -> None:
        source = (ROOT / "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("u.n[bottom] = domain_quarter ? dirichlet(0.)", source)
        self.assertIn("u.n[back] = domain_quarter ? dirichlet(0.)", source)
        self.assertIn('"  \\"transverse_periodic_boundaries\\": false', source)
        self.assertNotIn("periodic(bottom)", source)
        self.assertNotIn("periodic(back)", source)


if __name__ == "__main__":
    unittest.main()
