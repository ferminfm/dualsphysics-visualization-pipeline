#!/usr/bin/env python3
"""Collect diagnostics for the Basilisk periodic-span sheet bridge case.

The classification gate is deliberately conservative. A 3D periodic-span
bridge is not treated as a breakup proxy unless credible post-exit components
or detached-volume proxies survive basic volume/cell-count filters.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open(newline="") as f:
        yield from csv.DictReader(f)


def collect_frame_metrics(path: Path, threshold: float) -> dict[str, Any]:
    frame = None
    time = None
    volume = 0.0
    interface_area = 0.0
    weighted_x = weighted_y = weighted_z = 0.0
    weighted_x2 = weighted_y2 = weighted_z2 = 0.0
    active_front = 0.0
    active_front_any = False
    max_speed = 0.0
    count = 0
    interface_count = 0

    for row in _csv_rows(path):
        fval = _as_float(row.get("f"))
        if fval <= threshold:
            continue
        frame = _as_int(row.get("frame"))
        time = _as_float(row.get("time"))
        x = _as_float(row.get("x"))
        y = _as_float(row.get("y"))
        z = _as_float(row.get("z"))
        cell = _as_float(row.get("cell_size"))
        ux = _as_float(row.get("u_x"))
        uy = _as_float(row.get("u_y"))
        uz = _as_float(row.get("u_z"))
        dv = cell**3
        w = fval*dv
        volume += w
        weighted_x += w*x
        weighted_y += w*y
        weighted_z += w*z
        weighted_x2 += w*x*x
        weighted_y2 += w*y*y
        weighted_z2 += w*z*z
        if _as_int(row.get("interface_cell")):
            interface_area += cell*cell
            interface_count += 1
        if x >= 0.0:
            active_front = max(active_front, x)
            active_front_any = True
        max_speed = max(max_speed, math.sqrt(ux*ux + uy*uy + uz*uz))
        count += 1

    if volume > 0.0:
        cx = weighted_x/volume
        cy = weighted_y/volume
        cz = weighted_z/volume
        sx = math.sqrt(max(weighted_x2/volume - cx*cx, 0.0))
        sy = math.sqrt(max(weighted_y2/volume - cy*cy, 0.0))
        sz = math.sqrt(max(weighted_z2/volume - cz*cz, 0.0))
    else:
        cx = cy = cz = sx = sy = sz = 0.0

    return {
        "run_id": path.parent.name,
        "frame": frame if frame is not None else -1,
        "time": time if time is not None else 0.0,
        "liquid_volume_proxy": volume,
        "interface_area_proxy": interface_area,
        "liquid_cell_rows": count,
        "interface_cell_count": interface_count,
        "active_front": active_front if active_front_any else 0.0,
        "centroid_x": cx,
        "centroid_y": cy,
        "centroid_z": cz,
        "spread_x": sx,
        "spread_y": sy,
        "spread_z": sz,
        "aspect_xy": sx/sy if sy > 0.0 else 0.0,
        "spanwise_spread": sz,
        "max_speed": max_speed,
    }


def collect_component_metrics(path: Path, min_volume: float, min_cells: int) -> dict[str, Any]:
    components = []
    for row in _csv_rows(path):
        volume = _as_float(row.get("volume"))
        cell_count = _as_int(row.get("cell_count"))
        cx = _as_float(row.get("centroid_x"))
        detached = _as_int(row.get("detached_proxy"))
        credible = volume >= min_volume and cell_count >= min_cells and cx >= 0.05
        components.append(
            {
                "component_id": _as_int(row.get("component_id")),
                "volume": volume,
                "cell_count": cell_count,
                "centroid_x": cx,
                "centroid_y": _as_float(row.get("centroid_y")),
                "centroid_z": _as_float(row.get("centroid_z")),
                "detached_proxy": detached,
                "credible": credible,
                "credible_detached": credible and detached > 0,
            }
        )

    frame = -1
    time = 0.0
    if components:
        first = next(_csv_rows(path), None)
        if first:
            frame = _as_int(first.get("frame"))
            time = _as_float(first.get("time"))

    credible_count = sum(1 for c in components if c["credible"])
    credible_detached = sum(1 for c in components if c["credible_detached"])
    return {
        "run_id": path.parent.name,
        "frame": frame,
        "time": time,
        "raw_post_component_count": len(components),
        "credible_post_component_count": credible_count,
        "raw_detached_proxy_count": sum(1 for c in components if c["detached_proxy"]),
        "credible_detached_proxy_count": credible_detached,
        "max_component_volume": max((c["volume"] for c in components), default=0.0),
        "max_component_cells": max((c["cell_count"] for c in components), default=0),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def classify_run(frames: list[dict[str, Any]], comps: list[dict[str, Any]]) -> dict[str, Any]:
    if not frames:
        return {
            "morphology_label": "diagnostics_blocked",
            "bridge_candidate_found": False,
            "reason": "no interface frame diagnostics found",
        }

    base_candidates = [
        row["interface_area_proxy"]
        for row in frames
        if row["active_front"] >= 0.05 and row["interface_area_proxy"] > 0.0
    ]
    base_area = base_candidates[0] if base_candidates else (frames[0]["interface_area_proxy"] or 1.0)
    max_growth = max((row["interface_area_proxy"]/base_area for row in frames), default=1.0)
    max_active = max((row["active_front"] for row in frames), default=0.0)
    max_credible_components = max((row["credible_post_component_count"] for row in comps), default=0)
    max_credible_detached = max((row["credible_detached_proxy_count"] for row in comps), default=0)
    frames_with_components = sum(1 for row in comps if row["credible_post_component_count"] > 1)

    candidate = (
        max_active >= 0.5
        and frames_with_components > 0
        and max_credible_components > 1
        and (max_credible_detached > 0 or max_growth >= 2.5)
    )
    if candidate:
        label = "periodic_span_3d_bridge_candidate"
        reason = "credible post-exit components passed conservative 3D gate"
    elif max_active < 0.5:
        label = "insufficient_post_exit_window"
        reason = "active front did not reach 0.5 sheet thickness downstream"
    else:
        label = "periodic_span_negative_transfer_result"
        reason = "post-exit morphology stayed connected after credible-component filtering"

    return {
        "morphology_label": label,
        "bridge_candidate_found": candidate,
        "reason": reason,
        "max_active_front": max_active,
        "max_interface_area_growth": max_growth,
        "max_credible_post_component_count": max_credible_components,
        "max_credible_detached_proxy_count": max_credible_detached,
        "frames_with_credible_components_gt1": frames_with_components,
    }


def run_diagnostics(run_dirs: list[Path], output_dir: Path, threshold: float,
                    min_component_volume: float, min_component_cells: int) -> dict[str, Any]:
    frame_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []

    for run_dir in run_dirs:
        frames = [
            collect_frame_metrics(path, threshold)
            for path in sorted(run_dir.glob("interface_cells_*.csv"))
        ]
        comps = [
            collect_component_metrics(path, min_component_volume, min_component_cells)
            for path in sorted(run_dir.glob("post_components_*.csv"))
        ]
        result = classify_run(frames, comps)
        base_candidates = [
            row["interface_area_proxy"]
            for row in frames
            if row["active_front"] >= 0.05 and row["interface_area_proxy"] > 0.0
        ]
        base_area = base_candidates[0] if base_candidates else (frames[0]["interface_area_proxy"] if frames else 0.0)
        for row in frames:
            row["interface_area_growth"] = (
                row["interface_area_proxy"]/base_area if base_area > 0 else 0.0
            )
        frame_rows.extend(frames)
        component_rows.extend(comps)
        case_rows.append(
            {
                "run_id": run_dir.name,
                "frames": len(frames),
                "last_time": max((row["time"] for row in frames), default=0.0),
                "max_active_front": result.get("max_active_front", 0.0),
                "max_interface_area_growth": result.get("max_interface_area_growth", 0.0),
                "max_credible_post_component_count": result.get(
                    "max_credible_post_component_count", 0
                ),
                "max_credible_detached_proxy_count": result.get(
                    "max_credible_detached_proxy_count", 0
                ),
                "frames_with_credible_components_gt1": result.get(
                    "frames_with_credible_components_gt1", 0
                ),
                "bridge_candidate_found": result["bridge_candidate_found"],
                "morphology_label": result["morphology_label"],
                "classification_reason": result["reason"],
            }
        )

    frame_fields = [
        "run_id", "frame", "time", "liquid_volume_proxy", "interface_area_proxy",
        "interface_area_growth", "liquid_cell_rows", "interface_cell_count",
        "active_front", "centroid_x", "centroid_y", "centroid_z", "spread_x",
        "spread_y", "spread_z", "aspect_xy", "spanwise_spread", "max_speed",
    ]
    comp_fields = [
        "run_id", "frame", "time", "raw_post_component_count",
        "credible_post_component_count", "raw_detached_proxy_count",
        "credible_detached_proxy_count", "max_component_volume", "max_component_cells",
    ]
    case_fields = [
        "run_id", "frames", "last_time", "max_active_front",
        "max_interface_area_growth", "max_credible_post_component_count",
        "max_credible_detached_proxy_count", "frames_with_credible_components_gt1",
        "bridge_candidate_found", "morphology_label", "classification_reason",
    ]
    write_csv(output_dir/"periodic_bridge_frame_diagnostics.csv", frame_rows, frame_fields)
    write_csv(output_dir/"periodic_bridge_component_diagnostics.csv", component_rows, comp_fields)
    write_csv(output_dir/"periodic_bridge_case_summary.csv", case_rows, case_fields)

    summary = {
        "run_dirs": [str(path) for path in run_dirs],
        "case_count": len(case_rows),
        "bridge_candidate_found": any(row["bridge_candidate_found"] for row in case_rows),
        "max_tag_component_count": max(
            (row["max_credible_post_component_count"] for row in case_rows),
            default=0,
        ),
        "max_detached_proxy_count": max(
            (row["max_credible_detached_proxy_count"] for row in case_rows),
            default=0,
        ),
        "max_interface_area_growth": max(
            (row["max_interface_area_growth"] for row in case_rows),
            default=0.0,
        ),
        "case_summary_csv": str(output_dir/"periodic_bridge_case_summary.csv"),
        "frame_diagnostics_csv": str(output_dir/"periodic_bridge_frame_diagnostics.csv"),
        "component_diagnostics_csv": str(output_dir/"periodic_bridge_component_diagnostics.csv"),
    }
    with (output_dir/"periodic_bridge_parameter_map.json").open("w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="*", type=Path, help="Run directories to scan")
    parser.add_argument("--output-dir", type=Path, required=True, help="Metrics output directory")
    parser.add_argument("--threshold", type=float, default=1e-3, help="Liquid fraction threshold")
    parser.add_argument(
        "--min-component-volume",
        type=float,
        default=1e-4,
        help="Minimum post-exit component volume for credibility",
    )
    parser.add_argument(
        "--min-component-cells",
        type=int,
        default=8,
        help="Minimum post-exit component cell count for credibility",
    )
    args = parser.parse_args()

    run_dirs = [path for path in args.run_dirs if path.is_dir()]
    if not run_dirs:
        raise SystemExit("no valid run directories supplied")
    summary = run_diagnostics(
        run_dirs,
        args.output_dir,
        args.threshold,
        args.min_component_volume,
        args.min_component_cells,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
