#!/usr/bin/env python3
"""Build model-handoff artifacts from raw Basilisk internal-nozzle metrics.

The input is the post-processed raw-field export directory created by
`extract_internal_nozzle_raw_geometry.py`. This script writes stack-validation
handoff CSV/JSON/README files for SprayGeo and Ideal Momentum Jet Explorer.

It never runs a solver and never upgrades the data to fit-ready status unless a
separate convergence gate has actually passed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
from collections import Counter, defaultdict
from typing import Iterable


QUALITY_FLAGS = [
    "inside_nozzle",
    "near_exit",
    "low_occupancy",
    "fragmented",
    "detached_dominated",
    "active_front_nearby",
    "boundary_clipped",
    "insufficient_resolution",
    "not_stationary",
    "usable_for_shape_trend",
    "usable_for_model_overlay",
    "not_for_model_fit",
]


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


def f(row: dict[str, object], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value in ("", None):
        return default
    return float(value)


def load_json(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def flag_map(row: dict[str, object], dh: float) -> dict[str, bool]:
    xi = f(row, "xi")
    area = f(row, "A")
    active_front = f(row, "active_front")
    x_from_exit = f(row, "x_from_exit")
    raw_rows = f(row, "raw_rows")
    detached = f(row, "detached_proxy_count")
    components = f(row, "component_count")
    low_occupancy = area <= 0.0
    near_exit = 0.0 <= xi <= 0.5
    active_front_nearby = bool(active_front > 0.0 and x_from_exit >= 0.9 * active_front)
    fragmented = bool(components > 1.0)
    return {
        "inside_nozzle": False,
        "near_exit": near_exit,
        "low_occupancy": low_occupancy,
        "fragmented": fragmented,
        "detached_dominated": bool(detached > 0 and fragmented),
        "active_front_nearby": active_front_nearby,
        "boundary_clipped": False,
        "insufficient_resolution": bool(raw_rows < 64),
        "not_stationary": True,
        "usable_for_shape_trend": bool(not low_occupancy),
        "usable_for_model_overlay": bool(not low_occupancy),
        "not_for_model_fit": True,
    }


def quality_string(flags: dict[str, bool]) -> str:
    return "|".join(name for name in QUALITY_FLAGS if flags[name])


def augment_station_rows(rows: list[dict[str, str]], manifest: dict[str, object]) -> list[dict[str, object]]:
    geometry = manifest.get("baseline_run", {})
    raw_manifest = manifest
    dh = float(raw_manifest.get("baseline_run", {}).get("Dh", 0.0) or 0.0)
    if not dh:
        # RAW_EXPORT_MANIFEST stores Dh in the geometry schema path; station rows already have xi/zeta.
        dh = 0.139257126368
    out: list[dict[str, object]] = []
    for row in rows:
        base: dict[str, object] = dict(row)
        flags = flag_map(base, dh)
        base["source_id"] = "basilisk_internal_nozzle_W2_E1_raw"
        base["source_type"] = "basilisk"
        base["simulation_source"] = "pressure_driven_internal_nozzle_vof"
        base["physical_validation"] = "none"
        base["post_transient"] = "false"
        base["stationarity_window_id"] = "none_nonstationary_transient"
        base["fit_readiness"] = "blocked_pending_matched_cadence_convergence"
        base["morphology_classification"] = "connected_internal_nozzle_jet_raw_export_reproduced"
        base["quality_flags"] = quality_string(flags)
        for name in QUALITY_FLAGS:
            base[name] = str(flags[name]).lower()
        base["Ahat_error_or_quality"] = "not_statistical_error;nonstationary_quality_flag"
        base["model_fit_allowed"] = "false"
        base["breakup_claim_allowed"] = "false"
        out.append(base)
    return out


def ideal_overlay_rows(station_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for row in station_rows:
        rows.append(
            {
                "zeta": row.get("zeta", ""),
                "xi": row.get("xi", ""),
                "Ahat": row.get("Ahat", ""),
                "Ahat_error": "",
                "Ahat_error_or_quality": row.get("Ahat_error_or_quality", ""),
                "source_case": "W2_longer_duration",
                "source_id": row.get("source_id", ""),
                "time": row.get("time", ""),
                "frame_index": row.get("frame_index", ""),
                "station_id": row.get("station_id", ""),
                "variable": "area",
                "quality_flag": row.get("quality_flags", ""),
                "fit_readiness": row.get("fit_readiness", ""),
                "model_fit_performed": "false",
                "public_ready": "false",
            }
        )
    return rows


def spraygeo_rows(station_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for row in station_rows:
        rows.append(
            {
                "source_id": row.get("source_id", ""),
                "source_type": row.get("source_type", ""),
                "simulation_source": row.get("simulation_source", ""),
                "physical_validation": row.get("physical_validation", ""),
                "z": row.get("x_from_exit", ""),
                "xi": row.get("xi", ""),
                "zeta": row.get("zeta", ""),
                "time": row.get("time", ""),
                "frame": row.get("frame_index", ""),
                "post_transient": row.get("post_transient", ""),
                "stationarity_window_id": row.get("stationarity_window_id", ""),
                "area_proxy": row.get("A", ""),
                "Ahat": row.get("Ahat", ""),
                "Ahat_error": "",
                "width": row.get("width", ""),
                "thickness": row.get("thickness", ""),
                "aspect_ratio": row.get("aspect_ratio", ""),
                "centroid_y": row.get("centroid_y", ""),
                "centroid_z": row.get("centroid_z", ""),
                "orientation_unwrapped_rad": row.get("orientation_angle", ""),
                "warp_proxy": row.get("warp_proxy", ""),
                "interface_growth_proxy": row.get("interface_growth_proxy", ""),
                "component_count": row.get("component_count", ""),
                "detached_proxy_count": row.get("detached_proxy_count", ""),
                "quality_flags": row.get("quality_flags", ""),
                "fit_readiness": row.get("fit_readiness", ""),
            }
        )
    return rows


def copy_frame_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["source_case"] = "W2_longer_duration"
        item["source_id"] = "basilisk_internal_nozzle_W2_E1_raw"
        item["quality_flags"] = "not_stationary|not_for_model_fit|usable_for_shape_trend"
        item["fit_readiness"] = "blocked_pending_matched_cadence_convergence"
        out.append(item)
    return out


def component_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["source_case"] = "W2_longer_duration"
        item["source_id"] = "basilisk_internal_nozzle_W2_E1_raw"
        item["breakup_claim_allowed"] = "false"
        item["interpretation"] = "connected-component diagnostic; not detached breakup evidence without tag count greater than one and visual confirmation"
        out.append(item)
    return out


def svg_line_plot(path: pathlib.Path, title: str, series: dict[str, list[tuple[float, float]]], ylabel: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height, margin = 820, 440, 64
    pts = [p for values in series.values() for p in values]
    if not pts:
        path.write_text(f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\"><text x=\"40\" y=\"80\">No data</text></svg>\n", encoding="utf-8")
        return
    xmax = max(x for x, _ in pts) or 1.0
    ymin = min(y for _, y in pts)
    ymax = max(y for _, y in pts)
    if math.isclose(ymin, ymax):
        ymin -= 1.0
        ymax += 1.0
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e"]
    def sx(x: float) -> float:
        return margin + (width - 2 * margin) * x / xmax
    def sy(y: float) -> float:
        return height - margin - (height - 2 * margin) * (y - ymin) / (ymax - ymin)
    pieces = [
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>",
        f"<text x=\"{margin}\" y=\"32\" font-family=\"sans-serif\" font-size=\"18\">{title}</text>",
        f"<line x1=\"{margin}\" y1=\"{height-margin}\" x2=\"{width-margin}\" y2=\"{height-margin}\" stroke=\"#222\"/>",
        f"<line x1=\"{margin}\" y1=\"{margin}\" x2=\"{margin}\" y2=\"{height-margin}\" stroke=\"#222\"/>",
        f"<text x=\"{width/2-30}\" y=\"{height-18}\" font-family=\"sans-serif\" font-size=\"13\">xi</text>",
        f"<text x=\"12\" y=\"{height/2}\" font-family=\"sans-serif\" font-size=\"13\" transform=\"rotate(-90 12,{height/2})\">{ylabel}</text>",
    ]
    for idx, (name, values) in enumerate(series.items()):
        values = sorted(values)
        color = colors[idx % len(colors)]
        poly = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in values)
        pieces.append(f"<polyline points=\"{poly}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2\"/>")
        pieces.extend(f"<circle cx=\"{sx(x):.2f}\" cy=\"{sy(y):.2f}\" r=\"3\" fill=\"{color}\"/>" for x, y in values)
        pieces.append(f"<text x=\"{width-margin-180}\" y=\"{margin+18*idx}\" font-family=\"sans-serif\" font-size=\"12\" fill=\"{color}\">{name}</text>")
    pieces.append(f"<text x=\"{margin}\" y=\"{height-margin+28}\" font-family=\"sans-serif\" font-size=\"11\">Internal diagnostic plot; not validation or public media.</text>")
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def bar_plot(path: pathlib.Path, title: str, counts: Counter[str]) -> None:
    width, height, margin = 900, 440, 70
    keys = list(counts)
    maxv = max(counts.values()) if counts else 1
    bw = (width - 2 * margin) / max(len(keys), 1)
    pieces = [
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>",
        f"<text x=\"{margin}\" y=\"32\" font-family=\"sans-serif\" font-size=\"18\">{title}</text>",
        f"<line x1=\"{margin}\" y1=\"{height-margin}\" x2=\"{width-margin}\" y2=\"{height-margin}\" stroke=\"#222\"/>",
    ]
    for i, key in enumerate(keys):
        val = counts[key]
        x = margin + i * bw + 4
        bar_h = (height - 2 * margin) * val / maxv
        y = height - margin - bar_h
        pieces.append(f"<rect x=\"{x:.2f}\" y=\"{y:.2f}\" width=\"{max(bw-8,2):.2f}\" height=\"{bar_h:.2f}\" fill=\"#4c78a8\"/>")
        pieces.append(f"<text x=\"{x:.2f}\" y=\"{height-margin+16}\" font-family=\"sans-serif\" font-size=\"10\" transform=\"rotate(45 {x:.2f},{height-margin+16})\">{key}</text>")
        pieces.append(f"<text x=\"{x:.2f}\" y=\"{y-4:.2f}\" font-family=\"sans-serif\" font-size=\"10\">{val}</text>")
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def write_readme(path: pathlib.Path, title: str, body: str) -> None:
    path.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Basilisk internal-nozzle geometry/model handoff from raw metrics.")
    parser.add_argument("--raw-root", required=True, type=pathlib.Path)
    parser.add_argument("--output-root", required=True, type=pathlib.Path)
    args = parser.parse_args()

    raw_root = args.raw_root
    out = args.output_root
    metrics_dir = raw_root / "metrics"
    handoff = out / "geometry_handoff"
    spray = out / "spraygeo_handoff"
    ideal = out / "ideal_explorer_overlay"
    plots = out / "plots"
    handoff.mkdir(parents=True, exist_ok=True)
    spray.mkdir(parents=True, exist_ok=True)
    ideal.mkdir(parents=True, exist_ok=True)
    plots.mkdir(parents=True, exist_ok=True)

    manifest = load_json(raw_root / "RAW_EXPORT_MANIFEST.json")
    raw_summary = load_json(raw_root / "CODEX_INTERNAL_NOZZLE_RAW_FIELD_EXPORT_RERUN_SUMMARY.json")
    station_in = read_csv(metrics_dir / "raw_export_station_metrics.csv")
    frame_in = read_csv(metrics_dir / "raw_export_frame_summary.csv")
    component_in = read_csv(metrics_dir / "raw_export_component_summary.csv")
    if not station_in:
        raise SystemExit(f"missing station metrics: {metrics_dir / 'raw_export_station_metrics.csv'}")
    if not frame_in:
        raise SystemExit(f"missing frame summary: {metrics_dir / 'raw_export_frame_summary.csv'}")

    station = augment_station_rows(station_in, manifest)
    frame = copy_frame_rows(frame_in)
    components = component_rows(component_in)
    spray_rows = spraygeo_rows(station)
    overlay = ideal_overlay_rows(station)

    station_fields = list(station[0].keys())
    frame_fields = list(frame[0].keys())
    component_fields = list(components[0].keys()) if components else [
        "case_id", "time", "component_id", "tag_count", "volume", "cells",
        "centroid_x_from_exit", "centroid_y", "centroid_z", "credible", "region_flag",
        "source_case", "source_id", "breakup_claim_allowed", "interpretation",
    ]
    spray_fields = list(spray_rows[0].keys())
    overlay_fields = list(overlay[0].keys())

    write_csv(handoff / "jet_station_metrics.csv", station_fields, station)
    write_csv(handoff / "jet_frame_summary.csv", frame_fields, frame)
    write_csv(handoff / "jet_component_summary.csv", component_fields, components)
    write_csv(spray / "basilisk_internal_nozzle_geometry_metrics.csv", spray_fields, spray_rows)
    write_csv(ideal / "basilisk_internal_nozzle_Ahat_overlay.csv", overlay_fields, overlay)

    schema = {
        "schema_name": "basilisk_internal_nozzle_geometry_model_handoff",
        "selected_case": "W2_longer_duration",
        "source_raw_root": str(raw_root),
        "morphology_classification": "connected_internal_nozzle_jet_raw_export_reproduced",
        "overlay_ready": True,
        "fit_ready": False,
        "exploratory_fit_ready": False,
        "reason_not_fit_ready": "matched-cadence L7/L8 station-shape convergence gate has not passed; data are nonstationary transient connected-jet geometry",
        "quality_flags": QUALITY_FLAGS,
        "claim_boundary": [
            "not validation",
            "not production CFD",
            "not stationary spray",
            "not true atomisation",
            "not public ready",
            "connected jet is not breakup",
        ],
        "station_columns": station_fields,
        "frame_columns": frame_fields,
        "component_columns": component_fields,
    }
    for path in [handoff / "jet_geometry_schema.json", spray / "schema.json", ideal / "schema.json"]:
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    write_readme(
        handoff / "README.md",
        "Basilisk Internal-Nozzle Geometry Handoff",
        "Station-wise metrics derived from corrected E1 raw VOF station-cell exports. "
        "The package is overlay-ready for internal reduced-model comparison, but not fit-ready. "
        "Quality flags explicitly mark the data as nonstationary and not for model fitting.",
    )
    write_readme(
        spray / "README.md",
        "SprayGeo Handoff",
        "CSV formatted for SprayGeo-style station geometry ingestion. "
        "`physical_validation=none` and `fit_readiness=blocked_pending_matched_cadence_convergence` are intentional.",
    )
    write_readme(
        ideal / "README.md",
        "Ideal Momentum Jet Explorer Overlay",
        "Use `zeta` as x, `Ahat` as y, optional `Ahat_error` blank, and variable `area`. "
        "This overlay is for internal visual comparison only; no model fit has been performed.",
    )

    final_frame = max(station, key=lambda r: float(r["time"]))["frame_index"]
    final_station = [r for r in station if r["frame_index"] == final_frame]
    nonzero_final = [r for r in final_station if f(r, "Ahat") > 0.0]
    svg_line_plot(plots / "Ahat_vs_xi.svg", "Ahat vs xi", {"final frame": [(f(r, "xi"), f(r, "Ahat")) for r in nonzero_final]}, "Ahat")
    svg_line_plot(
        plots / "width_thickness_vs_xi.svg",
        "Width and thickness vs xi",
        {
            "width": [(f(r, "xi"), f(r, "width")) for r in nonzero_final],
            "thickness": [(f(r, "xi"), f(r, "thickness")) for r in nonzero_final],
        },
        "length",
    )
    svg_line_plot(plots / "aspect_ratio_vs_xi.svg", "Aspect ratio vs xi", {"aspect": [(f(r, "xi"), f(r, "aspect_ratio")) for r in nonzero_final]}, "width/thickness")
    svg_line_plot(
        plots / "centroid_warp_vs_xi.svg",
        "Centroid and warp proxies vs xi",
        {
            "centroid_y": [(f(r, "xi"), f(r, "centroid_y")) for r in nonzero_final],
            "centroid_z": [(f(r, "xi"), f(r, "centroid_z")) for r in nonzero_final],
            "warp": [(f(r, "xi"), f(r, "warp_proxy")) for r in nonzero_final],
        },
        "proxy",
    )
    svg_line_plot(
        plots / "frame_evolution.svg",
        "Frame evolution",
        {
            "active_front_Dh": [(float(r["frame_index"]), f(r, "active_front_Dh")) for r in frame],
            "interface_growth": [(float(r["frame_index"]), f(r, "interface_growth")) for r in frame],
        },
        "value",
    )
    qcounter: Counter[str] = Counter()
    for row in station:
        for name in row["quality_flags"].split("|"):
            qcounter[name] += 1
    bar_plot(plots / "quality_flags.svg", "Quality flag distribution", qcounter)

    model_note = out / "MODEL_CONNECTION_NOTE.md"
    model_note.write_text(
        """# Model Connection Note

