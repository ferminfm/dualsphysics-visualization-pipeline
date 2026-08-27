#!/usr/bin/env python3
"""Continue the accepted extended-domain campaign through the conditional t*=12 target.

This is deliberately a narrow process supervisor, not a scheduler.  It waits
for the already-launched segment, requires its durable terminal record and a
validated native checkpoint promotion, rechecks disk headroom at each boundary,
then launches the next bounded restore segment through the established
supervision wrapper.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path("/home/franco/stack-validation/20260826-internal-nozzle-l7-extended-domain-transient-audit-r1")
CAMPAIGN = ROOT / "campaign-physical-l7-equivalent"
OUTPUT_ROOT = ROOT / "task-04-campaign"
TASK = ROOT / "task-04-campaign"
BUILD = Path("/home/franco/tmp/l7-extended-audit-build")
SUPERVISOR = Path(__file__).with_name("supervise_internal_nozzle_run.py")
CHECKPOINTS = Path(__file__).with_name("manage_internal_nozzle_campaign_checkpoints.py")
TARGETS = (("segment-0007", 1.25, 6300), ("segment-0008-retry", 1.40, 7050),
           ("segment-0009", 1.55, 7800), ("segment-0010", 1.675, 8450))
MIN_FREE_BYTES = 10 * 1024**3
# Leave at least roughly 3 GiB below the 20 GiB batch cap for a final 0.125
# segment, based on the observed 0.15-segment output growth.
MAX_ROOT_BYTES_BEFORE_SEGMENT = 17 * 1024**3


def require_terminal(segment: str) -> None:
    terminal = TASK / segment / "supervision/terminal.json"
    while not terminal.is_file():
        time.sleep(30)
    payload = json.loads(terminal.read_text(encoding="utf-8"))
    if payload.get("exit_code") != 0 or payload.get("signal") is not None:
        raise RuntimeError(f"{segment} did not complete cleanly: {payload}")


def safety_gate() -> None:
    usage = shutil.disk_usage(ROOT)
    root_bytes = sum(path.stat().st_size for path in ROOT.rglob("*") if path.is_file())
    if usage.free < MIN_FREE_BYTES:
        raise RuntimeError(f"insufficient free disk before next segment: {usage.free}")
    if root_bytes > MAX_ROOT_BYTES_BEFORE_SEGMENT:
        raise RuntimeError(f"campaign root exceeds prelaunch data guard: {root_bytes}")


def selected_checkpoint() -> str:
    completed = subprocess.run(
        [sys.executable, "-B", str(CHECKPOINTS), "select", "--campaign-root", str(CAMPAIGN)],
        check=True, text=True, capture_output=True,
    )
    return json.loads(completed.stdout)["checkpoint"]


def promote_at_end(output: Path, end_time: float) -> None:
    matches = sorted(output.glob(f"checkpoints/*_t{end_time:09.6f}_*.dump"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one checkpoint at t={end_time}: {matches}")
    subprocess.run(
        [sys.executable, "-B", str(CHECKPOINTS), "promote", "--campaign-root", str(CAMPAIGN),
         "--checkpoint", str(matches[0])], check=True,
    )


def run_segment(segment: str, end_time: float, max_steps: int) -> None:
    safety_gate()
    evidence = TASK / segment / "supervision"
    evidence.mkdir(parents=True, exist_ok=False)
    # Each retry owns a fresh output directory.  A prior attempt without a
    # terminal record cannot be allowed to append duplicate accepted frames.
    output = TASK / segment / "output"
    command = [
        sys.executable, "-B", str(SUPERVISOR), "--evidence-dir", str(evidence), "--cwd", str(BUILD),
        "--timeout-seconds", "7200", "--heartbeat-seconds", "30", "--", "./internal_nozzle_l7_extended_audit",
        "--case-id", "l7_physical_l7_equivalent_extended_campaign", "--domain", "full", "--maxlevel", "8",
        "--baselevel", "4", "--pressure", "351.48", "--end-time", str(end_time), "--external-dh", "21",
        "--refine-external-dh", "6", "--output-dir", str(output), "--diagnostic-dt", "0.005",
        "--field-dt", "0.05", "--visual-dt", "0.05", "--checkpoint-dt", "0.05", "--raw-export", "1",
        "--field-export", "1", "--native-frames", "0", "--facet-export", "0", "--perturb-amp", "0",
        "--max-steps", str(max_steps), "--restore", selected_checkpoint(),
    ]
    subprocess.run(command, check=True)
    require_terminal(segment)
    promote_at_end(output, end_time)


def main() -> int:
    require_terminal("segment-0007")
    # Segment 0007 was written to the established shared campaign output.
    promote_at_end(ROOT / "task-03-extended-domain/physical-l7-equivalent/segment-0002/output", 1.25)
    for segment, end_time, max_steps in TARGETS[1:]:
        run_segment(segment, end_time, max_steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
