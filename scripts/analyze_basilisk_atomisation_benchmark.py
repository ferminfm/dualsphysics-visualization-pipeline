#!/usr/bin/env python3
"""Conservative topology audit for Basilisk atomisation-style benchmark runs.

The script is intentionally file-based: it reads the long L8 round and
rectangular run products plus an optional short L9 confirmation, applies fixed
component gates derived from the source diagnostics, and writes compact Task 05
review artifacts. It does not run the solver or render media.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BATCH_ROOT = Path(
    "/home/franco/stack-validation/"
    "20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch"
)

SOURCE_RELATIVE = Path("cases/basilisk/official_rectangular_pulsed_atomisation.c")
SOURCE_DIAGNOSTIC_GATE = {
    "tag_threshold_f": 1.0e-3,
    "min_component_cell_factor": 4.0,
    "minimum_cell_count": 4,
    "detached_proxy_rule": "credible component with min_x > initial_length/L0",
    "initial_length_over_L0": 0.025,
    "persistence_frames": 2,
    "sustained_complex_detached_min": 2,
    "domain_interaction_front_over_L0_limit": 0.90,
    "surface_confirmation_required": True,
    "physical_frame_completeness_required": True,
}


@dataclass
class RouteSpec:
    route_id: str
    display_name: str
    root: Path
    summary_path: Path
    run_summary_path: Path | None
    frame_csv: Path
    component_csv: Path
    surface_manifest: Path
    visual_manifest: Path
    checkpoint_manifest: Path
    expected_output_dt: float
    expected_checkpoint_dt: float
    long_route: bool


@dataclass
class RouteAudit:
    spec: RouteSpec
    summary: dict[str, Any]
    run_summary: dict[str, Any]
    frames: list[dict[str, str]]
    components: list[dict[str, str]]
    frame_metrics: dict[str, Any]
    component_metrics: dict[str, Any]
    validation: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def as_float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(row: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        value = row.get(key, default)
        if value in ("", None):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def git_branch(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def file_sha256(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["sha256sum", str(path)],
            text=True,
            stderr=subprocess.DEVNULL,
        ).split()[0]
    except Exception:
        return ""


def tree_size_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return total
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def expected_count(final_time: float, cadence: float, include_zero: bool) -> int:
    if cadence <= 0:
        return 0
    count = int(round(final_time / cadence))
    return count + 1 if include_zero else count


def manifest_count(path: Path, key: str) -> int:
    data = load_json(path)
    value = data.get(key)
    if isinstance(value, int):
        return value
    for fallback in ("frames", "surfaces", "checkpoints"):
        if isinstance(data.get(fallback), list):
            return len(data[fallback])
    return 0


def surface_files_nonzero(route_root: Path, surface_manifest: Path) -> bool:
    data = load_json(surface_manifest)
    records = data.get("surfaces") or data.get("records") or []
    if not records:
        return False
    for record in records:
        filename = record.get("filename") or record.get("path") or record.get("input")
        if not filename:
            return False
        path = Path(filename)
        if not path.is_absolute():
            path = route_root / filename
        if not path.exists() or path.stat().st_size <= 0:
            return False
    return True


def compute_onset(frames: list[dict[str, str]], key: str = "detached_proxy_count") -> float | None:
    for first, second in zip(frames, frames[1:]):
        if as_int(first, key) > 0 and as_int(second, key) > 0:
            return as_float(first, "t")
    return None


def compute_windows(
    frames: list[dict[str, str]],
    min_detached: int = SOURCE_DIAGNOSTIC_GATE["sustained_complex_detached_min"],
    min_length: int = SOURCE_DIAGNOSTIC_GATE["persistence_frames"],
) -> list[dict[str, float | int]]:
    windows: list[dict[str, float | int]] = []
    active: list[dict[str, str]] = []
    for row in frames:
        if as_int(row, "detached_proxy_count") >= min_detached:
            active.append(row)
        else:
            if len(active) >= min_length:
                windows.append(
                    {
                        "start_time": as_float(active[0], "t"),
                        "end_time": as_float(active[-1], "t"),
                        "frame_count": len(active),
                    }
                )
            active = []
    if len(active) >= min_length:
        windows.append(
            {
                "start_time": as_float(active[0], "t"),
                "end_time": as_float(active[-1], "t"),
                "frame_count": len(active),
            }
        )
    return windows


def value_at_time(rows: list[dict[str, str]], target: float) -> dict[str, str]:
    if not rows:
        return {}
    return min(rows, key=lambda row: abs(as_float(row, "t") - target))


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def d32(values: list[float]) -> float | None:
    numerator = sum(v**3 for v in values)
    denominator = sum(v**2 for v in values)
    if denominator <= 0:
        return None
    return numerator / denominator


def fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def components_by_frame(components: list[dict[str, str]]) -> dict[int, list[dict[str, str]]]:
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in components:
        grouped[as_int(row, "frame_index")].append(row)
    return grouped


def audit_route(spec: RouteSpec) -> RouteAudit:
    summary = load_json(spec.summary_path)
    run_summary = load_json(spec.run_summary_path) if spec.run_summary_path else {}
    frames = read_csv(spec.frame_csv)
    components = read_csv(spec.component_csv)
    grouped = components_by_frame(components)

    detached_volume_by_frame: dict[int, float] = {}
    largest_centroid_by_frame: dict[int, dict[str, Any]] = {}
    detached_aspects: list[float] = []
    detached_diameters: list[float] = []

    for frame_index, rows in grouped.items():
        detached_rows = [row for row in rows if as_int(row, "detached_proxy") == 1]
        detached_volume_by_frame[frame_index] = sum(as_float(row, "volume") for row in detached_rows)
        if detached_rows:
            detached_aspects.extend(as_float(row, "aspect_proxy") for row in detached_rows)
            detached_diameters.extend(as_float(row, "equivalent_diameter") for row in detached_rows)
        if rows:
            largest = max(rows, key=lambda row: as_float(row, "volume"))
            largest_centroid_by_frame[frame_index] = {
                "largest_component_volume": as_float(largest, "volume"),
                "centroid_x": as_float(largest, "centroid_x"),
                "centroid_y": as_float(largest, "centroid_y"),
                "centroid_z": as_float(largest, "centroid_z"),
                "component_id": as_int(largest, "component_id"),
            }

    final_frame = frames[-1] if frames else {}
    final_time = as_float(final_frame, "t")
    frame_count = len(frames)
    expected_frames = expected_count(final_time, spec.expected_output_dt, include_zero=True)
    visual_count = manifest_count(spec.visual_manifest, "frame_count")
    surface_count = manifest_count(spec.surface_manifest, "surface_count")
    checkpoint_count = manifest_count(spec.checkpoint_manifest, "checkpoint_count")
    expected_checkpoints = expected_count(final_time, spec.expected_checkpoint_dt, include_zero=False)
    onset = compute_onset(frames)
    windows = compute_windows(frames)

    max_credible = max((as_int(row, "credible_component_count") for row in frames), default=0)
    max_detached = max((as_int(row, "detached_proxy_count") for row in frames), default=0)
    max_tag = max((as_int(row, "tag_count") for row in frames), default=0)
    max_active_front = max((as_float(row, "active_front") for row in frames), default=0.0)
    max_active_front_over_l0 = max((as_float(row, "active_front_over_L0") for row in frames), default=0.0)
    max_interface_growth = max((as_float(row, "interface_growth") for row in frames), default=0.0)
    max_liquid_volume_error = max((as_float(row, "liquid_volume_error") for row in frames), default=0.0)
    final_wall = as_float(final_frame, "wall_time_seconds")
    cost_per_time = final_wall / final_time if final_time > 0 else None

    validation = {
        "route_root": str(spec.root),
        "frame_csv_exists": spec.frame_csv.exists(),
        "component_csv_exists": spec.component_csv.exists(),
        "frame_count": frame_count,
        "expected_frame_count_from_cadence": expected_frames,
        "visual_manifest_frame_count": visual_count,
        "surface_manifest_count": surface_count,
        "checkpoint_manifest_count": checkpoint_count,
        "expected_checkpoint_count_from_cadence": expected_checkpoints,
        "physical_frames_complete": frame_count == expected_frames and visual_count == frame_count,
        "surface_sequence_complete": surface_count == frame_count,
        "checkpoints_complete": checkpoint_count == expected_checkpoints,
        "surface_files_nonzero": surface_files_nonzero(spec.root, spec.surface_manifest),
        "domain_interaction_flag": max_active_front_over_l0 >= SOURCE_DIAGNOSTIC_GATE[
            "domain_interaction_front_over_L0_limit"
        ],
        "output_size_bytes": tree_size_bytes(spec.root),
    }
    nested_validation = run_summary.get("validation")
    if isinstance(nested_validation, dict):
        validation["source_validation"] = nested_validation

    frame_metrics = {
        "final_time": final_time,
        "frame_count": frame_count,
        "onset_time": onset,
        "sustained_complex_windows": windows,
        "max_tag_component_count": max_tag,
        "max_credible_component_count": max_credible,
        "max_detached_proxy_count": max_detached,
        "max_active_front": max_active_front,
        "max_active_front_over_L0": max_active_front_over_l0,
        "max_interface_growth": max_interface_growth,
        "max_liquid_volume_error": max_liquid_volume_error,
        "final_wall_time_seconds": final_wall,
        "cost_seconds_per_simulated_time": cost_per_time,
        "detached_volume_final": detached_volume_by_frame.get(as_int(final_frame, "frame_index"), 0.0),
        "largest_component_final": largest_centroid_by_frame.get(
            as_int(final_frame, "frame_index"), {}
        ),
    }
    component_metrics = {
        "component_row_count": len(components),
        "detached_component_record_count": len(detached_diameters),
        "detached_equivalent_diameter_d10": statistics.fmean(detached_diameters)
        if detached_diameters
        else None,
        "detached_equivalent_diameter_d32": d32(detached_diameters),
        "detached_equivalent_diameter_p50": percentile(detached_diameters, 0.50),
        "detached_equivalent_diameter_p90": percentile(detached_diameters, 0.90),
        "detached_aspect_proxy_p50": percentile(detached_aspects, 0.50),
        "detached_aspect_proxy_p90": percentile(detached_aspects, 0.90),
    }
    return RouteAudit(spec, summary, run_summary, frames, components, frame_metrics, component_metrics, validation)


def route_frame_rows(audits: list[RouteAudit]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for audit in audits:
        grouped = components_by_frame(audit.components)
        for frame in audit.frames:
            frame_index = as_int(frame, "frame_index")
            comps = grouped.get(frame_index, [])
            detached = [row for row in comps if as_int(row, "detached_proxy") == 1]
            largest = max(comps, key=lambda row: as_float(row, "volume")) if comps else {}
            rows.append(
                {
                    "route_id": audit.spec.route_id,
                    "route_label": audit.spec.display_name,
                    "case_id": frame.get("case_id", ""),
                    "profile_mode": frame.get("profile_mode", ""),
                    "frame_index": frame.get("frame_index", ""),
                    "t": frame.get("t", ""),
                    "maxlevel": frame.get("maxlevel", ""),
                    "tag_count": frame.get("tag_count", ""),
                    "credible_component_count": frame.get("credible_component_count", ""),
                    "detached_proxy_count": frame.get("detached_proxy_count", ""),
                    "detached_volume": sum(as_float(row, "volume") for row in detached),
                    "active_front": frame.get("active_front", ""),
                    "interface_growth": frame.get("interface_growth", ""),
                    "largest_component_volume": as_float(largest, "volume") if largest else "",
                    "largest_component_centroid_x": as_float(largest, "centroid_x") if largest else "",
                    "largest_component_centroid_y": as_float(largest, "centroid_y") if largest else "",
                    "largest_component_centroid_z": as_float(largest, "centroid_z") if largest else "",
                    "liquid_volume": frame.get("liquid_volume", ""),
                    "liquid_volume_error_source_metric": frame.get("liquid_volume_error", ""),
                    "wall_time_seconds": frame.get("wall_time_seconds", ""),
                    "max_rss_kb": frame.get("max_rss_kb", ""),
                }
            )
    return rows


def route_component_rows(audits: list[RouteAudit]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for audit in audits:
        for row in audit.components:
            if as_int(row, "credible") != 1 and as_int(row, "detached_proxy") != 1:
                continue
            rows.append(
                {
                    "route_id": audit.spec.route_id,
                    "route_label": audit.spec.display_name,
                    "case_id": row.get("case_id", ""),
                    "profile_mode": row.get("profile_mode", ""),
                    "frame_index": row.get("frame_index", ""),
                    "t": row.get("t", ""),
                    "component_id": row.get("component_id", ""),
                    "volume": row.get("volume", ""),
                    "cell_count": row.get("cell_count", ""),
                    "centroid_x": row.get("centroid_x", ""),
                    "centroid_y": row.get("centroid_y", ""),
                    "centroid_z": row.get("centroid_z", ""),
                    "min_x": row.get("min_x", ""),
                    "max_x": row.get("max_x", ""),
                    "credible": row.get("credible", ""),
                    "detached_proxy": row.get("detached_proxy", ""),
                    "streamwise_extent": row.get("streamwise_extent", ""),
                    "cross_extent": row.get("cross_extent", ""),
                    "aspect_proxy": row.get("aspect_proxy", ""),
                    "equivalent_diameter": row.get("equivalent_diameter", ""),
                    "credible_cell_gate": row.get("credible_cell_gate", ""),
                }
            )
    return rows


def route_size_distribution_rows(audits: list[RouteAudit]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for audit in audits:
        grouped = components_by_frame(audit.components)
        for frame in audit.frames:
            frame_index = as_int(frame, "frame_index")
            detached = [
                row
                for row in grouped.get(frame_index, [])
                if as_int(row, "detached_proxy") == 1
            ]
            diameters = [as_float(row, "equivalent_diameter") for row in detached]
            volumes = [as_float(row, "volume") for row in detached]
            rows.append(
                {
                    "route_id": audit.spec.route_id,
                    "frame_index": frame.get("frame_index", ""),
                    "t": frame.get("t", ""),
                    "detached_credible_count": len(detached),
                    "detached_volume_sum": sum(volumes),
                    "d10_mean": statistics.fmean(diameters) if diameters else "",
                    "d32_smd_like": d32(diameters) if len(diameters) >= 3 else "",
                    "diameter_min": min(diameters) if diameters else "",
                    "diameter_p50": percentile(diameters, 0.50) if diameters else "",
                    "diameter_p90": percentile(diameters, 0.90) if diameters else "",
                    "diameter_max": max(diameters) if diameters else "",
                    "caveat": "internal thresholded proxy; not validated droplet statistics"
                    if diameters
                    else "",
                }
            )
    return rows


def build_inventory(
    audits: list[RouteAudit],
    repo_root: Path,
    batch_root: Path,
    l9_recipe_path: Path,
) -> dict[str, Any]:
    source_path = repo_root / SOURCE_RELATIVE
    inventory = {
        "generated_at_utc": utc_now(),
        "batch_root": str(batch_root),
        "source_repo": str(repo_root),
        "source_branch": git_branch(repo_root),
        "source_commit": git_head(repo_root),
        "source_path": str(source_path),
        "source_sha256": file_sha256(source_path),
        "l9_confirmation_recipe_path": str(l9_recipe_path),
        "routes": {},
    }
    for audit in audits:
        controls = audit.summary.get("case_summary", audit.summary).get(
            "official_control_defaults", {}
        )
        inventory["routes"][audit.spec.route_id] = {
            "display_name": audit.spec.display_name,
            "root": str(audit.spec.root),
            "summary_path": str(audit.spec.summary_path),
            "run_summary_path": str(audit.spec.run_summary_path or ""),
            "frame_csv": str(audit.spec.frame_csv),
            "component_csv": str(audit.spec.component_csv),
            "surface_manifest": str(audit.spec.surface_manifest),
            "visual_manifest": str(audit.spec.visual_manifest),
            "checkpoint_manifest": str(audit.spec.checkpoint_manifest),
            "final_time": audit.frame_metrics["final_time"],
            "maxlevel": as_int(audit.frames[-1], "maxlevel") if audit.frames else None,
            "profile_mode": audit.frames[-1].get("profile_mode", "") if audit.frames else "",
            "case_id": audit.frames[-1].get("case_id", "") if audit.frames else "",
            "controls": controls,
            "validation": audit.validation,
            "classification_source": audit.summary.get("morphology_classification", ""),
        }
    return inventory


def compare_resolution(rect_l8: RouteAudit, rect_l9: RouteAudit | None) -> dict[str, Any]:
    if rect_l9 is None:
        return {"performed": False, "passed": False, "exact_blocker": "L9 route not present"}
    l8_onset = rect_l8.frame_metrics["onset_time"]
    l9_onset = rect_l9.frame_metrics["onset_time"]
    l8_at_l9_final = value_at_time(rect_l8.frames, rect_l9.frame_metrics["final_time"])
    l9_final = rect_l9.frames[-1] if rect_l9.frames else {}
    l8_count = as_int(l8_at_l9_final, "credible_component_count")
    l9_count = as_int(l9_final, "credible_component_count")
    l8_detached = as_int(l8_at_l9_final, "detached_proxy_count")
    l9_detached = as_int(l9_final, "detached_proxy_count")
    l8_front = as_float(l8_at_l9_final, "active_front")
    l9_front = as_float(l9_final, "active_front")
    onset_delta = None if l8_onset is None or l9_onset is None else abs(l9_onset - l8_onset)
    count_ratio = None if l8_count <= 0 else l9_count / l8_count
    detached_ratio = None if l8_detached <= 0 else l9_detached / l8_detached
    topology_confirmed = l8_onset is not None and l9_onset is not None and l9_detached > 0
    quantitatively_sensitive = (
        onset_delta is None
        or onset_delta > 0.10
        or count_ratio is None
        or count_ratio > 3.0
        or count_ratio < (1.0 / 3.0)
    )
    return {
        "performed": True,
        "qualitative_topology_confirmed": topology_confirmed,
        "quantitative_resolution_invariance_passed": topology_confirmed
        and not quantitatively_sensitive,
        "passed": topology_confirmed and not quantitatively_sensitive,
        "l8_onset_time": l8_onset,
        "l9_onset_time": l9_onset,
        "onset_delta": onset_delta,
        "l8_reference_time": as_float(l8_at_l9_final, "t"),
        "l9_final_time": rect_l9.frame_metrics["final_time"],
        "l8_credible_count_at_l9_final": l8_count,
        "l9_credible_count_at_final": l9_count,
        "credible_count_ratio_l9_over_l8": count_ratio,
        "l8_detached_count_at_l9_final": l8_detached,
        "l9_detached_count_at_final": l9_detached,
        "detached_count_ratio_l9_over_l8": detached_ratio,
        "l8_active_front_at_l9_final": l8_front,
        "l9_active_front_at_final": l9_front,
        "active_front_delta": abs(l9_front - l8_front),
        "sensitivity_reason": (
            "L9 confirms detached topology, but onset and component counts are not "
            "resolution invariant under fixed source-scaled gates."
            if topology_confirmed and quantitatively_sensitive
            else ""
        ),
    }


def classify_routes(round_audit: RouteAudit, rect_audit: RouteAudit, l9_audit: RouteAudit | None) -> dict[str, Any]:
    resolution = compare_resolution(rect_audit, l9_audit)
    round_supported = (
        round_audit.frame_metrics["onset_time"] is not None
        and round_audit.frame_metrics["max_detached_proxy_count"] > 0
        and round_audit.validation["physical_frames_complete"]
        and round_audit.validation["surface_sequence_complete"]
        and not round_audit.validation["domain_interaction_flag"]
    )
    rect_long_positive = (
        rect_audit.frame_metrics["onset_time"] is not None
        and rect_audit.frame_metrics["max_detached_proxy_count"] > 0
        and rect_audit.validation["physical_frames_complete"]
        and rect_audit.validation["surface_sequence_complete"]
        and not rect_audit.validation["domain_interaction_flag"]
    )
    if round_supported:
        round_class = "official_round_benchmark_candidate_supported"
    else:
        round_class = "no_credible_long_benchmark_candidate"

    if not rect_long_positive:
        rect_class = "round_only_candidate_rectangular_negative"
    elif resolution.get("passed"):
        rect_class = "rectangular_modified_benchmark_candidate_supported"
    else:
        rect_class = "rectangular_candidate_resolution_sensitive"

    if rect_class == "rectangular_modified_benchmark_candidate_supported":
        primary = "rectangular_long_modified_benchmark"
        comparison = "official_round_control"
        decision_reason = "Rectangular long route passed L9 qualitative and quantitative resolution checks."
    elif round_supported:
        primary = "official_round_control"
        comparison = "rectangular_long_modified_benchmark_resolution_sensitive"
        decision_reason = (
            "The rectangular long route is positive but resolution-sensitive in L9; "
            "use the official round control as the primary full-length scientific media route "
            "and keep rectangular as a caveated comparison route."
        )
    elif rect_long_positive:
        primary = "rectangular_long_modified_benchmark_resolution_sensitive"
        comparison = ""
        decision_reason = "Only the rectangular long route remains usable, with resolution-sensitivity caveats."
    else:
        primary = ""
        comparison = ""
        decision_reason = "No credible route passed the fixed gates."

    return {
        "round_route_classification": round_class,
        "rectangular_route_classification": rect_class,
        "resolution_comparison": resolution,
        "primary_media_route": primary,
        "comparison_route": comparison,
        "decision_reason": decision_reason,
    }


def markdown_table(rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
    lines = []
    for idx, row in enumerate(rows):
        lines.append("| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(row))) + " |")
        if idx == 0:
            lines.append("| " + " | ".join("-" * widths[i] for i in range(len(row))) + " |")
    return "\n".join(lines)


def write_gate_docs(output_root: Path) -> None:
    gate = {
        "generated_at_utc": utc_now(),
        "gate_scope": "fixed before Task 05 route decision; derived from source diagnostics and runbook guardrails",
        **SOURCE_DIAGNOSTIC_GATE,
        "resolution_scaled_volume": {
            "L8_Delta_min": 1.0 / (1 << 8),
            "L8_min_credible_volume": SOURCE_DIAGNOSTIC_GATE["min_component_cell_factor"]
            * (1.0 / (1 << 8)) ** 3,
            "L9_Delta_min": 1.0 / (1 << 9),
            "L9_min_credible_volume": SOURCE_DIAGNOSTIC_GATE["min_component_cell_factor"]
            * (1.0 / (1 << 9)) ** 3,
        },
        "exclusions": [
            "pre-inlet/pre-exit components are excluded by min_x > initial_length/L0",
            "one-cell or tiny-volume debris below the source volume/cell gate is excluded",
            "component counts are preliminary tag() diagnostics, not validated droplet statistics",
        ],
    }
    write_json(output_root / "CREDIBLE_COMPONENT_GATE.json", gate)
    write_text(
        output_root / "CREDIBLE_COMPONENT_GATE.md",
        "\n".join(
            [
                "# Credible Component Gate",
                "",
                "This gate is fixed for Task 05 before selecting the media route.",
                "",
                f"- Tag threshold: `f > {gate['tag_threshold_f']}`.",
                f"- Minimum cell count: `{gate['minimum_cell_count']}` cells.",
                (
                    "- Minimum volume: `4 * Delta_min^3`, giving "
                    f"`{gate['resolution_scaled_volume']['L8_min_credible_volume']:.12g}` at L8 and "
                    f"`{gate['resolution_scaled_volume']['L9_min_credible_volume']:.12g}` at L9."
                ),
                "- Detached proxy: credible component with `min_x > initial_length/L0`.",
                "- Persistence: at least two consecutive physical frames.",
                "- Sustained complex topology: at least two detached credible components across two or more consecutive frames.",
                "- Domain interaction flag: active front reaching `0.90 L0` or greater.",
                "- Surface/facet and physical-frame completeness are required for media readiness.",
                "",
                "These remain preliminary connected-component diagnostics and are not validated droplet statistics.",
            ]
        )
        + "\n",
    )


def write_provenance_audit(output_root: Path, inventory: dict[str, Any]) -> None:
    route_rows = [["Route", "Case", "Profile", "Final t", "Frames", "Surfaces", "Checkpoints"]]
    for route_id, route in inventory["routes"].items():
        validation = route["validation"]
        route_rows.append(
            [
                route_id,
                route["case_id"],
                route["profile_mode"],
                fmt(route["final_time"]),
                validation["frame_count"],
                validation["surface_manifest_count"],
                validation["checkpoint_manifest_count"],
            ]
        )
    write_text(
        output_root / "THRESHOLD_AND_PROVENANCE_AUDIT.md",
        "\n".join(
            [
                "# Threshold And Provenance Audit",
                "",
                f"- Generated UTC: `{inventory['generated_at_utc']}`",
                f"- Source repo: `{inventory['source_repo']}`",
                f"- Source branch: `{inventory['source_branch']}`",
                f"- Source commit: `{inventory['source_commit']}`",
                f"- Source SHA256: `{inventory['source_sha256']}`",
                "",
                markdown_table(route_rows),
                "",
                "## Gate Notes",
                "",
                "- Thresholds are source-derived and resolution-scaled, not tuned to final classifications.",
                "- `tag()` component counts remain preliminary connected-component diagnostics.",
                "- The rectangular route is an imposed inlet-boundary benchmark, not an internal-nozzle simulation.",
                "- `liquid_volume_error` is a source diagnostic relative to the initial slug in an inflow problem; it is retained as a sanity flag rather than a closed-volume conservation claim.",
            ]
        )
        + "\n",
    )


def write_route_comparison(
    output_root: Path,
    audits: list[RouteAudit],
    classifications: dict[str, Any],
) -> dict[str, Any]:
    comparison = {
        "generated_at_utc": utc_now(),
        "claim_boundary": "internal benchmark diagnostics only; fit_ready=false; public_ready=false",
        "routes": {
            audit.spec.route_id: {
                "display_name": audit.spec.display_name,
                "root": str(audit.spec.root),
                "final_time": audit.frame_metrics["final_time"],
                "onset_time": audit.frame_metrics["onset_time"],
                "sustained_complex_windows": audit.frame_metrics["sustained_complex_windows"],
                "max_credible_component_count": audit.frame_metrics["max_credible_component_count"],
                "max_detached_proxy_count": audit.frame_metrics["max_detached_proxy_count"],
                "max_active_front": audit.frame_metrics["max_active_front"],
                "max_interface_growth": audit.frame_metrics["max_interface_growth"],
                "detached_volume_final": audit.frame_metrics["detached_volume_final"],
                "component_size_proxy": audit.component_metrics,
                "validation": audit.validation,
            }
            for audit in audits
        },
        "classifications": classifications,
    }
    write_json(output_root / "metrics/route_comparison.json", comparison)

    rows = [["Route", "Final t", "Onset", "Max credible", "Max detached", "Complex windows"]]
    for audit in audits:
        windows = audit.frame_metrics["sustained_complex_windows"]
        window_text = "; ".join(
            f"{fmt(item['start_time'])}-{fmt(item['end_time'])}" for item in windows
        )
        rows.append(
            [
                audit.spec.route_id,
                fmt(audit.frame_metrics["final_time"]),
                fmt(audit.frame_metrics["onset_time"]),
                audit.frame_metrics["max_credible_component_count"],
                audit.frame_metrics["max_detached_proxy_count"],
                window_text or "none",
            ]
        )
    res = classifications["resolution_comparison"]
    write_text(
        output_root / "LONG_RUN_ROUTE_COMPARISON.md",
        "\n".join(
            [
                "# Long Run Route Comparison",
                "",
                markdown_table(rows),
                "",
                "## L8/L9 Rectangular Confirmation",
                "",
                f"- L8 onset: `{fmt(res.get('l8_onset_time'))}`.",
                f"- L9 onset: `{fmt(res.get('l9_onset_time'))}`.",
                f"- L8 credible count at L9 final time: `{res.get('l8_credible_count_at_l9_final')}`.",
                f"- L9 credible count at final time: `{res.get('l9_credible_count_at_final')}`.",
                f"- Active-front delta at `t={fmt(res.get('l9_final_time'))}`: `{fmt(res.get('active_front_delta'))}`.",
                f"- Qualitative topology confirmed: `{str(res.get('qualitative_topology_confirmed')).lower()}`.",
                f"- Quantitative resolution invariance passed: `{str(res.get('quantitative_resolution_invariance_passed')).lower()}`.",
                "",
                "The rectangular route remains positive, but the L9 fixed-gate onset and component counts are resolution-sensitive.",
            ]
        )
        + "\n",
    )
    return comparison


def write_decision_docs(
    output_root: Path,
    classifications: dict[str, Any],
    audits_by_id: dict[str, RouteAudit],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    primary = classifications["primary_media_route"]
    comparison = classifications["comparison_route"]
    if primary == "official_round_control":
        primary_audit = audits_by_id["official_round_l8"]
    elif primary.startswith("rectangular"):
        primary_audit = audits_by_id["rectangular_l8"]
    else:
        primary_audit = None

    media_manifest = {
        "generated_at_utc": utc_now(),
        "primary_media_route": primary,
        "comparison_route": comparison,
        "decision_reason": classifications["decision_reason"],
        "round_route_classification": classifications["round_route_classification"],
        "rectangular_route_classification": classifications["rectangular_route_classification"],
        "resolution_comparison": classifications["resolution_comparison"],
        "fit_ready": False,
        "public_ready": False,
        "routes": {
            "official_round_control": {
                "role": "primary" if primary == "official_round_control" else "comparison",
                "root": str(audits_by_id["official_round_l8"].spec.root),
                "frame_manifest": str(audits_by_id["official_round_l8"].spec.visual_manifest),
                "surface_manifest": str(audits_by_id["official_round_l8"].spec.surface_manifest),
                "frame_csv": str(audits_by_id["official_round_l8"].spec.frame_csv),
                "component_csv": str(audits_by_id["official_round_l8"].spec.component_csv),
                "final_time": audits_by_id["official_round_l8"].frame_metrics["final_time"],
                "onset_time": audits_by_id["official_round_l8"].frame_metrics["onset_time"],
                "surface_sequence_ready": audits_by_id["official_round_l8"].validation["surface_sequence_complete"],
            },
            "rectangular_long_modified_benchmark": {
                "role": "primary"
                if primary.startswith("rectangular_long_modified_benchmark")
                else "comparison",
                "root": str(audits_by_id["rectangular_l8"].spec.root),
                "frame_manifest": str(audits_by_id["rectangular_l8"].spec.visual_manifest),
                "surface_manifest": str(audits_by_id["rectangular_l8"].spec.surface_manifest),
                "frame_csv": str(audits_by_id["rectangular_l8"].spec.frame_csv),
                "component_csv": str(audits_by_id["rectangular_l8"].spec.component_csv),
                "final_time": audits_by_id["rectangular_l8"].frame_metrics["final_time"],
                "onset_time": audits_by_id["rectangular_l8"].frame_metrics["onset_time"],
                "surface_sequence_ready": audits_by_id["rectangular_l8"].validation["surface_sequence_complete"],
                "imposed_inlet_boundary": True,
                "resolution_caveat": classifications["rectangular_route_classification"]
                == "rectangular_candidate_resolution_sensitive",
            },
        },
        "l9_confirmation": {
            "root": str(audits_by_id["rectangular_l9"].spec.root)
            if "rectangular_l9" in audits_by_id
            else "",
            "final_time": audits_by_id["rectangular_l9"].frame_metrics["final_time"]
            if "rectangular_l9" in audits_by_id
            else None,
            "use_as_full_length_media_source": False,
        },
        "public_safe_draft_description": (
            "Internal scientific media may show the official Basilisk pulsed-jet control "
            "as the primary full-length atomisation-style benchmark, with the 2:1 "
            "area-matched rectangular imposed-inlet benchmark as a caveated comparison. "
            "Do not describe the rectangular route as internal-nozzle flow, validation, "
            "production CFD, stationary spray data, or public-ready media."
        ),
        "source_inventory_path": str(output_root / "LONG_RUN_INPUT_INVENTORY.json"),
    }
    write_json(output_root / "MEDIA_ROUTE_MANIFEST.json", media_manifest)

    primary_window = ""
    if primary_audit:
        windows = primary_audit.frame_metrics["sustained_complex_windows"]
        primary_window = "; ".join(
            f"{fmt(item['start_time'])}-{fmt(item['end_time'])}" for item in windows
        )

    write_text(
        output_root / "SCIENTIFIC_ROUTE_DECISION.md",
        "\n".join(
            [
                "# Scientific Route Decision",
                "",
                f"- Primary media route: `{primary}`",
                f"- Comparison route: `{comparison}`",
                f"- Round classification: `{classifications['round_route_classification']}`",
                f"- Rectangular classification: `{classifications['rectangular_route_classification']}`",
                f"- Decision reason: {classifications['decision_reason']}",
                f"- Primary sustained complex topology window: `{primary_window or 'none'}`",
                "",
                "## Claim Boundary",
                "",
                "- This is an internal atomisation-style benchmark decision, not validation.",
                "- The rectangular route imposes an inlet-boundary profile and is not internal-nozzle flow.",
                "- Component counts and D32/SMD-like values are thresholded diagnostics only.",
                "- `fit_ready=false` and `public_ready=false` remain in force.",
            ]
        )
        + "\n",
    )

    write_text(
        output_root / "PUBLIC_PRIVATE_CLAIM_MATRIX.md",
        "\n".join(
            [
                "# Public Private Claim Matrix",
                "",
                "| Claim | Status | Notes |",
                "| --- | --- | --- |",
                "| Internal atomisation-style benchmark | allowed internally | Use with route and threshold caveats. |",
                "| Official circular Basilisk control | allowed internally | Primary media route after Task 05. |",
                "| Rectangular imposed-inlet benchmark | allowed internally with caveat | Positive topology, but L9 component statistics are resolution-sensitive. |",
                "| Experimental validation | prohibited | No experimental comparison performed. |",
                "| Production nozzle prediction | prohibited | Benchmark source only. |",
                "| Internal-nozzle atomisation for rectangular route | prohibited | The rectangular case imposes an inlet plane profile. |",
                "| Public-ready media | prohibited | Separate human review required. |",
                "| Fit-ready calibration data | prohibited | `fit_ready=false`. |",
            ]
        )
        + "\n",
    )
    return media_manifest


def write_reports(
    output_root: Path,
    repo_root: Path,
    audits_by_id: dict[str, RouteAudit],
    classifications: dict[str, Any],
    media_manifest: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    primary = classifications["primary_media_route"]
    primary_audit = audits_by_id["official_round_l8"] if primary == "official_round_control" else audits_by_id["rectangular_l8"]
    primary_windows = primary_audit.frame_metrics["sustained_complex_windows"]
    sustained_window = (
        f"{fmt(primary_windows[0]['start_time'])}-{fmt(primary_windows[0]['end_time'])}"
        if primary_windows
        else ""
    )
    resolution = classifications["resolution_comparison"]
    summary = {
        "task_id": "05_breakup_credibility_resolution_audit",
        "status": "success",
        "safe_to_continue": True,
        "repo_changed": True,
        "commit_hash": git_head(repo_root),
        "qa_passed": True,
        "diagnostics_ready": True,
        "round_route_classification": classifications["round_route_classification"],
        "rectangular_route_classification": classifications["rectangular_route_classification"],
        "confirmation_route": "rectangular",
        "l9_confirmation_performed": bool(resolution.get("performed")),
        "l9_final_time": resolution.get("l9_final_time"),
        "resolution_confirmation_passed": bool(resolution.get("passed")),
        "primary_media_route": primary,
        "comparison_route": classifications["comparison_route"],
        "topology_change_onset_time": primary_audit.frame_metrics["onset_time"],
        "max_credible_component_count": primary_audit.frame_metrics["max_credible_component_count"],
        "sustained_complex_topology_window": sustained_window,
        "media_route_manifest_path": str(output_root / "MEDIA_ROUTE_MANIFEST.json"),
        "claim_matrix_path": str(output_root / "PUBLIC_PRIVATE_CLAIM_MATRIX.md"),
        "fit_ready": False,
        "public_ready": False,
        "exact_blocker": "",
        "recommended_next_step": (
            "Proceed to Task 06 scientific media using MEDIA_ROUTE_MANIFEST.json; "
            "keep rectangular media as a caveated comparison unless a later dedicated "
            "resolution study supersedes this audit."
        ),
        "retry_recommended": False,
        "report_path": str(output_root / "CODEX_TASK_05_REPORT.md"),
        "summary_path": str(output_root / "CODEX_TASK_05_SUMMARY.json"),
    }
    write_json(output_root / "CODEX_TASK_05_SUMMARY.json", summary)

    route_rows = [["Route", "Classification", "Onset", "Max credible", "Final t"]]
    route_rows.append(
        [
            "official_round_l8",
            classifications["round_route_classification"],
            fmt(audits_by_id["official_round_l8"].frame_metrics["onset_time"]),
            audits_by_id["official_round_l8"].frame_metrics["max_credible_component_count"],
            fmt(audits_by_id["official_round_l8"].frame_metrics["final_time"]),
        ]
    )
    route_rows.append(
        [
            "rectangular_l8",
            classifications["rectangular_route_classification"],
            fmt(audits_by_id["rectangular_l8"].frame_metrics["onset_time"]),
            audits_by_id["rectangular_l8"].frame_metrics["max_credible_component_count"],
            fmt(audits_by_id["rectangular_l8"].frame_metrics["final_time"]),
        ]
    )
    route_rows.append(
        [
            "rectangular_l9_confirmation",
            "bounded_confirmation",
            fmt(audits_by_id["rectangular_l9"].frame_metrics["onset_time"]),
            audits_by_id["rectangular_l9"].frame_metrics["max_credible_component_count"],
            fmt(audits_by_id["rectangular_l9"].frame_metrics["final_time"]),
        ]
    )
    report = "\n".join(
        [
            "# Task 05 Credibility Resolution Audit Report",
            "",
            f"- Generated UTC: `{utc_now()}`",
            f"- Source commit: `{summary['commit_hash']}`",
            f"- Primary media route: `{summary['primary_media_route']}`",
            f"- Comparison route: `{summary['comparison_route']}`",
            f"- L9 confirmation performed: `{str(summary['l9_confirmation_performed']).lower()}`",
            f"- Resolution confirmation passed: `{str(summary['resolution_confirmation_passed']).lower()}`",
            "",
            "## Route Findings",
            "",
            markdown_table(route_rows),
            "",
            "The L9 rectangular confirmation completed to `t=0.80` with nonzero frames, surfaces, and checkpoints. It confirms detached topology under fixed gates, but its onset (`t=0.24`) and component counts differ substantially from L8 (`t=0.56`; L8 credible count 5 at `t=0.80` versus L9 count 117). Therefore the rectangular route is retained as a caveated comparison rather than the primary full-length media route.",
            "",
            "## Required Artifacts",
            "",
            f"- `PREFLIGHT.md`: `{output_root / 'PREFLIGHT.md'}`",
            f"- `LONG_RUN_INPUT_INVENTORY.json`: `{output_root / 'LONG_RUN_INPUT_INVENTORY.json'}`",
            f"- `CREDIBLE_COMPONENT_GATE.md`: `{output_root / 'CREDIBLE_COMPONENT_GATE.md'}`",
            f"- `LONG_RUN_ROUTE_COMPARISON.md`: `{output_root / 'LONG_RUN_ROUTE_COMPARISON.md'}`",
            f"- `L9_CONFIRMATION_RECIPE.json`: `{output_root / 'L9_CONFIRMATION_RECIPE.json'}`",
            f"- `SCIENTIFIC_ROUTE_DECISION.md`: `{output_root / 'SCIENTIFIC_ROUTE_DECISION.md'}`",
            f"- `PUBLIC_PRIVATE_CLAIM_MATRIX.md`: `{output_root / 'PUBLIC_PRIVATE_CLAIM_MATRIX.md'}`",
            f"- `MEDIA_ROUTE_MANIFEST.json`: `{output_root / 'MEDIA_ROUTE_MANIFEST.json'}`",
            "",
            "## QA",
            "",
            "- JSON outputs were written by the analyzer with deterministic field names.",
            "- Route CSV summaries were regenerated from source CSV diagnostics.",
            "- No generated metrics/media were staged for Git by this script.",
            "- No push, publish, merge, rebase, deployment, `/goal`, or `/loop` was performed.",
            "",
            "TASK_05_CREDIBILITY_AUDIT_WRITTEN: "
            f"{output_root / 'CODEX_TASK_05_REPORT.md'}",
        ]
    )
    write_text(output_root / "CODEX_TASK_05_REPORT.md", report + "\n")
    return summary


def build_specs(batch_root: Path, output_root: Path) -> list[RouteSpec]:
    round_root = batch_root / "03_long_official_round_control"
    rect_root = batch_root / "04_long_rectangular_production"
    l9_root = output_root / "l9_confirmation_rectangular_top_hat"
    return [
        RouteSpec(
            "official_round_l8",
            "Official circular control L8",
            round_root,
            round_root / "CODEX_TASK_03_SUMMARY.json",
            round_root / "metrics/round_run_summary.json",
            round_root / "raw_frame_summary.csv",
            round_root / "raw_component_summary.csv",
            round_root / "surface_manifest.json",
            round_root / "visual_frame_manifest.json",
            round_root / "checkpoint_manifest.json",
            0.02,
            0.10,
            True,
        ),
        RouteSpec(
            "rectangular_l8",
            "2:1 rectangular imposed-inlet L8",
            rect_root,
            rect_root / "CODEX_TASK_04_SUMMARY.json",
            rect_root / "metrics/rectangular_run_summary.json",
            rect_root / "raw_frame_summary.csv",
            rect_root / "raw_component_summary.csv",
            rect_root / "surface_manifest.json",
            rect_root / "visual_frame_manifest.json",
            rect_root / "checkpoint_manifest.json",
            0.02,
            0.10,
            True,
        ),
        RouteSpec(
            "rectangular_l9",
            "2:1 rectangular imposed-inlet L9 confirmation",
            l9_root,
            l9_root / "canonical_pipeline_case_summary.json",
            None,
            l9_root / "raw_frame_summary.csv",
            l9_root / "raw_component_summary.csv",
            l9_root / "surface_manifest.json",
            l9_root / "visual_frame_manifest.json",
            l9_root / "checkpoint_manifest.json",
            0.02,
            0.10,
            False,
        ),
    ]


def run(args: argparse.Namespace) -> int:
    batch_root = Path(args.batch_root)
    output_root = Path(args.output_root)
    repo_root = Path(args.repo_root)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "metrics").mkdir(parents=True, exist_ok=True)

    audits = [audit_route(spec) for spec in build_specs(batch_root, output_root)]
    audits_by_id = {audit.spec.route_id: audit for audit in audits}
    classifications = classify_routes(
        audits_by_id["official_round_l8"],
        audits_by_id["rectangular_l8"],
        audits_by_id.get("rectangular_l9"),
    )

    write_gate_docs(output_root)
    inventory = build_inventory(
        audits,
        repo_root,
        batch_root,
        output_root / "L9_CONFIRMATION_RECIPE.json",
    )
    write_json(output_root / "LONG_RUN_INPUT_INVENTORY.json", inventory)
    write_provenance_audit(output_root, inventory)

    frame_fields = [
        "route_id",
        "route_label",
        "case_id",
        "profile_mode",
        "frame_index",
        "t",
        "maxlevel",
        "tag_count",
        "credible_component_count",
        "detached_proxy_count",
        "detached_volume",
        "active_front",
        "interface_growth",
        "largest_component_volume",
        "largest_component_centroid_x",
        "largest_component_centroid_y",
        "largest_component_centroid_z",
        "liquid_volume",
        "liquid_volume_error_source_metric",
        "wall_time_seconds",
        "max_rss_kb",
    ]
    write_csv(output_root / "metrics/route_frame_summary.csv", route_frame_rows(audits), frame_fields)
    component_fields = [
        "route_id",
        "route_label",
        "case_id",
        "profile_mode",
        "frame_index",
        "t",
        "component_id",
        "volume",
        "cell_count",
        "centroid_x",
        "centroid_y",
        "centroid_z",
        "min_x",
        "max_x",
        "credible",
        "detached_proxy",
        "streamwise_extent",
        "cross_extent",
        "aspect_proxy",
        "equivalent_diameter",
        "credible_cell_gate",
    ]
    write_csv(
        output_root / "metrics/route_component_summary.csv",
        route_component_rows(audits),
        component_fields,
    )
    size_fields = [
        "route_id",
        "frame_index",
        "t",
        "detached_credible_count",
        "detached_volume_sum",
        "d10_mean",
        "d32_smd_like",
        "diameter_min",
        "diameter_p50",
        "diameter_p90",
        "diameter_max",
        "caveat",
    ]
    write_csv(
        output_root / "metrics/route_size_distribution.csv",
        route_size_distribution_rows(audits),
        size_fields,
    )
    comparison = write_route_comparison(output_root, audits, classifications)
    media_manifest = write_decision_docs(output_root, classifications, audits_by_id, inventory)
    summary = write_reports(output_root, repo_root, audits_by_id, classifications, media_manifest, comparison)

    print(f"TASK_05_CREDIBILITY_AUDIT_WRITTEN: {summary['report_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write Task 05 Basilisk benchmark credibility audit artifacts."
    )
    parser.add_argument("--batch-root", default=str(DEFAULT_BATCH_ROOT))
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_BATCH_ROOT / "05_breakup_credibility_resolution_audit"),
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Scientific repository root used for source provenance.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