## Available Variables

- `A` and `Ahat`: station-wise liquid area proxy and normalized area.
- `width`, `thickness`, `aspect_ratio`: transverse extent metrics.
- `centroid_y`, `centroid_z`: centroid drift in the nozzle cross-plane.
- `orientation_angle`, `warp_proxy`: second-moment orientation and warp/skew proxy.
- `active_front`, `active_front_Dh`: transient front position.
- `interface_growth_proxy`: frame-level interface proxy from the raw-export run.
- component and detached-proxy counts: diagnostic context only.

## Model Mapping

- Ideal Explorer x-coordinate: `zeta` or `xi`.
- Ideal Explorer area variable: `Ahat`.
- SprayGeo station coordinate: `z = x_from_exit`, plus nondimensional `xi`.

## Readiness

The output is overlay-ready for internal visual comparison. It is not
exploratory-fit-ready because the matched-cadence L7/L8 station-shape convergence
gate has not passed and the selected case is a transient connected jet, not a
stationary spray.

## What Not To Infer

Do not infer breakup, validation, pressure-atomized-nozzle fidelity, stationary
spray behavior, or final predictive model calibration from these data.
""",
        encoding="utf-8",
    )
    convergence_plan = out / "CONVERGENCE_LIMITATION_AND_NEXT_RERUN_PLAN.md"
    convergence_plan.write_text(
        """# Convergence Limitation and Next Rerun Plan

