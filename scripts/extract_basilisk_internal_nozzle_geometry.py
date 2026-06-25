#!/usr/bin/env python3
"""Repackage Basilisk internal-nozzle metrics for geometry-handoff review.

This is a source/docs capture of the 2026-06-20 internal-nozzle handoff path.
It reads upstream cross-section and frame diagnostics from a selected case and
emits normalized station/frame CSVs. It does not read raw VOF fields and must
not be described as validation, stationary spray data, or fit-ready extraction.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
from typing import Iterable


DEFAULT_W = 0.208885689553
DEFAULT_H = 0.104442844776
DEFAULT_DH = 0.139257126368
DEFAULT_UMEAN = 0.931157985656


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: pathlib.Path, fieldnames: Iterable[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fnum(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = row.get(key, "")
    if raw == "":
        return default
    return float(raw)


def quality_for_station(area: float, active_front: float, x_from_exit: float) -> str:
    flags = ["not_stationary", "not_for_model_fit"]
    if area <= 0.0:
        flags.append("low_occupancy")
    else:
        flags.extend(["connected_core", "usable_for_shape_trend", "usable_for_model_overlay"])
        if active_front > 0.0 and x_from_exit >= 0.9 * active_front:
            flags.append("active_front_nearby")
    return "|".join(flags)


def build_outputs(
    cross_sections: pathlib.Path,
    frames: pathlib.Path,
    output_dir: pathlib.Path,
    source_case: str,
    width: float,
    height: float,
    dh: float,
    mean_velocity: float,
) -> dict[str, object]:
    xs_rows = read_csv(cross_sections)
    frame_rows = read_csv(frames)
    area0 = width * height
    r0 = math.sqrt(area0 / math.pi)
    frame_by_time = {row["t"]: row for row in frame_rows}

    station_rows: list[dict[str, object]] = []
    for row in xs_rows:
        time = row["t"]
        frame = frame_by_time.get(time, {})
        x_from_exit = fnum(row, "x_from_exit")
        area = fnum(row, "area_proxy")
        active_front = fnum(frame, "active_front")
        equivalent_diameter = math.sqrt(4.0 * area / math.pi) if area > 0.0 else 0.0
        station_rows.append(
            {
                "source_case": source_case,
                "time": time,
                "frame_id": frame.get("i", ""),
                "station_id": row.get("station_id", ""),
                "x_from_exit": row.get("x_from_exit", ""),
                "xi": x_from_exit / dh if dh else 0.0,
                "zeta": x_from_exit / r0 if r0 else 0.0,
                "tau": fnum(row, "t") * mean_velocity / dh if dh else 0.0,
                "A": area,
                "Ahat": area / area0 if area0 else 0.0,
                "equivalent_diameter": equivalent_diameter,
                "width": row.get("width", ""),
                "thickness": row.get("thickness", ""),
                "aspect_ratio": row.get("aspect_ratio", ""),
                "centroid_y": row.get("centroid_y", ""),
                "centroid_z": row.get("centroid_z", ""),
                "orientation_angle": "",
                "warp_proxy": row.get("warp_proxy", ""),
                "interface_growth_proxy": frame.get("interface_growth", ""),
                "component_count": frame.get("post_tag_count", ""),
                "detached_proxy_count": frame.get("detached_proxy_count", ""),
                "quality_flag": quality_for_station(area, active_front, x_from_exit),
                "source_metric_path": str(cross_sections),
            }
        )

    frame_out: list[dict[str, object]] = []
    for row in frame_rows:
        active_front = fnum(row, "active_front")
        frame_out.append(
            {
                "source_case": source_case,
                "time": row.get("t", ""),
                "frame_id": row.get("i", ""),
                "mean_exit_velocity": row.get("mean_exit_velocity", ""),
                "tau": fnum(row, "t") * mean_velocity / dh if dh else 0.0,
                "active_front": row.get("active_front", ""),
                "active_front_Dh": active_front / dh if dh else 0.0,
                "interface_proxy": row.get("interface_proxy", ""),
                "interface_growth": row.get("interface_growth", ""),
                "component_count": row.get("post_tag_count", ""),
                "detached_proxy_count": row.get("detached_proxy_count", ""),
                "one_cell_debris_count": row.get("one_cell_debris_count", ""),
                "quality_flag": "connected_core|not_stationary|not_for_model_fit",
                "source_metric_path": str(frames),
            }
        )

    station_fields = [
        "source_case",
        "time",
        "frame_id",
        "station_id",
        "x_from_exit",
        "xi",
        "zeta",
        "tau",
        "A",
        "Ahat",
        "equivalent_diameter",
        "width",
        "thickness",
        "aspect_ratio",
        "centroid_y",
        "centroid_z",
        "orientation_angle",
        "warp_proxy",
        "interface_growth_proxy",
        "component_count",
        "detached_proxy_count",
        "quality_flag",
        "source_metric_path",
    ]
    frame_fields = [
        "source_case",
        "time",
        "frame_id",
        "mean_exit_velocity",
        "tau",
        "active_front",
        "active_front_Dh",
        "interface_proxy",
        "interface_growth",
        "component_count",
        "detached_proxy_count",
        "one_cell_debris_count",
        "quality_flag",
        "source_metric_path",
    ]

    station_path = output_dir / "jet_station_metrics.csv"
    frame_path = output_dir / "jet_frame_summary.csv"
    schema_path = output_dir / "geometry_handoff_schema.json"
    write_csv(station_path, station_fields, station_rows)
    write_csv(frame_path, frame_fields, frame_out)
    schema = {
        "schema_name": "basilisk_internal_nozzle_geometry_handoff",
        "extraction_mode": "upstream_metric_repackaging",
        "selected_case": source_case,
        "geometry": {"W": width, "H": height, "Dh": dh, "A0": area0, "r0_equivalent": r0},
        "claim_boundary": [
            "not validation data",
            "not production CFD",
            "not stationary spray",
            "not pressure-atomized-nozzle validation",
            "not final predictive modeling",
        ],
    }
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return {
        "station_metrics": str(station_path),
        "frame_summary": str(frame_path),
        "schema": str(schema_path),
        "station_rows": len(station_rows),
        "frame_rows": len(frame_out),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repackage selected Basilisk internal-nozzle metrics without raw-field extraction."
    )
    parser.add_argument("--cross-sections", required=True, type=pathlib.Path)
    parser.add_argument("--frames", required=True, type=pathlib.Path)
    parser.add_argument("--output-dir", required=True, type=pathlib.Path)
    parser.add_argument("--source-case", default="W2_longer_duration")
    parser.add_argument("--width", type=float, default=DEFAULT_W)
    parser.add_argument("--height", type=float, default=DEFAULT_H)
    parser.add_argument("--dh", type=float, default=DEFAULT_DH)
    parser.add_argument("--mean-velocity", type=float, default=DEFAULT_UMEAN)
    args = parser.parse_args()

    result = build_outputs(
        args.cross_sections,
        args.frames,
        args.output_dir,
        args.source_case,
        args.width,
        args.height,
        args.dh,
        args.mean_velocity,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
