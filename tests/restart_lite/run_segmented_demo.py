#!/usr/bin/env python3
"""Run and verify a bounded native-dump restart-lite segment chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


OBS_RE = re.compile(r"^OBS\s+(.*)$")
STOP_RE = re.compile(r"^STOP i=(\d+) restored=(\d+) post_restore_step=(\d+)$")
RSS_RE = re.compile(r"Maximum resident set size \(kbytes\): (\d+)")
INTEGER_KEYS = {"i", "cells", "interfaces", "checkpoint_counter", "output_counter", "restored"}
NUMERIC_KEYS = {"t", "volume", "mx", "my", "mz", "ke", "fmin", "fmax", "umin", "umax"}
BOUNDARY_KEYS = (
    "i", "t", "cells", "interfaces", "volume", "mx", "my", "mz", "ke",
    "fmin", "fmax", "umin", "umax", "checkpoint_counter", "output_counter",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_log(path: Path) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    observations: list[dict[str, object]] = []
    stop = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = OBS_RE.match(line)
        if match:
            record: dict[str, object] = {}
            for item in match.group(1).split():
                key, text = item.split("=", 1)
                if key in INTEGER_KEYS:
                    record[key] = int(text)
                elif key in NUMERIC_KEYS:
                    record[key] = float(text)
                else:
                    record[key] = text
            observations.append(record)
            continue
        match = STOP_RE.match(line)
        if match:
            stop = {
                "i": int(match.group(1)),
                "restored": bool(int(match.group(2))),
                "post_restore_step": bool(int(match.group(3))),
            }
    return observations, stop


def directory_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--targets", default="4,8,12")
    parser.add_argument("--baselevel", type=int, default=5)
    parser.add_argument("--maxlevel", type=int, default=6)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--maxruntime", default="0:10:00")
    args = parser.parse_args()

    targets = [int(item) for item in args.targets.split(",")]
    if len(targets) not in (3, 4) or targets != sorted(set(targets)):
        raise SystemExit("targets must contain three or four strictly increasing iterations")
    if not args.binary.is_file() or args.binary.is_symlink():
        raise SystemExit("binary must be a non-symlink regular file")

    evidence = args.evidence_dir
    evidence.mkdir(parents=True, exist_ok=False)
    checkpoints = evidence / "checkpoints"
    checkpoints.mkdir()
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", ".state"):
        candidate = Path(str(args.checkpoint) + suffix)
        if candidate.exists():
            raise SystemExit(f"checkpoint target already exists: {candidate}")

    plan = {
        "schema_version": "1.0",
        "binary": str(args.binary),
        "binary_size_bytes": args.binary.stat().st_size,
        "binary_sha256": sha256(args.binary),
        "targets": targets,
        "baselevel": args.baselevel,
        "maxlevel": args.maxlevel,
        "timeout_seconds": args.timeout_seconds,
        "maxruntime": args.maxruntime,
        "resource_caps": {
            "rss_bytes": 18 * 1024**3,
            "generated_data_bytes": 20 * 1024**3,
            "gate4_wall_seconds": 4 * 3600,
        },
    }
    atomic_json(evidence / "plan.json", plan)

    started = time.monotonic()
    segments: list[dict[str, object]] = []
    previous_checkpoint_observation = None
    previous_target = -1
    for number, target in enumerate(targets, 1):
        segment_dir = evidence / f"segment-{number}"
        segment_dir.mkdir()
        if number > 1:
            for suffix in ("", ".state"):
                source = Path(str(args.checkpoint) + suffix)
                expected = checkpoints / f"segment-{number - 1}.dump{suffix}"
                if not source.is_file() or source.is_symlink() or sha256(source) != sha256(expected):
                    raise SystemExit("current checkpoint does not match the preserved previous generation")

        command = [
            "/usr/bin/time", "-v", "-o", str(segment_dir / "resource.time"),
            str(args.binary), str(args.checkpoint), str(target), str(target), "-",
            str(args.baselevel), str(args.maxlevel), "--maxruntime", args.maxruntime,
        ]
        (segment_dir / "argv.json").write_text(json.dumps(command) + "\n", encoding="utf-8")
        environment = os.environ.copy()
        environment["OMP_NUM_THREADS"] = "1"
        segment_started = time.monotonic()
        with (segment_dir / "stdout.log").open("wb") as stdout, (segment_dir / "stderr.log").open("wb") as stderr:
            try:
                completed = subprocess.run(command, stdout=stdout, stderr=stderr, env=environment,
                                           timeout=args.timeout_seconds, check=False)
                return_code = completed.returncode
            except subprocess.TimeoutExpired:
                return_code = 124
        elapsed = time.monotonic() - segment_started
        (segment_dir / "rc.txt").write_text(f"{return_code}\n", encoding="ascii")
        if return_code != 0:
            raise SystemExit(f"segment {number} failed with RC {return_code}")

        observations, stop = parse_log(segment_dir / "stderr.log")
        checkpoint_records = [item for item in observations if item.get("phase") == "checkpoint_written"]
        restored_records = [item for item in observations if item.get("phase") == "restored_immediate"]
        end_indices = [int(item["i"]) for item in observations if item.get("phase") == "end_step"]
        if len(checkpoint_records) != 1 or int(checkpoint_records[0]["i"]) != target:
            raise SystemExit(f"segment {number} did not produce exactly one target checkpoint")
        checkpoint_observation = checkpoint_records[0]
        expected_indices = list(range(previous_target + 1, target + 1))
        if end_indices != expected_indices:
            raise SystemExit(f"segment {number} output indices are not contiguous")
        if stop != {"i": target, "restored": number > 1, "post_restore_step": number > 1}:
            raise SystemExit(f"segment {number} stop record is invalid")

        boundary_exact = number == 1
        if number > 1:
            if len(restored_records) != 1 or previous_checkpoint_observation is None:
                raise SystemExit(f"segment {number} lacks one restored boundary record")
            boundary_exact = all(restored_records[0].get(key) == previous_checkpoint_observation.get(key)
                                 for key in BOUNDARY_KEYS)
            if not boundary_exact:
                raise SystemExit(f"segment {number} boundary continuity is not exact")

        checkpoint_meta = {}
        for suffix, label in (("", "dump"), (".state", "sidecar")):
            current = Path(str(args.checkpoint) + suffix)
            if not current.is_file() or current.is_symlink() or current.stat().st_size <= 0:
                raise SystemExit(f"segment {number} checkpoint member is invalid")
            preserved = checkpoints / f"segment-{number}.dump{suffix}"
            shutil.copy2(current, preserved)
            checkpoint_meta[label] = {
                "path": str(preserved),
                "size_bytes": preserved.stat().st_size,
                "sha256": sha256(preserved),
            }

        resource_text = (segment_dir / "resource.time").read_text(encoding="utf-8")
        rss_match = RSS_RE.search(resource_text)
        if not rss_match:
            raise SystemExit(f"segment {number} lacks peak RSS evidence")
        peak_rss = int(rss_match.group(1)) * 1024
        disk_bytes = directory_size(evidence)
        if peak_rss > plan["resource_caps"]["rss_bytes"] or disk_bytes > plan["resource_caps"]["generated_data_bytes"]:
            raise SystemExit(f"segment {number} exceeded a resource cap")

        segment = {
            "segment": number,
            "target_iteration": target,
            "restored": number > 1,
            "return_code": return_code,
            "elapsed_seconds": elapsed,
            "peak_rss_bytes": peak_rss,
            "evidence_bytes_after": disk_bytes,
            "checkpoint": checkpoint_meta,
            "checkpoint_observation": checkpoint_observation,
            "boundary_exact": boundary_exact,
            "output_indices": end_indices,
            "stop": stop,
        }
        segments.append(segment)
        atomic_json(segment_dir / "segment-result.json", segment)
        atomic_json(evidence / "progress.json", {"segments": segments})
        previous_checkpoint_observation = checkpoint_observation
        previous_target = target

    total_elapsed = time.monotonic() - started
    result = {
        "schema_version": "1.0",
        "status": "passed",
        "segments_completed": len(segments),
        "segments": segments,
        "monotonic_progress": all(segments[i]["target_iteration"] < segments[i + 1]["target_iteration"]
                                  for i in range(len(segments) - 1)),
        "all_boundary_checks_exact": all(bool(item["boundary_exact"]) for item in segments),
        "maximum_peak_rss_bytes": max(int(item["peak_rss_bytes"]) for item in segments),
        "final_evidence_bytes": directory_size(evidence),
        "total_elapsed_seconds": total_elapsed,
        "checkpoint_interval_iterations": targets[1] - targets[0],
        "estimated_lost_work_bound": "one checkpoint interval",
        "claim_boundary": "Bounded three-segment non-production restart-lite demonstration only; no L7/L8, production CFD, atomization, or physical-model validation claim.",
    }
    if total_elapsed > plan["resource_caps"]["gate4_wall_seconds"]:
        raise SystemExit("Gate 4 wall-time cap exceeded")
    atomic_json(evidence / "gate4-result.json", result)
    print(json.dumps({"status": "passed", "segments_completed": len(segments)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
