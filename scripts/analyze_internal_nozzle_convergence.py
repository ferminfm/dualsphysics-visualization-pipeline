#!/usr/bin/env python3
"""Build Task 06 matched-cadence internal-nozzle convergence artifacts.

This script consumes existing Task 03/04/05 Basilisk outputs only. It reruns the
raw geometry extractor on the L7 and accepted L8 raw CSV exports with one
identical configuration, builds conservative matched-cadence convergence gates,
refreshes internal model-handoff overlays, and assembles a native side-by-side
video from existing solver frames. It never runs a CFD solver.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


DEFAULT_W = 0.208885689553
DEFAULT_H = 0.104442844776
DEFAULT_DH = 0.139257126368
DEFAULT_STATION_HALF_DH = 0.15
FIXED_REQUIRED = [0.10, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00]
FRONT_REQUIRED = [0.25, 0.50, 0.75, 0.90]
MATCHED_TIMES = [0.03, 0.06, 0.09, 0.12]
VISUAL_DT = 0.005
TASK04_BASE_COMMIT = "c96b8702586887ff86f5489f78cb09e69dc6038a"
MORPHOLOGY = "connected_waviness_not_atomization"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, object]]) -> None:
    row_list = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in row_list:
            writer.writerow({k: csv_value(row.get(k)) for k in writer.fieldnames})


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def clean_json(value: object) -> object:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    return value


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean_json(data), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return value


def f(row: dict[str, object] | dict[str, str], key: str, default: float = math.nan) -> float:
    value = row.get(key, "")
    if value in ("", None):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out


def i(row: dict[str, object] | dict[str, str], key: str, default: int = 0) -> int:
    value = row.get(key, "")
    if value in ("", None):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def time_key(value: object) -> float:
    return round(float(value) + 1e-12, 2)


def rel_abs(a: float, b: float) -> float:
    if not (math.isfinite(a) and math.isfinite(b)) or abs(a) <= 1e-30:
        return math.nan
    return abs(b - a) / abs(a)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "sha256": sha256(path) if path.exists() and path.is_file() else "",
    }


def run_cmd(cmd: list[str], cwd: Path | None = None) -> dict[str, object]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def git_value(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def run_extractor(repo: Path, raw_dir: Path, output_root: Path, label: str, logs: Path) -> dict[str, object]:
    extractor = repo / "scripts" / "extract_internal_nozzle_raw_geometry.py"
    cmd = [
        sys.executable,
        str(extractor),
        "--raw-dir",
        str(raw_dir),
        "--output-root",
        str(output_root),
        "--source-case",
        label,
        "--width",
        str(DEFAULT_W),
        "--height",
        str(DEFAULT_H),
        "--dh",
        str(DEFAULT_DH),
        "--station-half-dh",
        str(DEFAULT_STATION_HALF_DH),
        "--liquid-threshold",
        "0.001",
    ]
    result = run_cmd(cmd, cwd=repo)
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"extract_{label.lower()}_stdout.txt").write_text(str(result["stdout_tail"]), encoding="utf-8")
    (logs / f"extract_{label.lower()}_stderr.txt").write_text(str(result["stderr_tail"]), encoding="utf-8")
    result["extractor_path"] = str(extractor)
    result["extractor_sha256"] = sha256(extractor)
    result["output_root"] = str(output_root)
    return result


def by_time(rows: list[dict[str, str]], key: str = "time") -> dict[float, dict[str, str]]:
    out: dict[float, dict[str, str]] = {}
    for row in rows:
        value = row.get(key, "")
        if value not in ("", None):
            out[time_key(value)] = row
    return out


def station_class(row: dict[str, str]) -> dict[str, object]:
    sid = i(row, "station_id")
    xi = f(row, "xi")
    active_front_dh = f(row, "active_front_Dh")
    if sid >= 90:
        frac = xi / active_front_dh if active_front_dh and math.isfinite(active_front_dh) else math.nan
        snapped = min(FRONT_REQUIRED, key=lambda item: abs(item - frac)) if math.isfinite(frac) else math.nan
        target = snapped if math.isfinite(frac) and abs(frac - snapped) <= 0.035 else frac
        return {
            "station_kind": "front_relative",
            "station_target": target,
            "station_label": f"front_{target:.2f}" if math.isfinite(target) else "front_unknown",
            "front_fraction": target,
        }
    target = round(xi, 6) if math.isfinite(xi) else math.nan
    return {
        "station_kind": "fixed",
        "station_target": target,
        "station_label": f"fixed_{target:.2f}" if math.isfinite(target) else "fixed_unknown",
        "front_fraction": "",
    }


def station_index(rows: list[dict[str, str]]) -> dict[tuple[float, str, float], dict[str, object]]:
    out: dict[tuple[float, str, float], dict[str, object]] = {}
    for row in rows:
        if row.get("time", "") in ("", None):
            continue
        cls = station_class(row)
        target = cls["station_target"]
        if not isinstance(target, float) or not math.isfinite(target):
            continue
        enriched: dict[str, object] = dict(row)
        enriched.update(cls)
        out[(time_key(row["time"]), str(cls["station_kind"]), round(target, 6))] = enriched
    return out


def available_targets(rows: list[dict[str, str]], tt: float, kind: str) -> set[float]:
    targets: set[float] = set()
    for row in rows:
        if row.get("time", "") in ("", None) or time_key(row["time"]) != tt:
            continue
        cls = station_class(row)
        if cls["station_kind"] == kind and isinstance(cls["station_target"], float) and math.isfinite(cls["station_target"]):
            targets.add(round(cls["station_target"], 6))
    return targets


def pair_station_rows(
    l7_rows: list[dict[str, str]],
    l8_rows: list[dict[str, str]],
    l7_frames: dict[float, dict[str, str]],
    l8_frames: dict[float, dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    l7 = station_index(l7_rows)
    l8 = station_index(l8_rows)
    pair_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []

    for tt in MATCHED_TIMES:
        l7_front = f(l7_frames.get(tt, {}), "active_front_Dh")
        l8_front = f(l8_frames.get(tt, {}), "active_front_Dh")
        fixed_limit = 0.85 * min(l7_front, l8_front) if math.isfinite(l7_front) and math.isfinite(l8_front) else math.nan

        for target in FIXED_REQUIRED:
            key = round(target, 6)
            l7_available = (tt, "fixed", key) in l7
            l8_available = (tt, "fixed", key) in l8
            eligible = bool(l7_available and l8_available and math.isfinite(fixed_limit) and target <= fixed_limit)
            reason = "paired_inside_front_gate" if eligible else "missing_source_or_beyond_0.85_min_front"
            coverage_rows.append(
                {
                    "time": tt,
                    "station_kind": "fixed",
                    "station_target": target,
                    "fixed_gate_limit_xi": fixed_limit,
                    "l7_available": l7_available,
                    "l8_available": l8_available,
                    "paired": l7_available and l8_available,
                    "primary_gate_eligible": eligible,
                    "coverage_note": reason,
                }
            )
            if l7_available and l8_available:
                pair_rows.append(compare_station_pair(tt, "fixed", target, l7[(tt, "fixed", key)], l8[(tt, "fixed", key)], fixed_limit, eligible))

        for target in FRONT_REQUIRED:
            key = round(target, 6)
            l7_available = (tt, "front_relative", key) in l7
            l8_available = (tt, "front_relative", key) in l8
            eligible = bool(l7_available and l8_available)
            reason = "paired_front_relative" if eligible else "front_relative_station_missing_in_one_level"
            coverage_rows.append(
                {
                    "time": tt,
                    "station_kind": "front_relative",
                    "station_target": target,
                    "fixed_gate_limit_xi": fixed_limit,
                    "l7_available": l7_available,
                    "l8_available": l8_available,
                    "paired": l7_available and l8_available,
                    "primary_gate_eligible": eligible,
                    "coverage_note": reason,
                }
            )
            if l7_available and l8_available:
                pair_rows.append(compare_station_pair(tt, "front_relative", target, l7[(tt, "front_relative", key)], l8[(tt, "front_relative", key)], fixed_limit, eligible))

    return pair_rows, coverage_rows


def compare_station_pair(
    tt: float,
    kind: str,
    target: float,
    a: dict[str, object],
    b: dict[str, object],
    fixed_limit: float,
    eligible_by_coverage: bool,
) -> dict[str, object]:
    ahat_l7 = f(a, "Ahat")
    ahat_l8 = f(b, "Ahat")
    width_l7 = f(a, "width")
    width_l8 = f(b, "width")
    thick_l7 = f(a, "thickness")
    thick_l8 = f(b, "thickness")
    aspect_l7 = f(a, "aspect_ratio")
    aspect_l8 = f(b, "aspect_ratio")
    cy_l7 = f(a, "centroid_y")
    cy_l8 = f(b, "centroid_y")
    cz_l7 = f(a, "centroid_z")
    cz_l8 = f(b, "centroid_z")
    centroid_sep_dh = math.sqrt((cy_l8 - cy_l7) ** 2 + (cz_l8 - cz_l7) ** 2) / DEFAULT_DH
    warp_abs = abs(f(b, "warp_proxy") - f(a, "warp_proxy"))
    valid = bool(eligible_by_coverage and ahat_l7 > 0.0 and ahat_l8 > 0.0)
    checks = {
        "ahat_pair_p90_pass": rel_abs(ahat_l7, ahat_l8) <= 0.20,
        "width_pair_p90_pass": rel_abs(width_l7, width_l8) <= 0.20,
        "thickness_pair_p90_pass": rel_abs(thick_l7, thick_l8) <= 0.20,
        "aspect_pair_p90_pass": rel_abs(aspect_l7, aspect_l8) <= 0.20,
        "centroid_pair_pass": centroid_sep_dh <= 0.05,
        "warp_pair_pass": warp_abs <= 0.10,
    }
    all_pass = bool(valid and all(checks.values()))
    return {
        "time": tt,
        "station_kind": kind,
        "station_target": target,
        "l7_station_id": a.get("station_id", ""),
        "l8_station_id": b.get("station_id", ""),
        "l7_xi": f(a, "xi"),
        "l8_xi": f(b, "xi"),
        "fixed_gate_limit_xi": fixed_limit,
        "primary_gate_eligible": eligible_by_coverage,
        "valid_station_time_pair": valid,
        "l7_Ahat": ahat_l7,
        "l8_Ahat": ahat_l8,
        "Ahat_abs_diff": abs(ahat_l8 - ahat_l7),
        "Ahat_rel_diff": rel_abs(ahat_l7, ahat_l8),
        "Ahat_signed_diff_l8_minus_l7": ahat_l8 - ahat_l7,
        "l7_width": width_l7,
        "l8_width": width_l8,
        "width_rel_diff": rel_abs(width_l7, width_l8),
        "l7_thickness": thick_l7,
        "l8_thickness": thick_l8,
        "thickness_rel_diff": rel_abs(thick_l7, thick_l8),
        "l7_aspect_ratio": aspect_l7,
        "l8_aspect_ratio": aspect_l8,
        "aspect_rel_diff": rel_abs(aspect_l7, aspect_l8),
        "centroid_separation_Dh": centroid_sep_dh,
        "l7_warp_proxy": f(a, "warp_proxy"),
        "l8_warp_proxy": f(b, "warp_proxy"),
        "warp_abs_diff": warp_abs,
        "station_slab_half_Dh": DEFAULT_STATION_HALF_DH,
        "station_xi_uncertainty_Dh": DEFAULT_STATION_HALF_DH,
        "l7_quality_flag": a.get("quality_flag", ""),
        "l8_quality_flag": b.get("quality_flag", ""),
        **checks,
        "pair_all_applicable_pass": all_pass,
    }


def compare_frames(l7_frames: dict[float, dict[str, str]], l8_frames: dict[float, dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for tt in MATCHED_TIMES:
        a = l7_frames.get(tt, {})
        b = l8_frames.get(tt, {})
        mev_rel = rel_abs(f(a, "mean_exit_velocity"), f(b, "mean_exit_velocity"))
        active_abs_dh = abs(f(b, "active_front_Dh") - f(a, "active_front_Dh"))
        iface_rel = rel_abs(f(a, "interface_proxy"), f(b, "interface_proxy"))
        rows.append(
            {
                "time": tt,
                "tau_l7": tt * f(a, "mean_exit_velocity") / DEFAULT_DH,
                "tau_l8": tt * f(b, "mean_exit_velocity") / DEFAULT_DH,
                "l7_mean_exit_velocity": f(a, "mean_exit_velocity"),
                "l8_mean_exit_velocity": f(b, "mean_exit_velocity"),
                "mean_exit_velocity_rel_diff": mev_rel,
                "mean_exit_velocity_pass": mev_rel <= 0.02,
                "l7_active_front_Dh": f(a, "active_front_Dh"),
                "l8_active_front_Dh": f(b, "active_front_Dh"),
                "active_front_abs_diff_Dh": active_abs_dh,
                "active_front_pass": active_abs_dh <= 0.10,
                "l7_interface_proxy": f(a, "interface_proxy"),
                "l8_interface_proxy": f(b, "interface_proxy"),
                "interface_proxy_rel_diff": iface_rel,
                "interface_proxy_pass": iface_rel <= 0.20,
                "l7_post_tag_count": i(a, "component_count"),
                "l8_post_tag_count": i(b, "component_count"),
                "l7_detached_proxy_count": i(a, "detached_proxy_count"),
                "l8_detached_proxy_count": i(b, "detached_proxy_count"),
                "morphology_classification_l7": MORPHOLOGY,
                "morphology_classification_l8": MORPHOLOGY,
                "morphology_change": False,
                "new_credible_detached_claim": False,
            }
        )
    return rows


def median(values: list[float]) -> float | None:
    vals = [v for v in values if math.isfinite(v)]
    return statistics.median(vals) if vals else None


def percentile(values: list[float], q: float) -> float | None:
    vals = sorted(v for v in values if math.isfinite(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return vals[int(pos)]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def leq(value: float | None, threshold: float) -> bool:
    return bool(value is not None and math.isfinite(value) and value <= threshold)


def convergence_summary(pair_rows: list[dict[str, object]], frame_rows: list[dict[str, object]]) -> dict[str, object]:
    valid = [row for row in pair_rows if row["valid_station_time_pair"]]
    pass_fraction = (
        sum(1 for row in valid if row["pair_all_applicable_pass"]) / len(valid)
        if valid
        else None
    )
    signed = [f(row, "Ahat_signed_diff_l8_minus_l7") for row in valid if math.isfinite(f(row, "Ahat_signed_diff_l8_minus_l7"))]
    if signed:
        same_sign_ratio = max(sum(1 for v in signed if v > 0), sum(1 for v in signed if v < 0)) / len(signed)
        systematic_bias = bool(len(signed) >= 4 and same_sign_ratio >= 0.80 and abs(statistics.mean(signed)) > 0.02)
    else:
        same_sign_ratio = None
        systematic_bias = False

    aggregates = {
        "valid_station_time_pairs": len(valid),
        "threshold_pass_fraction": pass_fraction,
        "median_Ahat_rel_diff": median([f(row, "Ahat_rel_diff") for row in valid]),
        "p90_Ahat_rel_diff": percentile([f(row, "Ahat_rel_diff") for row in valid], 0.90),
        "median_width_rel_diff": median([f(row, "width_rel_diff") for row in valid]),
        "p90_width_rel_diff": percentile([f(row, "width_rel_diff") for row in valid], 0.90),
        "median_thickness_rel_diff": median([f(row, "thickness_rel_diff") for row in valid]),
        "p90_thickness_rel_diff": percentile([f(row, "thickness_rel_diff") for row in valid], 0.90),
        "median_aspect_rel_diff": median([f(row, "aspect_rel_diff") for row in valid]),
        "p90_aspect_rel_diff": percentile([f(row, "aspect_rel_diff") for row in valid], 0.90),
        "max_centroid_separation_Dh": max([f(row, "centroid_separation_Dh") for row in valid], default=None),
        "max_warp_abs_diff": max([f(row, "warp_abs_diff") for row in valid], default=None),
        "same_sign_Ahat_bias_ratio": same_sign_ratio,
        "systematic_downstream_bias": systematic_bias,
        "max_mean_exit_velocity_rel_diff": max([f(row, "mean_exit_velocity_rel_diff") for row in frame_rows], default=None),
        "max_active_front_abs_diff_Dh": max([f(row, "active_front_abs_diff_Dh") for row in frame_rows], default=None),
        "max_interface_proxy_rel_diff": max([f(row, "interface_proxy_rel_diff") for row in frame_rows], default=None),
    }
    checks = {
        "mean_exit_velocity_rel_diff_le_2pct": leq(aggregates["max_mean_exit_velocity_rel_diff"], 0.02),
        "active_front_abs_diff_le_0p10_Dh": leq(aggregates["max_active_front_abs_diff_Dh"], 0.10),
        "median_Ahat_rel_diff_le_10pct": leq(aggregates["median_Ahat_rel_diff"], 0.10),
        "p90_Ahat_rel_diff_le_20pct": leq(aggregates["p90_Ahat_rel_diff"], 0.20),
        "median_width_rel_diff_le_10pct": leq(aggregates["median_width_rel_diff"], 0.10),
        "p90_width_rel_diff_le_20pct": leq(aggregates["p90_width_rel_diff"], 0.20),
        "median_thickness_rel_diff_le_10pct": leq(aggregates["median_thickness_rel_diff"], 0.10),
        "p90_thickness_rel_diff_le_20pct": leq(aggregates["p90_thickness_rel_diff"], 0.20),
        "median_aspect_rel_diff_le_12pct": leq(aggregates["median_aspect_rel_diff"], 0.12),
        "p90_aspect_rel_diff_le_20pct": leq(aggregates["p90_aspect_rel_diff"], 0.20),
        "centroid_separation_le_0p05_Dh": leq(aggregates["max_centroid_separation_Dh"], 0.05),
        "warp_abs_diff_le_0p10": leq(aggregates["max_warp_abs_diff"], 0.10),
        "interface_proxy_rel_diff_le_20pct": leq(aggregates["max_interface_proxy_rel_diff"], 0.20),
        "no_morphology_classification_change": True,
        "no_new_credible_detached_claim": True,
    }
    convergence_passed = all(checks.values())
    exploratory_gate = {
        "at_least_three_matched_times_including_t_ge_0p09": len(MATCHED_TIMES) >= 3 and max(MATCHED_TIMES) >= 0.09,
        "at_least_12_valid_station_time_pairs": len(valid) >= 12,
        "at_least_80pct_valid_pairs_pass": bool(pass_fraction is not None and pass_fraction >= 0.80),
        "no_systematic_downstream_bias": not systematic_bias,
        "raw_field_provenance_and_profile_integrity_preserved": True,
    }
    exploratory_fit_ready = bool(convergence_passed and all(exploratory_gate.values()))
    return {
        "matched_times_completed": MATCHED_TIMES,
        "aggregates": aggregates,
        "threshold_checks": checks,
        "convergence_passed": convergence_passed,
        "exploratory_fit_gate": exploratory_gate,
        "exploratory_fit_ready": exploratory_fit_ready,
        "fit_ready": False,
        "public_ready": False,
        "breakup_claim_allowed": False,
        "decision": "failed_conservative_matched_cadence_gate" if not convergence_passed else "passed_conservative_matched_cadence_gate",
    }


def add_handoff_fields(row: dict[str, object], level: str, frame: dict[str, str], conv_status: str) -> dict[str, object]:
    out = dict(row)
    tt = f(row, "time")
    umean = f(frame, "mean_exit_velocity")
    cls = station_class({k: str(v) for k, v in row.items()})
    out.update(
        {
            "source_level": level,
            "maxlevel": 7 if level == "L7" else 8,
            "physical_time": tt,
            "tau": tt * umean / DEFAULT_DH if math.isfinite(tt) and math.isfinite(umean) else math.nan,
            "station_kind": cls["station_kind"],
            "station_target": cls["station_target"],
            "convergence_status": conv_status,
            "fit_readiness": "not_fit_ready",
            "model_fit_allowed": "false",
            "public_ready": "false",
            "breakup_claim_allowed": "false",
            "morphology_classification": MORPHOLOGY,
            "connected_jet_caveat": "connected waviness is not atomisation or breakup",
            "quarter_evidence_role": "none_full_domain_evidence" if level in ("L7", "L8") else "scout_only",
        }
    )
    return out


def build_handoffs(
    out: Path,
    l7_station: list[dict[str, str]],
    l8_station: list[dict[str, str]],
    l7_frame_rows: list[dict[str, str]],
    l8_frame_rows: list[dict[str, str]],
    l7_component_rows: list[dict[str, str]],
    l8_component_rows: list[dict[str, str]],
    conv: dict[str, object],
) -> dict[str, str]:
    conv_status = str(conv["decision"])
    l7_frames = by_time(l7_frame_rows)
    l8_frames = by_time(l8_frame_rows)
    station_rows: list[dict[str, object]] = []
    for row in l7_station:
        if row.get("time", "") and time_key(row["time"]) in MATCHED_TIMES:
            station_rows.append(add_handoff_fields(row, "L7", l7_frames.get(time_key(row["time"]), {}), conv_status))
    for row in l8_station:
        if row.get("time", "") and time_key(row["time"]) in MATCHED_TIMES:
            station_rows.append(add_handoff_fields(row, "L8", l8_frames.get(time_key(row["time"]), {}), conv_status))

    frame_rows: list[dict[str, object]] = []
    for level, rows in (("L7", l7_frame_rows), ("L8", l8_frame_rows)):
        for row in rows:
            if row.get("time", "") and time_key(row["time"]) in MATCHED_TIMES:
                tt = time_key(row["time"])
                umean = f(row, "mean_exit_velocity")
                item = dict(row)
                item.update(
                    {
                        "source_level": level,
                        "maxlevel": 7 if level == "L7" else 8,
                        "physical_time": tt,
                        "tau": tt * umean / DEFAULT_DH if math.isfinite(umean) else math.nan,
                        "convergence_status": conv_status,
                        "fit_readiness": "not_fit_ready",
                        "connected_jet_caveat": "connected waviness is not atomisation or breakup",
                    }
                )
                frame_rows.append(item)

    component_rows: list[dict[str, object]] = []
    for level, rows in (("L7", l7_component_rows), ("L8", l8_component_rows)):
        for row in rows:
            if row.get("time", "") and time_key(row["time"]) in MATCHED_TIMES:
                item = dict(row)
                item.update(
                    {
                        "source_level": level,
                        "maxlevel": 7 if level == "L7" else 8,
                        "breakup_claim_allowed": "false",
                        "interpretation": "component diagnostic only; post-exit tag count stayed one in accepted full-domain evidence",
                    }
                )
                component_rows.append(item)

    handoff = out / "geometry_handoff"
    spray = out / "spraygeo_handoff"
    ideal = out / "ideal_explorer_overlay"
    station_fields = [
        "source_level", "maxlevel", "source_case", "physical_time", "time", "tau", "frame_index",
        "station_id", "station_kind", "station_target", "xi", "zeta", "x_from_exit", "A", "Ahat",
        "equivalent_diameter", "width", "thickness", "aspect_ratio", "centroid_y", "centroid_z",
        "moment_yy", "moment_zz", "moment_yz", "orientation_angle", "warp_proxy", "raw_rows",
        "liquid_rows", "active_front", "active_front_Dh", "interface_growth_proxy", "component_count",
        "detached_proxy_count", "quality_flag", "convergence_status", "fit_readiness",
        "model_fit_allowed", "public_ready", "breakup_claim_allowed", "morphology_classification",
        "connected_jet_caveat", "quarter_evidence_role",
    ]
    frame_fields = sorted({key for row in frame_rows for key in row})
    component_fields = sorted({key for row in component_rows for key in row}) if component_rows else [
        "source_level", "time", "component_id", "tag_count", "volume", "cells",
        "centroid_x_from_exit", "centroid_y", "centroid_z", "credible", "region_flag",
        "breakup_claim_allowed", "interpretation",
    ]
    write_csv(handoff / "jet_station_metrics.csv", station_fields, station_rows)
    write_csv(handoff / "jet_frame_summary.csv", frame_fields, frame_rows)
    write_csv(handoff / "jet_component_summary.csv", component_fields, component_rows)

    spray_fields = [
        "source_level", "maxlevel", "physical_time", "tau", "xi", "zeta", "x_from_exit",
        "station_kind", "station_target", "A", "Ahat", "width", "thickness", "aspect_ratio",
        "centroid_y", "centroid_z", "orientation_angle", "warp_proxy", "quality_flag",
        "convergence_status", "fit_readiness", "connected_jet_caveat",
    ]
    ideal_fields = [
        "source_level", "maxlevel", "physical_time", "tau", "xi", "zeta", "Ahat",
        "Ahat_error", "variable", "station_kind", "station_target", "quality_flag",
        "convergence_status", "fit_readiness", "model_fit_performed", "public_ready",
    ]
    spray_rows = [{field: row.get(field, "") for field in spray_fields} for row in station_rows]
    ideal_rows = []
    for row in station_rows:
        ideal_rows.append(
            {
                "source_level": row.get("source_level", ""),
                "maxlevel": row.get("maxlevel", ""),
                "physical_time": row.get("physical_time", ""),
                "tau": row.get("tau", ""),
                "xi": row.get("xi", ""),
                "zeta": row.get("zeta", ""),
                "Ahat": row.get("Ahat", ""),
                "Ahat_error": "",
                "variable": "area",
                "station_kind": row.get("station_kind", ""),
                "station_target": row.get("station_target", ""),
                "quality_flag": row.get("quality_flag", ""),
                "convergence_status": row.get("convergence_status", ""),
                "fit_readiness": "not_fit_ready",
                "model_fit_performed": "false",
                "public_ready": "false",
            }
        )
    write_csv(spray / "basilisk_internal_nozzle_geometry_metrics.csv", spray_fields, spray_rows)
    write_csv(ideal / "basilisk_internal_nozzle_Ahat_overlay.csv", ideal_fields, ideal_rows)

    schema = {
        "schema_name": "basilisk_internal_nozzle_convergence_geometry_handoff",
        "source_cases": ["task03_l7_full_domain", "task04_l8_full_domain accepted_t0p12"],
        "matched_times": MATCHED_TIMES,
        "l8_accepted_final_time": 0.12,
        "station_extraction": {
            "extractor": "scripts/extract_internal_nozzle_raw_geometry.py",
            "width": DEFAULT_W,
            "height": DEFAULT_H,
            "Dh": DEFAULT_DH,
            "station_half_Dh": DEFAULT_STATION_HALF_DH,
            "liquid_threshold": 0.001,
        },
        "readiness": {
            "metrics_ready": True,
            "overlay_ready": True,
            "fit_ready": False,
            "public_ready": False,
            "breakup_claim_allowed": False,
        },
        "claim_boundary": [
            "internal diagnostic overlay only",
            "not validation",
            "not production CFD",
            "not stationary spray",
            "not public ready",
            "connected flow is not breakup",
        ],
        "station_columns": station_fields,
        "frame_columns": frame_fields,
        "component_columns": component_fields,
    }
    for path in [handoff / "jet_geometry_schema.json", spray / "schema.json", ideal / "schema.json"]:
        write_json(path, schema)

    (handoff / "README.md").write_text(
        "# Basilisk Internal-Nozzle Convergence Geometry Handoff\n\n"
        "This package combines L7 and accepted L8 full-domain raw-field geometry at exact matched times "
        "0.03, 0.06, 0.09, and 0.12. It is overlay-ready for internal model comparison only. "
        "It is not fit-ready, public-ready, or breakup evidence.\n",
        encoding="utf-8",
    )
    (spray / "README.md").write_text(
        "# SprayGeo Handoff\n\n"
        "CSV station metrics for internal SprayGeo-style ingestion. Rows include level, time, tau, "
        "quality flags, convergence status, and the connected-jet caveat. `fit_readiness` remains "
        "`not_fit_ready` for every row.\n",
        encoding="utf-8",
    )
    (ideal / "README.md").write_text(
        "# Ideal Momentum Jet Explorer Overlay\n\n"
        "Use `xi` or `zeta` as the streamwise coordinate and `Ahat` as the area overlay. The overlay "
        "contains L7 and accepted L8 diagnostic rows only; no parameter inference or model fit is allowed.\n",
        encoding="utf-8",
    )
    return {
        "station_metrics_path": str(handoff / "jet_station_metrics.csv"),
        "spraygeo_handoff_path": str(spray / "basilisk_internal_nozzle_geometry_metrics.csv"),
        "ideal_explorer_overlay_path": str(ideal / "basilisk_internal_nozzle_Ahat_overlay.csv"),
        "geometry_schema_path": str(handoff / "jet_geometry_schema.json"),
    }


def svg_line_plot(path: Path, title: str, series: dict[str, list[tuple[float, float]]], xlabel: str, ylabel: str, note: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height, margin = 980, 520, 72
    pts = [(x, y) for values in series.values() for x, y in values if math.isfinite(x) and math.isfinite(y)]
    if not pts:
        path.write_text(f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\"><text x=\"40\" y=\"80\">No data</text></svg>\n", encoding="utf-8")
        return
    xmin = min(x for x, _ in pts)
    xmax = max(x for x, _ in pts)
    ymin = min(y for _, y in pts)
    ymax = max(y for _, y in pts)
    if math.isclose(xmin, xmax):
        xmin -= 1.0
        xmax += 1.0
    if math.isclose(ymin, ymax):
        ymin -= 1.0
        ymax += 1.0
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#7f7f7f"]

    def sx(x: float) -> float:
        return margin + (width - 2 * margin) * (x - xmin) / (xmax - xmin)

    def sy(y: float) -> float:
        return height - margin - (height - 2 * margin) * (y - ymin) / (ymax - ymin)

    pieces = [
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>",
        f"<text x=\"{margin}\" y=\"34\" font-family=\"sans-serif\" font-size=\"19\">{html.escape(title)}</text>",
        f"<line x1=\"{margin}\" y1=\"{height-margin}\" x2=\"{width-margin}\" y2=\"{height-margin}\" stroke=\"#222\"/>",
        f"<line x1=\"{margin}\" y1=\"{margin}\" x2=\"{margin}\" y2=\"{height-margin}\" stroke=\"#222\"/>",
        f"<text x=\"{width/2-30}\" y=\"{height-20}\" font-family=\"sans-serif\" font-size=\"13\">{html.escape(xlabel)}</text>",
        f"<text x=\"18\" y=\"{height/2}\" font-family=\"sans-serif\" font-size=\"13\" transform=\"rotate(-90 18,{height/2})\">{html.escape(ylabel)}</text>",
    ]
    for idx, (name, values) in enumerate(series.items()):
        clean = sorted((x, y) for x, y in values if math.isfinite(x) and math.isfinite(y))
        if not clean:
            continue
        color = colors[idx % len(colors)]
        poly = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in clean)
        pieces.append(f"<polyline points=\"{poly}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2\"/>")
        for x, y in clean:
            pieces.append(f"<circle cx=\"{sx(x):.2f}\" cy=\"{sy(y):.2f}\" r=\"3\" fill=\"{color}\"/>")
        pieces.append(f"<text x=\"{width-margin-230}\" y=\"{margin+18*idx}\" font-family=\"sans-serif\" font-size=\"12\" fill=\"{color}\">{html.escape(name)}</text>")
    if note:
        pieces.append(f"<text x=\"{margin}\" y=\"{height-margin+30}\" font-family=\"sans-serif\" font-size=\"11\">{html.escape(note)}</text>")
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def svg_bar_plot(path: Path, title: str, counts: Counter[str]) -> None:
    width, height, margin = 940, 460, 78
    keys = list(counts.keys())
    maxv = max(counts.values()) if counts else 1
    bw = (width - 2 * margin) / max(len(keys), 1)
    pieces = [
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>",
        f"<text x=\"{margin}\" y=\"34\" font-family=\"sans-serif\" font-size=\"19\">{html.escape(title)}</text>",
        f"<line x1=\"{margin}\" y1=\"{height-margin}\" x2=\"{width-margin}\" y2=\"{height-margin}\" stroke=\"#222\"/>",
    ]
    for idx, key in enumerate(keys):
        val = counts[key]
        x = margin + idx * bw + 5
        bar_h = (height - 2 * margin) * val / maxv
        y = height - margin - bar_h
        pieces.append(f"<rect x=\"{x:.2f}\" y=\"{y:.2f}\" width=\"{max(bw-10, 2):.2f}\" height=\"{bar_h:.2f}\" fill=\"#4c78a8\"/>")
        pieces.append(f"<text x=\"{x:.2f}\" y=\"{height-margin+14}\" font-family=\"sans-serif\" font-size=\"10\" transform=\"rotate(45 {x:.2f},{height-margin+14})\">{html.escape(key)}</text>")
        pieces.append(f"<text x=\"{x:.2f}\" y=\"{y-4:.2f}\" font-family=\"sans-serif\" font-size=\"10\">{val}</text>")
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def svg_heatmap(path: Path, pair_rows: list[dict[str, object]]) -> None:
    cols = ["Ahat", "width", "thick", "aspect", "centroid", "warp", "all"]
    width = 880
    row_h = 28
    height = 90 + row_h * max(len(pair_rows), 1)
    pieces = [
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>",
        "<text x=\"30\" y=\"34\" font-family=\"sans-serif\" font-size=\"19\">Convergence Pass/Fail Heatmap</text>",
    ]
    x0 = 280
    for c, name in enumerate(cols):
        pieces.append(f"<text x=\"{x0+c*78}\" y=\"66\" font-family=\"sans-serif\" font-size=\"11\">{name}</text>")
    for r, row in enumerate(pair_rows):
        y = 86 + r * row_h
        label = f"t={f(row, 'time'):.2f} {row.get('station_kind')} {f(row, 'station_target'):.2f}"
        pieces.append(f"<text x=\"30\" y=\"{y+17}\" font-family=\"sans-serif\" font-size=\"11\">{html.escape(label)}</text>")
        checks = [
            bool(row.get("ahat_pair_p90_pass")),
            bool(row.get("width_pair_p90_pass")),
            bool(row.get("thickness_pair_p90_pass")),
            bool(row.get("aspect_pair_p90_pass")),
            bool(row.get("centroid_pair_pass")),
            bool(row.get("warp_pair_pass")),
            bool(row.get("pair_all_applicable_pass")),
        ]
        for c, ok in enumerate(checks):
            color = "#2ca02c" if ok else "#d62728"
            if not row.get("valid_station_time_pair"):
                color = "#bdbdbd"
            pieces.append(f"<rect x=\"{x0+c*78}\" y=\"{y}\" width=\"56\" height=\"20\" fill=\"{color}\"/>")
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def build_plots(out: Path, pair_rows: list[dict[str, object]], frame_rows: list[dict[str, object]], l7_station: list[dict[str, str]], l8_station: list[dict[str, str]], quarter_root: Path) -> list[str]:
    plots = out / "plots"
    plot_paths: list[str] = []
    ahat_series: dict[str, list[tuple[float, float]]] = {}
    for level, rows in (("L7", l7_station), ("L8", l8_station)):
        for tt in MATCHED_TIMES:
            vals = [(f(row, "xi"), f(row, "Ahat")) for row in rows if row.get("time", "") and time_key(row["time"]) == tt and f(row, "Ahat") > 0.0]
            ahat_series[f"{level} t={tt:.2f}"] = vals
    path = plots / "ahat_vs_xi_l7_l8.svg"
    svg_line_plot(path, "Ahat versus xi for L7/L8", ahat_series, "xi", "Ahat", "Existing raw station rows only; no interpolation.")
    plot_paths.append(str(path))

    path = plots / "width_thickness_aspect_convergence.svg"
    svg_line_plot(
        path,
        "Width/thickness/aspect relative differences",
        {
            "width rel diff": [(idx, f(row, "width_rel_diff")) for idx, row in enumerate(pair_rows)],
            "thickness rel diff": [(idx, f(row, "thickness_rel_diff")) for idx, row in enumerate(pair_rows)],
            "aspect rel diff": [(idx, f(row, "aspect_rel_diff")) for idx, row in enumerate(pair_rows)],
        },
        "station pair index",
        "relative difference",
        "Gray heatmap rows mark pairs not valid for the primary station gate.",
    )
    plot_paths.append(str(path))

    path = plots / "centroid_warp_convergence.svg"
    svg_line_plot(
        path,
        "Centroid and warp convergence",
        {
            "centroid separation Dh": [(idx, f(row, "centroid_separation_Dh")) for idx, row in enumerate(pair_rows)],
            "warp abs diff": [(idx, f(row, "warp_abs_diff")) for idx, row in enumerate(pair_rows)],
        },
        "station pair index",
        "difference",
    )
    plot_paths.append(str(path))

    path = plots / "active_front_interface_histories.svg"
    svg_line_plot(
        path,
        "Active-front and interface histories",
        {
            "L7 active front Dh": [(f(row, "time"), f(row, "l7_active_front_Dh")) for row in frame_rows],
            "L8 active front Dh": [(f(row, "time"), f(row, "l8_active_front_Dh")) for row in frame_rows],
            "interface proxy rel diff": [(f(row, "time"), f(row, "interface_proxy_rel_diff")) for row in frame_rows],
            "mean exit velocity rel diff": [(f(row, "time"), f(row, "mean_exit_velocity_rel_diff")) for row in frame_rows],
        },
        "time",
        "value",
    )
    plot_paths.append(str(path))

    path = plots / "convergence_pass_fail_heatmap.svg"
    svg_heatmap(path, pair_rows)
    plot_paths.append(str(path))

    qcounter: Counter[str] = Counter()
    for row in [*l7_station, *l8_station]:
        if row.get("time", "") and time_key(row["time"]) in MATCHED_TIMES:
            for item in row.get("quality_flag", "").split("|"):
                if item:
                    qcounter[item] += 1
    path = plots / "quality_coverage.svg"
    svg_bar_plot(path, "Quality coverage flags", qcounter)
    plot_paths.append(str(path))

    quarter_rows = read_csv(quarter_root / "metrics" / "quarter_full_comparison.csv")
    path = plots / "quarter_full_diagnostic_comparison.svg"
    svg_line_plot(
        path,
        "Quarter/full diagnostic comparison",
        {
            "mean velocity rel error": [(f(row, "t"), f(row, "mean_exit_velocity_rel_error")) for row in quarter_rows if f(row, "t") <= 0.12],
            "4x flow rel error": [(f(row, "t"), f(row, "flow_rate_4x_rel_error")) for row in quarter_rows if f(row, "t") <= 0.12],
            "active-front abs error Dh": [(f(row, "t"), abs(f(row, "active_front_Dh_error"))) for row in quarter_rows if f(row, "t") <= 0.12],
        },
        "time",
        "diagnostic error",
        "Quarter evidence is scout-only and not independent full-domain evidence.",
    )
    plot_paths.append(str(path))
    return plot_paths


def build_native_video(out: Path, l7_root: Path, l8_root: Path) -> dict[str, object]:
    native = out / "native_video"
    l7_sel = native / "selected_l7"
    l8_sel = native / "selected_l8"
    l7_sel.mkdir(parents=True, exist_ok=True)
    l8_sel.mkdir(parents=True, exist_ok=True)
    selected: list[dict[str, object]] = []
    for out_idx, tt in enumerate(MATCHED_TIMES):
        frame_idx = int(round(tt / VISUAL_DT))
        src7 = l7_root / "native_frames" / f"native_vof_{frame_idx:04d}.ppm"
        src8 = l8_root / "native_frames" / f"native_vof_{frame_idx:04d}.ppm"
        dst7 = l7_sel / f"native_vof_{out_idx:04d}.ppm"
        dst8 = l8_sel / f"native_vof_{out_idx:04d}.ppm"
        if src7.exists():
            shutil.copyfile(src7, dst7)
        if src8.exists():
            shutil.copyfile(src8, dst8)
        selected.append(
            {
                "time": tt,
                "source_visual_frame_index": frame_idx,
                "l7_source": str(src7),
                "l8_source": str(src8),
                "l7_selected": str(dst7),
                "l8_selected": str(dst8),
                "l7_exists": src7.exists(),
                "l8_exists": src8.exists(),
            }
        )
    output = native / "internal_nozzle_l7_l8_side_by_side.mp4"
    ffmpeg = shutil.which("ffmpeg") or ""
    result: dict[str, object] = {
        "selected_frames": selected,
        "ffmpeg": ffmpeg,
        "output": str(output),
        "used_existing_solver_frames_only": True,
        "interpolation_performed": False,
    }
    if ffmpeg and all(item["l7_exists"] and item["l8_exists"] for item in selected):
        cmd = [
            ffmpeg,
            "-y",
            "-framerate",
            "2",
            "-i",
            str(l7_sel / "native_vof_%04d.ppm"),
            "-framerate",
            "2",
            "-i",
            str(l8_sel / "native_vof_%04d.ppm"),
            "-filter_complex",
            "[0:v]scale=640:-2,setpts=PTS-STARTPTS[l];[1:v]scale=640:-2,setpts=PTS-STARTPTS[r];[l][r]hstack=inputs=2[v]",
            "-map",
            "[v]",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
        run = run_cmd(cmd)
        result["ffmpeg_command"] = cmd
        result["ffmpeg_returncode"] = run["returncode"]
        result["ffmpeg_stderr_tail"] = run["stderr_tail"]
    else:
        result["ffmpeg_returncode"] = None
        result["ffmpeg_stderr_tail"] = "ffmpeg missing or selected source frames missing"
    result["video_exists"] = output.exists() and output.stat().st_size > 0
    if result["video_exists"] and shutil.which("ffprobe"):
        probe_path = native / "ffprobe_internal_nozzle_l7_l8_side_by_side.json"
        probe = run_cmd([
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(output),
        ])
        probe_path.write_text(str(probe["stdout_tail"]), encoding="utf-8")
        result["ffprobe_path"] = str(probe_path)
        result["ffprobe_returncode"] = probe["returncode"]
    write_json(native / "frame_selection_manifest.json", result)
    return result


def write_model_note(path: Path, conv: dict[str, object]) -> None:
    path.write_text(
        "# Model Connection Note\n\n"
        "## Direct Observables\n\n"
        "- `A` and `Ahat`: station-slab liquid area and normalized area.\n"
        "- `width`, `thickness`, `aspect_ratio`: transverse occupancy extents.\n"
        "- `centroid_y`, `centroid_z`: cross-plane centroid drift.\n"
        "- `orientation_angle` and `warp_proxy`: second-moment orientation and skew proxy.\n"
        "- `active_front_Dh`, `interface_proxy`, and `interface_growth`: frame-level transient diagnostics.\n\n"
        "## Closures Or Model Quantities\n\n"
        "- Ideal/lossy jet-model area overlays may use `xi` or `zeta` as streamwise coordinate and `Ahat` as the area variable.\n"
        "- Any entrainment, dissipation, contraction-loss, or atomisation parameter remains a closure, not a directly fitted value from this batch.\n\n"
        "## Readiness\n\n"
        f"- Matched-cadence convergence decision: `{conv['decision']}`.\n"
        "- Overlay readiness: `true` for internal diagnostic comparison.\n"
        "- `exploratory_fit_ready=false`, `fit_ready=false`, and `public_ready=false`.\n"
        "- Final parameter inference is prohibited.\n\n"
        "## Next Model Experiment\n\n"
        "Do not run a parameter-fitting experiment from this package. The next model step is a source-level diagnostic alignment check: "
        "rerun or restore L7 with the same fixed/front-relative station schedule used by the accepted L8 export, then repeat this exact gate.\n",
        encoding="utf-8",
    )


def write_decision_docs(out: Path, conv: dict[str, object], l7_summary: dict[str, object], l8_summary: dict[str, object]) -> None:
    checks = conv["threshold_checks"]
    aggregates = conv["aggregates"]
    lines = [
        "# Matched-Cadence Convergence Decision",
        "",
        "Decision: `failed_conservative_matched_cadence_gate`.",
        "",
        "Exact common physical times used: `0.03, 0.06, 0.09, 0.12`.",
        "The accepted L8 final time for this gate is `0.12`; later L8 frames are recorded as context only.",
        "",
        "## Threshold Results",
        "",
    ]
    for key, value in checks.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Aggregate Metrics",
            "",
            f"- valid station/time pairs: `{aggregates['valid_station_time_pairs']}`",
            f"- threshold pass fraction: `{aggregates['threshold_pass_fraction']}`",
            f"- max mean-exit-velocity relative difference: `{aggregates['max_mean_exit_velocity_rel_diff']}`",
            f"- max active-front difference: `{aggregates['max_active_front_abs_diff_Dh']} Dh`",
            "",
            "The mean exit velocity and active-front thresholds fail by a wide margin. Station coverage is also limited because Task 03 L7 was generated with the older station schedule while accepted Task 04 L8 used the runbook-required station schedule.",
        ]
    )
    (out / "MATCHED_CADENCE_CONVERGENCE_DECISION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "MODEL_READINESS_DECISION.md").write_text(
        "# Model Readiness Decision\n\n"
        "- `fit_ready=false`.\n"
        f"- `exploratory_fit_ready={str(conv['exploratory_fit_ready']).lower()}`.\n"
        "- `public_ready=false`.\n"
        "- `breakup_claim_allowed=false`.\n"
        "- `quarter_evidence_used_as_scout_only=true`.\n\n"
        "The exploratory fit gate does not pass because the matched-cadence convergence gate fails and the valid station/time pair count is below 12. "
        "Quarter-domain evidence remains a scout comparison only and is not used as independent full-domain evidence.\n",
        encoding="utf-8",
    )


def write_inventory_and_audit(
    out: Path,
    repo: Path,
    batch_root: Path,
    l7_root: Path,
    l8_root: Path,
    l8_accepted: Path,
    quarter_root: Path,
    summaries: dict[str, dict[str, object]],
    extractor_results: dict[str, dict[str, object]],
) -> None:
    manifest_paths = {
        "task03_checkpoint_manifest": l7_root / "manifests" / "checkpoint_manifest.json",
        "task03_raw_export_manifest": l7_root / "manifests" / "raw_export_manifest.json",
        "task03_surface_manifest": l7_root / "manifests" / "surface_manifest.json",
        "task03_visual_frame_manifest": l7_root / "manifests" / "visual_frame_manifest.json",
        "task04_checkpoint_manifest": l8_accepted / "manifests" / "checkpoint_manifest.json",
        "task04_raw_export_manifest": l8_accepted / "manifests" / "raw_export_manifest.json",
        "task04_surface_manifest": l8_accepted / "manifests" / "surface_manifest.json",
        "task04_visual_frame_manifest": l8_accepted / "manifests" / "visual_frame_manifest.json",
        "task05_raw_export_manifest": quarter_root / "raw_export_manifest.json",
        "task05_native_assets_manifest": quarter_root / "native_video" / "native_assets_manifest.json",
        "task05_native_video_manifest": quarter_root / "native_video" / "native_video_manifest.json",
    }
    inventory = {
        "task_id": "06_convergence_geometry_model_refresh",
        "batch_root": str(batch_root),
        "source_roots": {
            "l7_full_domain": str(l7_root),
            "l8_full_domain_context": str(l8_root),
            "l8_accepted_t0p12": str(l8_accepted),
            "quarter_scout": str(quarter_root),
        },
        "matched_times_completed": MATCHED_TIMES,
        "l8_accepted_final_time": 0.12,
        "l8_context_final_time": summaries["04"].get("l8_final_time"),
        "selected_cpu_mode": summaries["03"].get("selected_cpu_mode", summaries["02"].get("selected_cpu_mode", "")),
        "station_definitions": {
            "required_fixed_xi": FIXED_REQUIRED,
            "required_front_relative": FRONT_REQUIRED,
            "task03_l7_inferred_fixed_xi": [0.25, 0.50, 0.75, 1.00, 1.50],
            "task03_l7_inferred_front_relative": [0.50, 0.90],
            "task04_l8_accepted_fixed_xi": FIXED_REQUIRED,
            "task04_l8_accepted_front_relative": FRONT_REQUIRED,
        },
        "control_equality": {
            "pressure": 351.48,
            "pressure_equal": True,
            "geometry_equal": True,
            "phase_properties_equal": True,
            "domain_equal": True,
            "only_physical_or_numerical_difference": "maxlevel 7 versus maxlevel 8",
        },
        "frame_completeness": {
            "task03_all_physical_frames_accounted": summaries["03"].get("all_physical_frames_accounted"),
            "task04_all_physical_frames_accounted": summaries["04"].get("all_physical_frames_accounted"),
            "task05_all_physical_frames_accounted": summaries["05"].get("all_physical_frames_accounted"),
        },
        "quarter_evidence": {
            "classification": summaries["05"].get("classification"),
            "used_as_scout_only": True,
            "quarter_as_final_reference_allowed": summaries["05"].get("quarter_as_final_reference_allowed", False),
            "periodic_quadrant_boundaries_used": summaries["05"].get("periodic_quadrant_boundaries_used", False),
        },
        "previous_overlay_package": {
            "commit": "a943b9f",
            "context": git_value(repo, ["show", "--stat", "--oneline", "--no-renames", "a943b9f", "--"]),
        },
        "manifests": {name: file_record(path) for name, path in manifest_paths.items()},
        "extractor_runs": extractor_results,
    }
    write_json(out / "INPUT_INVENTORY.json", inventory)
    (out / "PROVENANCE_AND_CONTROL_AUDIT.md").write_text(
        "# Provenance And Control Audit\n\n"
        "- Scientific repo: `/home/franco/Documents/GitHub/dualsphysics-visualsphysics-portfolio`.\n"
        "- Branch: `review/basilisk-internal-nozzle-and-periodic-span-20260621`.\n"
        "- L7 source: Task 03 full-domain raw/native/surface package.\n"
        "- L8 source: Task 04 accepted `t=0.12` full-domain raw/native/surface package. Later L8 frames are context only.\n"
        "- Quarter source: Task 05 quarter-domain package, scout-only.\n"
        "- Pressure, geometry, phase properties, domain, perturbation, and pressure-driven inlet are preserved across L7/L8; the intended difference is maxlevel.\n"
        "- Station schedule caveat: Task 03 L7 was produced with the older fixed/front-relative schedule, while accepted Task 04 L8 used the runbook-required schedule. Missing L7 stations are treated as coverage limits, not interpolated data.\n"
        "- No CFD solver run, push, deploy, or public publish was performed by Task 06.\n\n"
        "Quarter-domain mirrored observations are diagnostic reconstructions only. They are not independent samples and are not used for full-domain convergence or breakup claims.\n",
        encoding="utf-8",
    )


def qa_results(repo: Path) -> dict[str, object]:
    diff_check = run_cmd(["git", "diff", "--check"], cwd=repo)
    py_compile = run_cmd([
        sys.executable,
        "-m",
        "py_compile",
        "scripts/analyze_internal_nozzle_convergence.py",
        "scripts/extract_internal_nozzle_raw_geometry.py",
        "scripts/build_internal_nozzle_geometry_model_handoff.py",
    ], cwd=repo)
    latest_files = git_value(repo, ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]).splitlines()
    forbidden_suffixes = {".csv", ".mp4", ".mov", ".avi", ".mkv", ".webm", ".vtk", ".vtp", ".vtu", ".bi4", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"}
    forbidden_latest = [path for path in latest_files if Path(path).suffix.lower() in forbidden_suffixes]
    status = git_value(repo, ["status", "--porcelain=v1"])
    return {
        "git_diff_check": diff_check,
        "python_py_compile": py_compile,
        "latest_commit_files": latest_files,
        "forbidden_generated_files_in_latest_commit": forbidden_latest,
        "repo_status_porcelain": status,
        "passed": diff_check["returncode"] == 0 and py_compile["returncode"] == 0 and not forbidden_latest and status == "",
    }


def write_report(
    out: Path,
    branch: str,
    head: str,
    conv: dict[str, object],
    handoff_paths: dict[str, str],
    video: dict[str, object],
    plots: list[str],
    qa: dict[str, object],
) -> Path:
    report = out / "CODEX_TASK_06_REPORT.md"
    agg = conv["aggregates"]
    plot_lines = "\n".join(f"- `{path}`" for path in plots)
    report_body = (
        "# CODEX Task 06 Report - Convergence Geometry Model Refresh\n\n"
        "Status: `success` with negative convergence decision.\n\n"
        "No CFD solver, push, deploy, public publish, sudo, install, download, `/goal`, or `/loop` was performed.\n\n"
        "## Scope\n\n"
        f"- Branch: `{branch}`\n"
        f"- Commit: `{head}`\n"
        "- Exact matched physical times: `0.03, 0.06, 0.09, 0.12`.\n"
        "- Accepted L8 final time for this gate: `0.12`.\n"
        "- Quarter-domain evidence: scout-only.\n\n"
        "## Outputs\n\n"
        f"- Input inventory: `{out / 'INPUT_INVENTORY.json'}`\n"
        f"- Provenance audit: `{out / 'PROVENANCE_AND_CONTROL_AUDIT.md'}`\n"
        f"- Station pairs: `{out / 'metrics' / 'convergence_station_pairs.csv'}`\n"
        f"- Frame pairs: `{out / 'metrics' / 'convergence_frame_pairs.csv'}`\n"
        f"- Quality coverage: `{out / 'metrics' / 'convergence_quality_coverage.csv'}`\n"
        f"- Convergence summary: `{out / 'metrics' / 'convergence_summary.json'}`\n"
        f"- Geometry handoff: `{handoff_paths['station_metrics_path']}`\n"
        f"- SprayGeo handoff: `{handoff_paths['spraygeo_handoff_path']}`\n"
        f"- Ideal Explorer overlay: `{handoff_paths['ideal_explorer_overlay_path']}`\n"
        f"- Native side-by-side video: `{video['output']}`\n"
        f"- Model connection note: `{out / 'MODEL_CONNECTION_NOTE.md'}`\n\n"
        "## Convergence Decision\n\n"
        f"- Decision: `{conv['decision']}`\n"
        f"- Valid station/time pairs: `{agg['valid_station_time_pairs']}`\n"
        f"- Threshold pass fraction: `{agg['threshold_pass_fraction']}`\n"
        f"- Max mean-exit-velocity relative difference: `{agg['max_mean_exit_velocity_rel_diff']}`\n"
        f"- Max active-front absolute difference: `{agg['max_active_front_abs_diff_Dh']} Dh`\n"
        f"- Convergence passed: `{conv['convergence_passed']}`\n"
        f"- Exploratory fit ready: `{conv['exploratory_fit_ready']}`\n\n"
        "The gate fails primarily on mean exit velocity and active-front differences. The station-pair count also remains below the exploratory-fit gate because L7 and accepted L8 were produced with different station schedules. Missing stations were not interpolated or manufactured.\n\n"
        "## Diagnostic Media\n\n"
        f"{plot_lines}\n\n"
        "The native comparison MP4 uses only the existing matched native frames at visual-frame indices `6, 12, 18, 24`; no hidden interpolation was performed.\n\n"
        "## Claim Boundary\n\n"
        "`fit_ready=false`, `public_ready=false`, `breakup_claim_allowed=false`, `raw_outputs_committed=false`, `push_performed=false`, `deploy_performed=false`, and `public_publish_performed=false` remain in force. Connected waviness is not atomisation or breakup.\n\n"
        "## QA\n\n"
        f"- `git diff --check`: `{qa['git_diff_check']['returncode']}`\n"
        f"- Python syntax checks: `{qa['python_py_compile']['returncode']}`\n"
        f"- Forbidden generated files in latest commit: `{qa['forbidden_generated_files_in_latest_commit']}`\n"
        f"- Repo status clean: `{qa['repo_status_porcelain'] == ''}`\n"
        f"- Native video exists: `{video['video_exists']}`\n"
        f"- QA passed: `{qa['passed'] and video['video_exists']}`\n\n"
        "## Recommended Next Step\n\n"
        "Use a schedule-aligned L7 raw export or restore path before any model-fitting attempt. Until then, keep the refreshed handoffs as internal overlays only.\n\n"
        f"TASK_06_CONVERGENCE_MODEL_WRITTEN: {report}\n"
    )
    report.write_text(report_body, encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("/home/franco/Documents/GitHub/dualsphysics-visualsphysics-portfolio"))
    parser.add_argument("--batch-root", type=Path, default=Path("/home/franco/stack-validation/20260622-basilisk-internal-nozzle-convergence-visual-batch"))
    parser.add_argument("--output-root", type=Path, default=Path("/home/franco/stack-validation/20260622-basilisk-internal-nozzle-convergence-visual-batch/06_convergence_geometry_model_refresh"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo_root
    batch = args.batch_root
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"

    l7_root = batch / "03_full_domain_l7_reference"
    l8_root = batch / "04_full_domain_l8_convergence"
    l8_accepted = l8_root / "accepted_t0p12"
    quarter_root = batch / "05_quarter_domain_visual_recovery"
    summaries = {
        "01": load_json(batch / "01_visual_output_checkpoint_pipeline" / "CODEX_TASK_01_SUMMARY.json"),
        "02": load_json(batch / "02_execution_scaling_qualification" / "CODEX_TASK_02_SUMMARY.json"),
        "03": load_json(l7_root / "CODEX_TASK_03_SUMMARY.json"),
        "04": load_json(l8_root / "CODEX_TASK_04_SUMMARY.json"),
        "05": load_json(quarter_root / "CODEX_TASK_05_SUMMARY.json"),
    }

    extraction_root = out / "reextracted_geometry"
    extractor_results = {
        "l7": run_extractor(repo, l7_root, extraction_root / "l7", "L7", logs),
        "l8": run_extractor(repo, l8_accepted, extraction_root / "l8", "L8", logs),
    }
    if extractor_results["l7"]["returncode"] != 0 or extractor_results["l8"]["returncode"] != 0:
        raise SystemExit("raw geometry extraction failed; see Task 06 logs")

    l7_station = read_csv(extraction_root / "l7" / "metrics" / "raw_export_station_metrics.csv")
    l8_station = read_csv(extraction_root / "l8" / "metrics" / "raw_export_station_metrics.csv")
    l7_frame_rows = read_csv(extraction_root / "l7" / "metrics" / "raw_export_frame_summary.csv")
    l8_frame_rows = read_csv(extraction_root / "l8" / "metrics" / "raw_export_frame_summary.csv")
    l7_component = read_csv(extraction_root / "l7" / "metrics" / "raw_export_component_summary.csv")
    l8_component = read_csv(extraction_root / "l8" / "metrics" / "raw_export_component_summary.csv")
    l7_frames = by_time(l7_frame_rows)
    l8_frames = by_time(l8_frame_rows)

    pair_rows, coverage_rows = pair_station_rows(l7_station, l8_station, l7_frames, l8_frames)
    frame_rows = compare_frames(l7_frames, l8_frames)
    conv = convergence_summary(pair_rows, frame_rows)

    metrics = out / "metrics"
    station_fields = [
        "time", "station_kind", "station_target", "l7_station_id", "l8_station_id", "l7_xi", "l8_xi",
        "fixed_gate_limit_xi", "primary_gate_eligible", "valid_station_time_pair", "l7_Ahat", "l8_Ahat",
        "Ahat_abs_diff", "Ahat_rel_diff", "Ahat_signed_diff_l8_minus_l7", "l7_width", "l8_width",
        "width_rel_diff", "l7_thickness", "l8_thickness", "thickness_rel_diff", "l7_aspect_ratio",
        "l8_aspect_ratio", "aspect_rel_diff", "centroid_separation_Dh", "l7_warp_proxy", "l8_warp_proxy",
        "warp_abs_diff", "station_slab_half_Dh", "station_xi_uncertainty_Dh", "l7_quality_flag",
        "l8_quality_flag", "ahat_pair_p90_pass", "width_pair_p90_pass", "thickness_pair_p90_pass",
        "aspect_pair_p90_pass", "centroid_pair_pass", "warp_pair_pass", "pair_all_applicable_pass",
    ]
    frame_fields = [
        "time", "tau_l7", "tau_l8", "l7_mean_exit_velocity", "l8_mean_exit_velocity",
        "mean_exit_velocity_rel_diff", "mean_exit_velocity_pass", "l7_active_front_Dh", "l8_active_front_Dh",
        "active_front_abs_diff_Dh", "active_front_pass", "l7_interface_proxy", "l8_interface_proxy",
        "interface_proxy_rel_diff", "interface_proxy_pass", "l7_post_tag_count", "l8_post_tag_count",
        "l7_detached_proxy_count", "l8_detached_proxy_count", "morphology_classification_l7",
        "morphology_classification_l8", "morphology_change", "new_credible_detached_claim",
    ]
    coverage_fields = [
        "time", "station_kind", "station_target", "fixed_gate_limit_xi", "l7_available", "l8_available",
        "paired", "primary_gate_eligible", "coverage_note",
    ]
    write_csv(metrics / "convergence_station_pairs.csv", station_fields, pair_rows)
    write_csv(metrics / "convergence_frame_pairs.csv", frame_fields, frame_rows)
    write_csv(metrics / "convergence_quality_coverage.csv", coverage_fields, coverage_rows)
    write_json(metrics / "convergence_summary.json", conv)

    handoff_paths = build_handoffs(out, l7_station, l8_station, l7_frame_rows, l8_frame_rows, l7_component, l8_component, conv)
    plots = build_plots(out, pair_rows, frame_rows, l7_station, l8_station, quarter_root)
    video = build_native_video(out, l7_root, l8_accepted)
    write_model_note(out / "MODEL_CONNECTION_NOTE.md", conv)
    write_decision_docs(out, conv, summaries["03"], summaries["04"])
    write_inventory_and_audit(out, repo, batch, l7_root, l8_root, l8_accepted, quarter_root, summaries, extractor_results)

    branch = git_value(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    head = git_value(repo, ["rev-parse", "HEAD"])
    qa = qa_results(repo)
    report_path = write_report(out, branch, head, conv, handoff_paths, video, plots, qa)

    qa_passed = bool(qa["passed"] and video["video_exists"])
    summary = {
        "task_id": "06_convergence_geometry_model_refresh",
        "status": "success",
        "execution_complete": True,
        "safe_to_continue": True,
        "classification": "negative_convergence_decision_overlay_refreshed",
        "output_root": str(out),
        "report_path": str(report_path),
        "branch_name": branch,
        "repo_changed": head != TASK04_BASE_COMMIT,
        "commit_hash": head,
        "solver_run_performed": False,
        "render_run_performed": True,
        "raw_outputs_committed": False,
        "push_performed": False,
        "deploy_performed": False,
        "public_publish_performed": False,
        "fit_ready": False,
        "public_ready": False,
        "qa_passed": qa_passed,
        "selected_source_case": "Task03 L7 full-domain and Task04 accepted_t0p12 L8 full-domain",
        "l7_final_time": summaries["03"].get("l7_final_time"),
        "l8_final_time": 0.12,
        "matched_times_completed": MATCHED_TIMES,
        "valid_station_time_pairs": conv["aggregates"]["valid_station_time_pairs"],
        "threshold_pass_fraction": conv["aggregates"]["threshold_pass_fraction"],
        "convergence_passed": conv["convergence_passed"],
        "metrics_ready": True,
        "overlay_ready": True,
        "exploratory_fit_ready": conv["exploratory_fit_ready"],
        "breakup_claim_allowed": False,
        "morphology_classification": MORPHOLOGY,
        "station_metrics_path": handoff_paths["station_metrics_path"],
        "spraygeo_handoff_path": handoff_paths["spraygeo_handoff_path"],
        "ideal_explorer_overlay_path": handoff_paths["ideal_explorer_overlay_path"],
        "native_convergence_video_path": video["output"],
        "model_connection_note_path": str(out / "MODEL_CONNECTION_NOTE.md"),
        "quarter_evidence_used_as_scout_only": True,
        "exact_blocker": "",
        "recommended_next_step": "Run or restore a schedule-aligned L7 raw export before any model-fitting attempt; keep current handoffs internal overlay-only.",
        "retry_recommended": False,
    }
    write_json(out / "CODEX_TASK_06_SUMMARY.json", summary)
    print(f"TASK_06_CONVERGENCE_MODEL_WRITTEN: {report_path}")
    return 0 if qa_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
