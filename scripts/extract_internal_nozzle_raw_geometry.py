#!/usr/bin/env python3
"""Extract station-wise geometry metrics from Basilisk raw nozzle exports.

This script consumes the selective raw CSV files emitted by
`rectangular_internal_nozzle_raw_export.c`. It computes station slab liquid area,
normalized area, width/thickness, centroid, moments, orientation, and simple
warp proxies directly from exported VOF cell rows. It is an internal
fit-readiness diagnostic, not a validation or public-media tool.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
from collections import defaultdict
from typing import Iterable


DEFAULT_W = 0.208885689553
DEFAULT_H = 0.104442844776
DEFAULT_DH = 0.139257126368
DEFAULT_STATION_HALF_DH = 0.15


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: pathlib.Path, fieldnames: Iterable[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def as_float(row: dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value == "" or value is None:
        return default
    return float(value)


def as_int(row: dict[str, str], key: str, default: int = 0) -> int:
    value = row.get(key, "")
    if value == "" or value is None:
        return default
    return int(float(value))


def grouped(rows: Iterable[dict[str, str]], keys: tuple[str, ...]) -> dict[tuple[str, ...], list[dict[str, str]]]:
    out: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        out[tuple(row.get(k, "") for k in keys)].append(row)
    return out


def quality_flags(area: float, active_front: float, x_from_exit: float, rows: int) -> str:
    flags: list[str] = ["not_stationary", "not_for_model_fit"]
    if rows <= 0:
        flags.append("no_raw_rows")
    if area <= 0.0:
        flags.append("low_occupancy")
    else:
        flags.extend(["raw_field_extracted", "usable_for_shape_trend", "usable_for_model_overlay"])
    if active_front > 0.0 and x_from_exit >= 0.9 * active_front:
        flags.append("active_front_nearby")
    return "|".join(flags)


def station_metrics_from_raw(
    rows: list[dict[str, str]],
    frame_by_index: dict[str, dict[str, str]],
    width: float,
    height: float,
    dh: float,
    station_half_dh: float,
    liquid_threshold: float,
) -> list[dict[str, object]]:
    area0 = width * height
    r0 = math.sqrt(area0 / math.pi)
    metrics: list[dict[str, object]] = []
    for key, group in sorted(grouped(rows, ("case_id", "frame_index", "station_id")).items()):
        case_id, frame_index, station_id = key
        first = group[0]
        time = as_float(first, "t")
        xi = as_float(first, "xi")
        x_from_exit = as_float(first, "x_from_exit")
        weights: list[tuple[float, float, float, float]] = []
        liquid_rows = 0
        for row in group:
          f = as_float(row, "f")
          delta = as_float(row, "Delta")
          vol = as_float(row, "cell_volume_proxy")
          slab_width = 2.0 * max(station_half_dh * dh, 0.75 * delta)
          cell_area = f * vol / slab_width if slab_width > 0.0 else 0.0
          y = as_float(row, "y")
          z = as_float(row, "z")
          weights.append((cell_area, y, z, f))
          if f > liquid_threshold:
              liquid_rows += 1
        area = sum(w[0] for w in weights)
        if area > 0.0:
            cy = sum(w * y for w, y, _z, _f in weights) / area
            cz = sum(w * z for w, _y, z, _f in weights) / area
            covyy = sum(w * (y - cy) ** 2 for w, y, _z, _f in weights) / area
            covzz = sum(w * (z - cz) ** 2 for w, _y, z, _f in weights) / area
            covyz = sum(w * (y - cy) * (z - cz) for w, y, z, _f in weights) / area
            occupied = [(y, z) for _w, y, z, f in weights if f > liquid_threshold]
            if occupied:
                ys = [p[0] for p in occupied]
                zs = [p[1] for p in occupied]
                span_y = max(ys) - min(ys)
                span_z = max(zs) - min(zs)
            else:
                span_y = 0.0
                span_z = 0.0
            aspect = span_y / span_z if span_z > 0.0 else 0.0
            angle = 0.5 * math.atan2(2.0 * covyz, covyy - covzz) if covyy != covzz or covyz else 0.0
            warp = math.sqrt((covyy - covzz) ** 2 + 4.0 * covyz ** 2) / (covyy + covzz + 1e-30)
            equiv_d = math.sqrt(4.0 * area / math.pi)
        else:
            cy = cz = covyy = covzz = covyz = span_y = span_z = aspect = angle = warp = equiv_d = 0.0

        frame = frame_by_index.get(frame_index, {})
        active_front = as_float(frame, "active_front")
        metrics.append(
            {
                "source_case": case_id,
                "time": time,
                "frame_index": frame_index,
                "station_id": station_id,
                "xi": xi,
                "zeta": x_from_exit / r0 if r0 else 0.0,
                "x_from_exit": x_from_exit,
                "A": area,
                "Ahat": area / area0 if area0 else 0.0,
                "equivalent_diameter": equiv_d,
                "width": span_y,
                "thickness": span_z,
                "aspect_ratio": aspect,
                "centroid_y": cy,
                "centroid_z": cz,
                "moment_yy": covyy,
                "moment_zz": covzz,
                "moment_yz": covyz,
                "orientation_angle": angle,
                "warp_proxy": warp,
                "raw_rows": len(group),
                "liquid_rows": liquid_rows,
                "active_front": active_front,
                "active_front_Dh": active_front / dh if dh else 0.0,
                "interface_growth_proxy": frame.get("interface_growth", ""),
                "component_count": frame.get("post_tag_count", ""),
                "detached_proxy_count": frame.get("detached_proxy_count", ""),
                "quality_flag": quality_flags(area, active_front, x_from_exit, len(group)),
            }
        )
    return metrics


def interface_summary(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for frame_index, group in grouped(rows, ("frame_index",)).items():
        idx = frame_index[0]
        proxy = sum(as_float(row, "Delta") ** 2 for row in group)
        max_x = max((as_float(row, "x_from_exit") for row in group), default=0.0)
        out[idx] = {"interface_cell_rows": len(group), "raw_interface_proxy": proxy, "raw_interface_front": max_x}
    return out


def frame_summary_rows(frame_rows: list[dict[str, str]], iface: dict[str, dict[str, object]], dh: float) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in frame_rows:
        idx = row.get("frame_index", "")
        active_front = as_float(row, "active_front")
        iface_row = iface.get(idx, {})
        out.append(
            {
                "case_id": row.get("case_id", ""),
                "time": row.get("t", ""),
                "frame_index": idx,
                "mean_exit_velocity": row.get("mean_exit_velocity", ""),
                "exit_flow": row.get("exit_flow", ""),
                "exit_liquid_area": row.get("exit_liquid_area", ""),
                "profile_sanity": row.get("profile_sanity", ""),
                "liquid_volume_error": row.get("liquid_volume_error", ""),
                "active_front": active_front,
                "active_front_Dh": active_front / dh if dh else 0.0,
                "interface_proxy": row.get("interface_proxy", ""),
                "interface_growth": row.get("interface_growth", ""),
                "raw_interface_proxy": iface_row.get("raw_interface_proxy", 0.0),
                "raw_interface_front": iface_row.get("raw_interface_front", 0.0),
                "component_count": row.get("post_tag_count", ""),
                "detached_proxy_count": row.get("detached_proxy_count", ""),
                "one_cell_debris_count": row.get("one_cell_debris_count", ""),
            }
        )
    return out


def copy_component_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    return [
        {
            "case_id": row.get("case_id", ""),
            "time": row.get("t", ""),
            "component_id": row.get("component_id", ""),
            "tag_count": row.get("tag_count", ""),
            "volume": row.get("volume", ""),
            "cells": row.get("cells", ""),
            "centroid_x_from_exit": row.get("centroid_x_from_exit", ""),
            "centroid_y": row.get("centroid_y", ""),
            "centroid_z": row.get("centroid_z", ""),
            "credible": row.get("credible", ""),
            "region_flag": row.get("region_flag", ""),
        }
        for row in rows
    ]


def write_geometry_readme(path: pathlib.Path, source_case: str, extraction_mode: str) -> None:
    path.write_text(
        "\n".join(
            [
                "# Basilisk Internal-Nozzle Raw Geometry Handoff",
                "",
                f"Source case: `{source_case}`",
                f"Extraction mode: `{extraction_mode}`",
                "",
                "These metrics are computed from selective station-slab and interface-cell raw exports.",
                "They are internal fit-readiness diagnostics only. They are not validation data,",
                "not stationary spray data, and not public-ready atomisation evidence.",
                "",
                "The normalized coordinate is `xi = (x - x_exit)/Dh` and `Ahat = A/A0`.",
                "Quality flags preserve non-stationary and not-for-model-fit caveats.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract geometry metrics from Basilisk raw nozzle CSV exports.")
    parser.add_argument("--raw-dir", required=True, type=pathlib.Path)
    parser.add_argument("--output-root", required=True, type=pathlib.Path)
    parser.add_argument("--source-case", default="W2_longer_duration")
    parser.add_argument("--width", type=float, default=DEFAULT_W)
    parser.add_argument("--height", type=float, default=DEFAULT_H)
    parser.add_argument("--dh", type=float, default=DEFAULT_DH)
    parser.add_argument("--station-half-dh", type=float, default=DEFAULT_STATION_HALF_DH)
    parser.add_argument("--liquid-threshold", type=float, default=1e-3)
    args = parser.parse_args()

    raw_dir = args.raw_dir
    output_root = args.output_root
    metrics_dir = output_root / "metrics"
    handoff_dir = output_root / "geometry_handoff"
    station_rows = read_csv(raw_dir / "raw_station_cells.csv")
    interface_rows = read_csv(raw_dir / "raw_interface_cells.csv")
    frame_rows = read_csv(raw_dir / "raw_frame_summary.csv")
    component_rows = read_csv(raw_dir / "raw_component_summary.csv")
    case_rows = read_csv(raw_dir / "raw_case_summary.csv")

    if not station_rows:
        raise SystemExit(f"no station raw rows found in {raw_dir / 'raw_station_cells.csv'}")
    if not frame_rows:
        raise SystemExit(f"no frame summary rows found in {raw_dir / 'raw_frame_summary.csv'}")

    frame_by_index = {row.get("frame_index", ""): row for row in frame_rows}
    iface = interface_summary(interface_rows)
    station_metrics = station_metrics_from_raw(
        station_rows,
        frame_by_index,
        args.width,
        args.height,
        args.dh,
        args.station_half_dh,
        args.liquid_threshold,
    )
    frame_metrics = frame_summary_rows(frame_rows, iface, args.dh)
    component_metrics = copy_component_rows(component_rows)

    station_fields = [
        "source_case",
        "time",
        "frame_index",
        "station_id",
        "xi",
        "zeta",
        "x_from_exit",
        "A",
        "Ahat",
        "equivalent_diameter",
        "width",
        "thickness",
        "aspect_ratio",
        "centroid_y",
        "centroid_z",
        "moment_yy",
        "moment_zz",
        "moment_yz",
        "orientation_angle",
        "warp_proxy",
        "raw_rows",
        "liquid_rows",
        "active_front",
        "active_front_Dh",
        "interface_growth_proxy",
        "component_count",
        "detached_proxy_count",
        "quality_flag",
    ]
    frame_fields = [
        "case_id",
        "time",
        "frame_index",
        "mean_exit_velocity",
        "exit_flow",
        "exit_liquid_area",
        "profile_sanity",
        "liquid_volume_error",
        "active_front",
        "active_front_Dh",
        "interface_proxy",
        "interface_growth",
        "raw_interface_proxy",
        "raw_interface_front",
        "component_count",
        "detached_proxy_count",
        "one_cell_debris_count",
    ]
    component_fields = [
        "case_id",
        "time",
        "component_id",
        "tag_count",
        "volume",
        "cells",
        "centroid_x_from_exit",
        "centroid_y",
        "centroid_z",
        "credible",
        "region_flag",
    ]

    write_csv(metrics_dir / "raw_export_station_metrics.csv", station_fields, station_metrics)
    write_csv(metrics_dir / "raw_export_frame_summary.csv", frame_fields, frame_metrics)
    write_csv(metrics_dir / "raw_export_component_summary.csv", component_fields, component_metrics)
    write_csv(metrics_dir / "raw_export_case_summary.csv", case_rows[0].keys() if case_rows else ["case_id"], case_rows)
    write_csv(handoff_dir / "jet_station_metrics.csv", station_fields, station_metrics)

    schema = {
        "schema_name": "basilisk_internal_nozzle_raw_geometry_handoff",
        "source_case": args.source_case,
        "extraction_mode": "raw_station_slab_cell_extraction",
        "coordinate_system": {
            "streamwise": "x",
            "transverse": ["y", "z"],
            "xi": "(x - x_exit)/Dh",
            "Ahat": "A/A0",
        },
        "geometry": {
            "W": args.width,
            "H": args.height,
            "Dh": args.dh,
            "A0": args.width * args.height,
        },
        "quality_flags": [
            "not_stationary",
            "not_for_model_fit",
            "raw_field_extracted",
            "usable_for_shape_trend",
            "usable_for_model_overlay",
            "low_occupancy",
            "active_front_nearby",
        ],
        "claim_boundary": [
            "not validation data",
            "not production CFD",
            "not stationary spray",
            "not pressure-atomized-nozzle validation",
            "not final predictive modeling",
        ],
    }
    (handoff_dir / "jet_geometry_schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    write_geometry_readme(handoff_dir / "README.md", args.source_case, "raw_station_slab_cell_extraction")

    summary = {
        "raw_dir": str(raw_dir),
        "station_raw_rows": len(station_rows),
        "interface_raw_rows": len(interface_rows),
        "frame_rows": len(frame_rows),
        "component_rows": len(component_rows),
        "station_metric_rows": len(station_metrics),
        "frames_processed": sorted({row["frame_index"] for row in station_metrics}),
        "station_metrics_path": str(metrics_dir / "raw_export_station_metrics.csv"),
        "geometry_handoff_path": str(handoff_dir / "jet_station_metrics.csv"),
        "geometry_schema_path": str(handoff_dir / "jet_geometry_schema.json"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
