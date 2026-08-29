import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_transient_mechanism_corrected_campaign.py"
SPEC = importlib.util.spec_from_file_location("corrected_campaign", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CorrectedCampaignTests(unittest.TestCase):
    def test_checkpoint_time_reads_actual_time(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "state.dump"
            checkpoint.write_bytes(b"dump")
            Path(str(checkpoint) + ".meta").write_text(
                "schema=x\nactual_time=2.785\n", encoding="utf-8"
            )
            self.assertEqual(MODULE.checkpoint_time(checkpoint), 2.785)

    def test_endpoint_checkpoint_selects_by_metadata_not_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            checkpoints = output / "checkpoints"
            checkpoints.mkdir()
            one = checkpoints / "arbitrary.dump"
            one.write_bytes(b"dump")
            Path(str(one) + ".meta").write_text("actual_time=1.25\n", encoding="utf-8")
            self.assertEqual(MODULE.endpoint_checkpoint(output, 1.25), one)

    def test_terminal_requires_closed_successful_child(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal = Path(directory) / "terminal.json"
            terminal.write_text(json.dumps({
                "exit_code": 0,
                "terminating_signal": None,
                "child_exists_after_wait": False,
            }), encoding="utf-8")
            self.assertEqual(MODULE.terminal_payload(terminal)["exit_code"], 0)
            terminal.write_text(json.dumps({
                "exit_code": 0,
                "terminating_signal": None,
                "child_exists_after_wait": True,
            }), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                MODULE.terminal_payload(terminal)


if __name__ == "__main__":
    unittest.main()