## Current Limitation

E2 was an early-time maxlevel-8 raw export at `t=0.015`. It matched reduced
diagnostics at that early frame, but the active front was still upstream of the
fixed downstream station grid. Station-shape convergence is therefore partial
and cannot support exploratory-fit-ready status.

## Required Matched-Cadence Design

- Use the same pressure `351.48`, same internal-nozzle geometry, and same raw
  export schema as E1.
- Run L7 and L8 with matched output frames.
- Adapt station grids to the active-front range, including stations behind,
  near, and just ahead of the front.
- Preserve fixed stations at `xi = 0.25, 0.5, 0.75, 1.0, 1.5` when reached.
- Export station slabs, interface cloud, component diagnostics, and exit-profile
  samples at every matched frame.

## Stop Criteria

- Stop if L8 exceeds the bounded wall budget before the first active-front
  station window is reached.
- Stop if disk usage becomes risky or raw CSV size exceeds the documented
  bound.
- Stop if pressure-driven interpretation or no-slip/internal-nozzle setup is
  compromised.

## Suggested Bounds

- L7 reference: reuse corrected E1 or rerun with matched active-front-adaptive
  frames.
- L8: target the earliest frame where active front exceeds `0.5 Dh`; cap at
  45-60 minutes unless a separate review approves more.

