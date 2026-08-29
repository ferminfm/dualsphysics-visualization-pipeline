#!/usr/bin/env python3
"""Aggregate and validate one supervised corrected-baseline campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


CSV_SPECS = {
    "raw_frame_summary.csv": ("t", "i"),
    "hydraulic_plane_metrics.csv": ("t", "i", "plane_label"),
    "solver_health_metrics.csv": ("t", "i"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def numeric_key(row: dict[str, str], columns: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(round(float(row[name]), 12) if name == "t" else row[name] for name in columns)


def aggregate(segment_dirs: list[Path], filename: str,
              key_columns: tuple[str, ...]) -> tuple[list[dict[str, str]], int]:
    selected: dict[tuple[object, ...], dict[str, str]] = {}
    duplicates = 0
    for segment in segment_dirs:
        path = segment / "output" / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        for row in rows(path):
            key = numeric_key(row, key_columns)
            if key in selected:
                duplicates += 1
            selected[key] = row
    return [selected[key] for key in sorted(selected)], duplicates


def write_csv(path: Path, values: list[dict[str, str]]) -> None:
    if not values:
        raise ValueError(f"cannot write empty aggregate {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(values[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(values)


def validate_campaign_state(root: Path) -> dict[str, object]:
    state_path = root / "campaign-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schema") != "internal_nozzle_campaign_state_v1":
        raise ValueError("unexpected campaign-state schema")
    generations = state.get("generations")
    if not isinstance(generations, list) or not generations:
        raise ValueError("campaign has no retained validated generation")
    for generation in generations:
        directory = root / str(generation["directory"])
        for member in generation["members"]:
            path = directory / str(member["name"])
            if not path.is_file() or path.stat().st_size != int(member["size_bytes"]):
                raise ValueError(f"checkpoint member size mismatch: {path}")
            if sha256(path) != member["sha256"]:
                raise ValueError(f"checkpoint member hash mismatch: {path}")
    return state


def terminal(segment: Path) -> dict[str, object]:
    path = segment / "supervision" / "terminal.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("exit_code") != 0 or payload.get("terminating_signal") is not None:
        raise ValueError(f"segment has non-clean terminal state: {segment}")
    if payload.get("child_exists_after_wait") is not False:
        raise ValueError(f"segment did not close child lifecycle: {segment}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment-root", required=True, type=Path)
    parser.add_argument("--campaign-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--tstar-factor", type=float, default=7.180961047245843)
    args = parser.parse_args()
    segment_dirs = sorted(path for path in args.segment_root.glob("segment-*") if path.is_dir())
    if not segment_dirs:
        raise SystemExit("no campaign segments found")
    terminals = [terminal(segment) for segment in segment_dirs]
    state = validate_campaign_state(args.campaign_root)
    duplicates: dict[str, int] = {}
    aggregates: dict[str, list[dict[str, str]]] = {}
    for filename, keys in CSV_SPECS.items():
        values, count = aggregate(segment_dirs, filename, keys)
        aggregates[filename] = values
        duplicates[filename] = count
        write_csv(args.output_root / filename, values)
    if any(duplicates.values()):
        raise ValueError(f"duplicate accepted aggregate keys: {duplicates}")

    hydraulic = aggregates["hydraulic_plane_metrics.csv"]
    exit_rows = [row for row in hydraulic if row["plane_label"] == "geometric_nozzle_exit"]
    if not exit_rows:
        raise ValueError("geometric-exit metrics unavailable")
    final_t = max(float(row["t"]) for row in exit_rows)
    summary = {
        "schema": "internal_nozzle_corrected_campaign_summary_v1",
        "segment_count": len(segment_dirs),
        "final_time": final_t,
        "final_tstar": final_t * args.tstar_factor,
        "selected_generation": state["newest_generation"],
        "previous_generation": state.get("previous_generation"),
        "terminal_records_clean": True,
        "aggregate_duplicate_count": sum(duplicates.values()),
        "duplicate_counts": duplicates,
        "solver_elapsed_seconds": sum(float(item["elapsed_seconds"]) for item in terminals),
        "peak_rss_kib": max(int(item["peak_rss_kib"]) for item in terminals),
        "segment_terminal_records": [str(segment / "supervision" / "terminal.json")
                                     for segment in segment_dirs],
        "aggregate_files": {
            name: {"path": str(args.output_root / name),
                   "rows": len(values), "sha256": sha256(args.output_root / name)}
            for name, values in aggregates.items()
        },
    }
    output = args.output_root / "campaign-summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "final_tstar": summary["final_tstar"],
                      "segments": len(segment_dirs)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
