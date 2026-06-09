#!/usr/bin/env python3
"""Run a tiny Basilisk 3D VOF jet smoke case and export visualization data.

The generated CSV, VTK, logs, and metrics are intended to stay outside Git,
typically under /tmp. The case is a solver-generated visualization/data-contract
proof, not a validated atomization simulation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_SOURCE = REPO_ROOT / "cases" / "basilisk" / "tiny_atomisation3d_export.c"
DEFAULT_QCC = Path("/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qcc", type=Path, default=DEFAULT_QCC)
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/basilisk-jet-showcase"))
    parser.add_argument("--maxlevel", type=int, default=5)
    parser.add_argument("--end-time", type=float, default=0.14)
    parser.add_argument("--output-interval", type=float, default=0.035)
    parser.add_argument("--uemax", type=float, default=0.05)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--threshold", type=float, default=0.08)
    parser.add_argument("--z-bins", type=int, default=14)
    parser.add_argument("--max-points-per-frame", type=int, default=900)
    return parser.parse_args()


def run_command(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n\n")
        log.flush()
        proc = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        log.write(f"\nEXIT_CODE={proc.returncode}\n")
        log.write(f"RUNTIME_SECONDS={time.time() - started:.3f}\n")
    return proc


def copy_case(work_dir: Path) -> Path:
    if not CASE_SOURCE.exists():
        raise SystemExit(f"ERROR missing Basilisk case source: {CASE_SOURCE}")
    case_dst = work_dir / CASE_SOURCE.name
    shutil.copy2(CASE_SOURCE, case_dst)
    return case_dst


def compile_case(args: argparse.Namespace, work_dir: Path, case_path: Path) -> Path:
    if not args.qcc.exists():
        raise SystemExit(f"ERROR missing qcc: {args.qcc}")
    exe_path = work_dir / "tiny_atomisation3d_export"
    command = [
        str(args.qcc),
        "-O2",
        "-Wall",
        "-grid=octree",
        case_path.name,
        "-o",
        str(exe_path),
        "-lm",
    ]
    proc = run_command(command, cwd=work_dir, log_path=work_dir / "log.compile.txt")
    if proc.returncode != 0:
        raise SystemExit(f"ERROR Basilisk compile failed; see {work_dir / 'log.compile.txt'}")
    return exe_path


def run_case(args: argparse.Namespace, work_dir: Path, exe_path: Path) -> None:
    command = [
        str(exe_path),
        str(args.maxlevel),
        f"{args.end_time:.12g}",
        f"{args.output_interval:.12g}",
        f"{args.uemax:.12g}",
    ]
    try:
        proc = run_command(
            command,
            cwd=work_dir,
            log_path=work_dir / "log.run.txt",
            timeout=args.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"ERROR Basilisk run timed out after {args.timeout_seconds}s") from exc
    if proc.returncode != 0:
        raise SystemExit(f"ERROR Basilisk run failed; see {work_dir / 'log.run.txt'}")


def read_rows(frame_files: Iterable[Path]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for path in frame_files:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                row = {
                    "frame": int(raw["frame"]),
                    "time": float(raw["time"]),
                    "x": float(raw["x"]),
                    "y": float(raw["y"]),
                    "z": float(raw["z"]),
                    "f": float(raw["f"]),
                    "u_x": float(raw["u_x"]),
                    "u_y": float(raw["u_y"]),
                    "u_z": float(raw["u_z"]),
                    "level": int(raw["level"]),
                    "cell_size": float(raw["cell_size"]),
                }
                rows.append(row)
    return rows


def write_combined_csv(rows: list[dict[str, float]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "frame",
        "time",
        "x",
        "y",
        "z",
        "f",
        "u_x",
        "u_y",
        "u_z",
        "level",
        "cell_size",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sampled_rows(rows: list[dict[str, float]], threshold: float, limit: int) -> list[dict[str, float]]:
    active = [row for row in rows if row["f"] >= threshold]
    active.sort(key=lambda item: (item["x"], item["y"], item["z"]))
    if len(active) <= limit:
        return active
    stride = math.ceil(len(active) / limit)
    return active[::stride][:limit]


def write_vtk(points: list[dict[str, float]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("# vtk DataFile Version 3.0\n")
        fh.write("Tiny Basilisk 3D VOF jet point cloud; not validation\n")
        fh.write("ASCII\n")
        fh.write("DATASET POLYDATA\n")
        fh.write(f"POINTS {len(points)} float\n")
        for row in points:
            fh.write(f"{row['x']:.8g} {row['y']:.8g} {row['z']:.8g}\n")
        fh.write(f"VERTICES {len(points)} {len(points) * 2}\n")
        for idx in range(len(points)):
            fh.write(f"1 {idx}\n")
        fh.write(f"POINT_DATA {len(points)}\n")
        fh.write("SCALARS f float 1\n")
        fh.write("LOOKUP_TABLE default\n")
        for row in points:
            fh.write(f"{row['f']:.8g}\n")
        fh.write("SCALARS speed float 1\n")
        fh.write("LOOKUP_TABLE default\n")
        for row in points:
            speed = math.sqrt(row["u_x"] ** 2 + row["u_y"] ** 2 + row["u_z"] ** 2)
            fh.write(f"{speed:.8g}\n")


def covariance_metrics(samples: list[dict[str, float]]) -> dict[str, float | str | int]:
    weights = [max(0.0, row["f"]) * row["cell_size"] ** 2 for row in samples]
    total = sum(weights)
    if total <= 0.0:
        return {
            "area_proxy": 0.0,
            "centroid_y": math.nan,
            "centroid_z": math.nan,
            "major_extent": math.nan,
            "minor_extent": math.nan,
            "aspect_ratio": math.nan,
            "orientation_rad": math.nan,
            "quality_flags": "zero_area",
        }

    cy = sum(w * row["y"] for w, row in zip(weights, samples)) / total
    cz = sum(w * row["z"] for w, row in zip(weights, samples)) / total
    yy = sum(w * (row["y"] - cy) ** 2 for w, row in zip(weights, samples)) / total
    zz = sum(w * (row["z"] - cz) ** 2 for w, row in zip(weights, samples)) / total
    yz = sum(w * (row["y"] - cy) * (row["z"] - cz) for w, row in zip(weights, samples)) / total
    trace = yy + zz
    disc = max(0.0, (yy - zz) ** 2 + 4.0 * yz ** 2)
    lam1 = max(0.0, 0.5 * (trace + math.sqrt(disc)))
    lam2 = max(0.0, 0.5 * (trace - math.sqrt(disc)))
    major = 4.0 * math.sqrt(lam1) if lam1 > 0.0 else 0.0
    minor = 4.0 * math.sqrt(lam2) if lam2 > 0.0 else 0.0
    aspect = major / minor if minor > 1e-12 else math.inf
    orientation = 0.5 * math.atan2(2.0 * yz, yy - zz)
    flag = "ok" if len(samples) >= 5 else "sparse"
    return {
        "area_proxy": total,
        "centroid_y": cy,
        "centroid_z": cz,
        "major_extent": major,
        "minor_extent": minor,
        "aspect_ratio": aspect,
        "orientation_rad": orientation,
        "quality_flags": flag,
    }


def compute_metrics(rows: list[dict[str, float]], threshold: float, z_bins: int) -> list[dict[str, float | str | int]]:
    active = [row for row in rows if row["f"] >= threshold]
    if not active:
        return []
    by_frame: dict[int, list[dict[str, float]]] = defaultdict(list)
    for row in active:
        by_frame[int(row["frame"])].append(row)

    x_values = [row["x"] for row in active]
    xmin, xmax = min(x_values), max(x_values)
    width = max((xmax - xmin) / max(1, z_bins), 1e-12)
    metrics: list[dict[str, float | str | int]] = []
    for frame, frame_rows in sorted(by_frame.items()):
        time_value = frame_rows[0]["time"]
        bins: dict[int, list[dict[str, float]]] = defaultdict(list)
        for row in frame_rows:
            idx = min(z_bins - 1, max(0, int((row["x"] - xmin) / width)))
            bins[idx].append(row)
        for idx in range(z_bins):
            samples = bins.get(idx, [])
            if not samples:
                continue
            stats = covariance_metrics(samples)
            z_center = xmin + (idx + 0.5) * width
            metrics.append(
                {
                    "source_id": "basilisk_tiny_3d_jet_showcase",
                    "source_type": "basilisk_vof_smoke",
                    "simulation_source": "Basilisk tiny 3D VOF export",
                    "physical_validation": "false",
                    "frame": frame,
                    "time": time_value,
                    "z": z_center,
                    "post_transient": "false",
                    "stationarity_window_id": "",
                    "cell_count": len(samples),
                    "particle_count": len(samples),
                    "threshold": threshold,
                    "area_proxy": stats["area_proxy"],
                    "Ahat": "",
                    "centroid_x": "",
                    "centroid_y": stats["centroid_y"],
                    "aspect_ratio": stats["aspect_ratio"],
                    "orientation_rad": stats["orientation_rad"],
                    "major_extent": stats["major_extent"],
                    "minor_extent": stats["minor_extent"],
                    "u_axial_mean": sum(row["u_x"] for row in samples) / len(samples),
                    "u_axial_std": _std([row["u_x"] for row in samples]),
                    "mass_or_particle_flux_proxy": sum(row["f"] * row["u_x"] for row in samples),
                    "quality_flags": stats["quality_flags"],
                }
            )

    valid_areas = [
        float(row["area_proxy"])
        for row in metrics
        if isinstance(row["area_proxy"], (float, int)) and row["area_proxy"] > 0.0
    ]
    reference = valid_areas[0] if valid_areas else 0.0
    if reference > 0.0:
        for row in metrics:
            area = float(row["area_proxy"])
            row["Ahat"] = area / reference if area > 0.0 else ""
    return metrics


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def write_metrics(metrics: list[dict[str, float | str | int]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_id",
        "source_type",
        "simulation_source",
        "physical_validation",
        "frame",
        "time",
        "z",
        "post_transient",
        "stationarity_window_id",
        "cell_count",
        "particle_count",
        "threshold",
        "area_proxy",
        "Ahat",
        "centroid_x",
        "centroid_y",
        "aspect_ratio",
        "orientation_rad",
        "major_extent",
        "minor_extent",
        "u_axial_mean",
        "u_axial_std",
        "mass_or_particle_flux_proxy",
        "quality_flags",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in metrics:
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    case_path = copy_case(work_dir)
    exe_path = compile_case(args, work_dir, case_path)
    run_case(args, work_dir, exe_path)

    frame_files = sorted(work_dir.glob("basilisk3d_jet_frame_*.csv"))
    if not frame_files:
        raise SystemExit("ERROR Basilisk run produced no CSV frames")
    rows = read_rows(frame_files)
    if not rows:
        raise SystemExit("ERROR Basilisk CSV frames contain no liquid/interface rows")

    combined_csv = work_dir / "data" / "basilisk3d_jet_cells.csv"
    write_combined_csv(rows, combined_csv)

    vtk_dir = work_dir / "vtk"
    vtk_paths: list[Path] = []
    by_frame: dict[int, list[dict[str, float]]] = defaultdict(list)
    for row in rows:
        by_frame[int(row["frame"])].append(row)
    for frame, frame_rows in sorted(by_frame.items()):
        points = sampled_rows(frame_rows, args.threshold, args.max_points_per_frame)
        if not points:
            continue
        vtk_path = vtk_dir / f"basilisk_jet_points_{frame:04d}.vtk"
        write_vtk(points, vtk_path)
        vtk_paths.append(vtk_path)

    metrics = compute_metrics(rows, args.threshold, args.z_bins)
    metrics_csv = work_dir / "metrics" / "basilisk3d_jet_slice_metrics.csv"
    write_metrics(metrics, metrics_csv)

    summary = {
        "status": "success",
        "case": "tiny_atomisation3d_export.c",
        "qcc": str(args.qcc),
        "work_dir": str(work_dir),
        "maxlevel": args.maxlevel,
        "end_time": args.end_time,
        "output_interval": args.output_interval,
        "threshold": args.threshold,
        "frame_csv_count": len(frame_files),
        "raw_cell_rows": len(rows),
        "vtk_frame_count": len(vtk_paths),
        "metrics_rows": len(metrics),
        "combined_csv": str(combined_csv),
        "metrics_csv": str(metrics_csv),
        "vtk_dir": str(vtk_dir),
        "caveat": (
            "Tiny Basilisk 3D VOF smoke/export case for visualization and data-contract "
            "testing only; not validated atomization, not production CFD."
        ),
    }
    summary_path = work_dir / "showcase_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("BASILISK_JET_SHOWCASE_STATUS=success")
    print(f"WORK_DIR={work_dir}")
    print(f"FRAME_CSV_COUNT={len(frame_files)}")
    print(f"RAW_CELL_ROWS={len(rows)}")
    print(f"VTK_FRAME_COUNT={len(vtk_paths)}")
    print(f"METRICS_ROWS={len(metrics)}")
    print(f"COMBINED_CSV={combined_csv}")
    print(f"METRICS_CSV={metrics_csv}")
    print(f"VTK_DIR={vtk_dir}")
    print(f"SUMMARY_JSON={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