## Pass/Fail Thresholds

- Ahat relative difference at occupied stations: target below 10-15%.
- width/thickness relative difference: target below 10-15%.
- centroid offset difference: target below one L7 cell width.
- interface proxy trend: same qualitative direction and within a documented
  tolerance.

Failing these thresholds keeps the package overlay-ready only, not fit-ready.
""",
        encoding="utf-8",
    )

    inventory = {
        "selected_case": "W2_longer_duration",
        "corrected_E1": manifest.get("baseline_run", {}),
        "E2_status": manifest.get("convergence_scout", {}),
        "active_front_range": {
            "min": min(f(r, "active_front") for r in station),
            "max": max(f(r, "active_front") for r in station),
        },
        "station_ids": sorted({str(r["station_id"]) for r in station}),
        "morphology_classification": "connected_internal_nozzle_jet_raw_export_reproduced",
        "raw_fields_consumed": True,
        "overlay_ready": True,
        "exploratory_fit_ready": False,
        "fit_ready": False,
        "why_connected_only": "tag count remains one and no validated detached breakup morphology is established",
        "why_convergence_partial": "E2 is early-time only; active front had not reached fixed station grid",
        "related_repos_read_only": [
            "/home/franco/Documents/GitHub/spray-jet-geometry-reduced-model",
            "/home/franco/Documents/GitHub/ideal-momentum-jet-explorer",
        ],
    }
    (out / "INPUT_INVENTORY.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    (out / "INPUT_INVENTORY.md").write_text(
        "# Input Inventory\n\n"
        "- selected case: `W2_longer_duration`\n"
        f"- corrected E1 pressure: `{manifest.get('baseline_run', {}).get('pressure_value')}`\n"
        f"- corrected E1 maxlevel: `{manifest.get('baseline_run', {}).get('maxlevel')}`\n"
        f"- corrected E1 end time: `{manifest.get('baseline_run', {}).get('end_time')}`\n"
        f"- E1 station raw rows: `{manifest.get('baseline_run', {}).get('station_raw_rows')}`\n"
        f"- E1 interface raw rows: `{manifest.get('baseline_run', {}).get('interface_raw_rows')}`\n"
        f"- E2 status: `{manifest.get('convergence_scout', {}).get('status')}`\n"
        f"- active-front range: `{inventory['active_front_range']}`\n"
        f"- station ids: `{', '.join(inventory['station_ids'])}`\n"
        "- morphology: `connected_internal_nozzle_jet_raw_export_reproduced`\n\n"
        "This is connected-jet geometry evidence only. The data are overlay-ready, not fit-ready.\n",
        encoding="utf-8",
    )

    preflight = out / "PREFLIGHT.md"
    preflight.write_text(
        "# Geometry Model Handoff Preflight\n\n"
        f"- raw root: `{raw_root}`\n"
        f"- upstream report exists: `{(raw_root / 'CODEX_INTERNAL_NOZZLE_RAW_FIELD_EXPORT_RERUN_REPORT.md').exists()}`\n"
        f"- station metrics exist: `{(metrics_dir / 'raw_export_station_metrics.csv').exists()}`\n"
        "- no solver run performed by this handoff script\n"
        "- no deploy, install, download, or main push\n",
        encoding="utf-8",
    )

    summary = {
        "selected_case": "W2_longer_duration",
        "raw_fields_consumed": True,
        "station_rows": len(station),
        "frame_rows": len(frame),
        "component_rows": len(components),
        "spraygeo_rows": len(spray_rows),
        "ideal_overlay_rows": len(overlay),
        "station_metrics_path": str(handoff / "jet_station_metrics.csv"),
        "spraygeo_handoff_path": str(spray / "basilisk_internal_nozzle_geometry_metrics.csv"),
        "ideal_explorer_overlay_path": str(ideal / "basilisk_internal_nozzle_Ahat_overlay.csv"),
        "model_connection_note_path": str(model_note),
        "convergence_plan_path": str(convergence_plan),
        "plot_paths": [str(p) for p in sorted(plots.glob("*.svg"))],
        "overlay_ready": True,
        "exploratory_fit_ready": False,
        "fit_ready": False,
        "public_ready": False,
        "raw_summary": raw_summary,
    }
    (out / "HANDOFF_BUILD_SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
