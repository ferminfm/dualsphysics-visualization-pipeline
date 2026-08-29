#!/usr/bin/env python3
"""Run the corrected physical-L7-equivalent campaign in auditable segments.

This is a narrow batch driver, not a general scheduler.  It launches every
scientific process through the established lifecycle supervisor, requires a
clean terminal record, promotes the endpoint native checkpoint, and rechecks
wall/data/filesystem guards before the next segment.  Paths are supplied by
the caller so the committed tool contains no machine-specific location.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def terminal_payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("exit_code") != 0 or payload.get("terminating_signal") is not None:
        raise RuntimeError(f"scientific process did not complete cleanly: {payload}")
    if payload.get("child_exists_after_wait") is not False:
        raise RuntimeError(f"scientific process lifecycle was not closed: {payload}")
    return payload


def select_checkpoint(manager: Path, campaign: Path) -> Path:
    completed = subprocess.run(
        [sys.executable, "-B", str(manager), "select", "--campaign-root", str(campaign)],
        check=True,
        text=True,
        capture_output=True,
    )
    return Path(json.loads(completed.stdout)["checkpoint"])


def checkpoint_time(checkpoint: Path) -> float:
    metadata = Path(str(checkpoint) + ".meta")
    for line in metadata.read_text(encoding="utf-8").splitlines():
        if line.startswith("actual_time="):
            return float(line.split("=", 1)[1])
    raise RuntimeError(f"checkpoint metadata has no actual_time: {metadata}")


def endpoint_checkpoint(output: Path, end_time: float) -> Path:
    candidates = sorted((output / "checkpoints").glob("*.dump"))
    matched = [item for item in candidates if abs(checkpoint_time(item) - end_time) <= 1e-9]
    if len(matched) != 1:
        raise RuntimeError(f"expected one endpoint checkpoint at {end_time}: {matched}")
    return matched[0]


def promote(manager: Path, campaign: Path, checkpoint: Path) -> None:
    subprocess.run(
        [sys.executable, "-B", str(manager), "promote", "--campaign-root", str(campaign),
         "--checkpoint", str(checkpoint)],
        check=True,
    )
    selected = select_checkpoint(manager, campaign)
    if selected.resolve() == checkpoint.resolve():
        raise RuntimeError("promotion must select the validated copied generation, not source output")
    if checkpoint_time(selected) != checkpoint_time(checkpoint):
        raise RuntimeError("promoted checkpoint time disagrees with source endpoint")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument("--campaign-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--build-cwd", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--target-tstar", action="append", required=True, type=float)
    parser.add_argument("--field-at-tstar", action="append", default=[], type=float)
    parser.add_argument("--tstar-factor", required=True, type=float)
    parser.add_argument("--supervisor", type=Path,
                        default=Path(__file__).with_name("supervise_internal_nozzle_run.py"))
    parser.add_argument("--checkpoint-manager", type=Path,
                        default=Path(__file__).with_name("manage_internal_nozzle_campaign_checkpoints.py"))
    parser.add_argument("--segment-timeout-seconds", type=float, default=10800.)
    parser.add_argument("--solver-wall-budget-seconds", type=float, default=79200.)
    parser.add_argument("--batch-data-cap-bytes", type=int, default=20 * 1024**3)
    parser.add_argument("--minimum-free-bytes", type=int, default=8 * 1024**3)
    parser.add_argument("--case-id", default="l7_transient_mechanism_corrected_baseline")
    parser.add_argument("--start-fresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = sorted(set(args.target_tstar))
    if any(value <= 0. for value in targets) or targets != list(args.target_tstar):
        raise ValueError("--target-tstar values must be unique, positive, and ascending")
    if args.tstar_factor <= 0.:
        raise ValueError("--tstar-factor must be positive")
    if not args.binary.is_file() or not args.supervisor.is_file() or not args.checkpoint_manager.is_file():
        raise FileNotFoundError("binary, supervisor, or checkpoint manager is missing")
    if sha256(args.binary) == args.source_sha256:
        raise ValueError("source SHA-256 must identify source bytes, not the produced binary")

    args.batch_root.mkdir(parents=True, exist_ok=True)
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.campaign_root.mkdir(parents=True, exist_ok=True)
    state_path = args.campaign_root / "campaign-state.json"
    if args.start_fresh and state_path.exists():
        raise RuntimeError("--start-fresh refused because campaign state already exists")
    ledger_path = args.output_root / "corrected-campaign-ledger.json"
    ledger: dict[str, object] = {
        "schema": "internal_nozzle_corrected_campaign_ledger_v1",
        "started_at_utc": now(),
        "source_sha256": args.source_sha256,
        "binary_sha256": sha256(args.binary),
        "tstar_factor": args.tstar_factor,
        "targets_tstar": targets,
        "segments": [],
    }
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    elapsed = sum(float(item.get("elapsed_seconds", 0.)) for item in ledger["segments"])
    current_time = checkpoint_time(select_checkpoint(args.checkpoint_manager, args.campaign_root)) \
        if state_path.exists() else 0.
    for target_index, target_tstar in enumerate(targets, start=1):
        end_time = target_tstar / args.tstar_factor
        if end_time <= current_time + 1e-9:
            continue
        if elapsed >= args.solver_wall_budget_seconds:
            raise RuntimeError(f"solver wall budget exhausted before t*={target_tstar}: {elapsed}")
        if tree_size(args.batch_root) >= args.batch_data_cap_bytes:
            raise RuntimeError("batch data cap reached before next segment")
        free = shutil.disk_usage(args.batch_root).free
        if free < args.minimum_free_bytes:
            raise RuntimeError(f"filesystem free-space guard failed before next segment: {free}")

        segment = f"segment-{target_index:04d}-tstar-{target_tstar:g}"
        segment_root = args.output_root / segment
        if segment_root.exists():
            raise RuntimeError(f"refusing duplicate or ambiguous segment output: {segment_root}")
        evidence = segment_root / "supervision"
        output = segment_root / "output"
        evidence.mkdir(parents=True)
        field_export = any(abs(target_tstar - value) <= 1e-12 for value in args.field_at_tstar)
        previous_time = current_time
        command = [
            sys.executable, "-B", str(args.supervisor),
            "--evidence-dir", str(evidence), "--cwd", str(args.build_cwd),
            "--timeout-seconds", str(args.segment_timeout_seconds), "--heartbeat-seconds", "30", "--",
            str(args.binary), "--case-id", args.case_id, "--domain", "full",
            "--maxlevel", "8", "--baselevel", "4", "--pressure", "351.48",
            "--end-time", f"{end_time:.15g}", "--external-dh", "21",
            "--refine-external-dh", "6", "--output-dir", str(output),
            "--diagnostic-dt", "0.005", "--field-dt", f"{max(end_time - previous_time, 0.005):.15g}",
            "--visual-dt", "1", "--checkpoint-dt", f"{end_time:.15g}",
            "--raw-export", "0", "--field-export", "1" if field_export else "0",
            "--native-frames", "0", "--facet-export", "0", "--perturb-amp", "0",
            "--max-steps", str(math.ceil(end_time * 6000.) + 1000),
            "--source-sha", args.source_sha256,
        ]
        if state_path.exists():
            command.extend(["--restore", str(select_checkpoint(args.checkpoint_manager,
                                                                  args.campaign_root))])
        subprocess.run(command, check=True)
        terminal = terminal_payload(evidence / "terminal.json")
        checkpoint = endpoint_checkpoint(output, end_time)
        promote(args.checkpoint_manager, args.campaign_root, checkpoint)
        elapsed += float(terminal["elapsed_seconds"])
        current_time = end_time
        ledger["segments"].append({
            "segment": segment,
            "target_tstar": target_tstar,
            "end_time": end_time,
            "field_export": field_export,
            "elapsed_seconds": terminal["elapsed_seconds"],
            "peak_rss_kib": terminal["peak_rss_kib"],
            "checkpoint": str(select_checkpoint(args.checkpoint_manager, args.campaign_root)),
            "batch_bytes_after": tree_size(args.batch_root),
            "filesystem_free_bytes_after": shutil.disk_usage(args.batch_root).free,
            "completed_at_utc": now(),
        })
        atomic_json(ledger_path, ledger)

    ledger["completed_at_utc"] = now()
    ledger["solver_elapsed_seconds"] = elapsed
    atomic_json(ledger_path, ledger)
    print(json.dumps({"status": "complete", "tstar": targets[-1],
                      "solver_elapsed_seconds": elapsed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
