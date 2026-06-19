#!/usr/bin/env python3
"""Conservative morphology classification helpers for Basilisk VOF routes.

The classifier intentionally separates reduced-model scout evidence from 3D
breakup-proxy evidence. Connected waviness is not atomization.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


POSITIVE_2D_LABELS = {
    "2d_instability_scout_candidate_rollup_detached_proxy",
    "reduced_model_breakup_proxy_candidate",
}

POSITIVE_3D_LABELS = {
    "3d_breakup_proxy_candidate",
    "3d_ligament_or_detached_proxy_candidate",
    "periodic_span_3d_bridge_candidate",
}

NEGATIVE_LABELS = {
    "connected_waviness_not_atomization",
    "negative_transfer_result",
    "periodic_span_negative_transfer_result",
    "runtime_limited_no_post_exit_morphology_window",
    "insufficient_post_exit_window",
    "numerically_unstable_not_interpretable",
    "compile_blocked",
    "diagnostics_blocked",
}

INTERNAL_PRELIMINARY_LABEL = "internal_preliminary_interface_evidence"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return default


def infer_dimensionality(row: Mapping[str, Any]) -> str:
    """Infer dimensionality from normalized fields and route/source names."""
    parts = " ".join(
        _as_text(row.get(key)).lower()
        for key in ("route_id", "model_type", "source_case", "case_id", "output_root")
    )
    if "2d" in parts or "planar" in parts:
        return "2D"
    if "axisym" in parts:
        return "axisymmetric"
    if "3d" in parts or "rectangular_slot" in parts or "periodic_span" in parts or "atomisation" in parts:
        return "3D"
    return "unknown"


def classify_case(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return conservative classification metadata for one normalized case row."""
    dimensionality = _as_text(row.get("dimensionality")) or infer_dimensionality(row)
    dim = dimensionality.upper()
    route_id = _as_text(row.get("route_id")).lower()
    status_text = " ".join(
        _as_text(row.get(key)).lower()
        for key in ("status", "run_status", "exact_blocker", "classification")
    )
    source_label = _as_text(row.get("classification") or row.get("morphology_classification"))

    post_component_candidates = [
        _as_int(row.get("post_exit_tag_component_count")),
        _as_int(row.get("max_post_tag_component_count")),
    ]
    if any(post_component_candidates):
        raw_post_components = max(post_component_candidates)
    else:
        raw_post_components = max(
            _as_int(row.get("max_tag_component_count")),
            _as_int(row.get("tag_component_count")),
        )
    raw_detached = max(
        _as_int(row.get("detached_proxy_count")),
        _as_int(row.get("max_detached_proxy_count")),
        _as_int(row.get("max_post_detached_proxy_count")),
    )

    explicit_credible_components = row.get("credible_post_exit_tag_component_count")
    explicit_credible_detached = row.get("credible_detached_proxy_count")
    frames_with_components = max(
        _as_int(row.get("frames_with_credible_post_components_gt1")),
        _as_int(row.get("frames_with_post_components_gt1")),
        _as_int(row.get("frames_with_credible_components_gt1")),
    )

    if explicit_credible_components not in (None, ""):
        credible_components = _as_int(explicit_credible_components)
    elif dim == "2D":
        credible_components = raw_post_components
    else:
        credible_components = raw_post_components if frames_with_components > 0 else min(raw_post_components, 1)

    if explicit_credible_detached not in (None, ""):
        credible_detached = _as_int(explicit_credible_detached)
    elif dim == "2D":
        credible_detached = raw_detached
    else:
        credible_detached = raw_detached if frames_with_components > 0 else 0

    interface_growth = max(
        _as_float(row.get("interface_length_or_area_growth")),
        _as_float(row.get("max_interface_length_growth")),
        _as_float(row.get("max_interface_area_growth")),
    )
    scout_flag = _as_bool(row.get("scout_candidate_found")) or _as_bool(row.get("adaptive_candidate_found"))
    micro_flag = _as_bool(row.get("micro_translation_candidate_found"))
    bridge_flag = _as_bool(row.get("bridge_candidate_found"))
    followup_flag = _as_bool(row.get("followup_candidate_found"))
    breakup_flag = _as_bool(row.get("breakup_proxy_candidate"))

    notes: list[str] = []
    classification = source_label or "connected_waviness_not_atomization"
    reduced_candidate = False
    three_d_candidate = False

    if "compile" in status_text and ("blocked" in status_text or "fail" in status_text):
        classification = "compile_blocked"
    elif "numerically_unstable" in status_text or "not_interpretable" in status_text:
        classification = "numerically_unstable_not_interpretable"
    elif "runtime_limited_no_post_exit" in status_text:
        classification = "runtime_limited_no_post_exit_morphology_window"
    elif "insufficient_post_exit" in status_text:
        classification = "insufficient_post_exit_window"
    elif "official_atomisation_wrapper" in route_id or "atomisation_route" in route_id:
        classification = INTERNAL_PRELIMINARY_LABEL
        notes.append("internal preliminary route; public_ready remains false")
    elif dim == "2D":
        if (
            source_label in POSITIVE_2D_LABELS
            or scout_flag
            or credible_detached > 0
            or (credible_components > 1 and interface_growth >= 2.0)
        ):
            classification = "2d_instability_scout_candidate_rollup_detached_proxy"
            reduced_candidate = True
        else:
            classification = source_label if source_label in NEGATIVE_LABELS else "connected_waviness_not_atomization"
    elif dim == "3D":
        if source_label in POSITIVE_3D_LABELS and credible_components > 1 and credible_detached > 0:
            classification = source_label
            three_d_candidate = True
        elif (breakup_flag or bridge_flag or followup_flag) and credible_components > 1 and credible_detached > 0:
            classification = "3d_breakup_proxy_candidate"
            three_d_candidate = True
        elif credible_components > 1 and credible_detached > 0 and frames_with_components > 0:
            classification = "3d_ligament_or_detached_proxy_candidate"
            three_d_candidate = True
        elif micro_flag:
            classification = "3d_breakup_proxy_candidate"
            three_d_candidate = True
        elif raw_post_components > credible_components or raw_detached > credible_detached:
            classification = "connected_waviness_not_atomization"
            notes.append("raw component/debris count rejected by credible 3D gate")
        elif source_label in NEGATIVE_LABELS:
            classification = source_label
        else:
            classification = "connected_waviness_not_atomization"
    else:
        if source_label in POSITIVE_2D_LABELS:
            classification = source_label
            reduced_candidate = True
        elif source_label in POSITIVE_3D_LABELS:
            classification = source_label
            three_d_candidate = True
        elif source_label in NEGATIVE_LABELS:
            classification = source_label
        else:
            classification = "diagnostics_blocked"

    if classification in POSITIVE_2D_LABELS:
        reduced_candidate = True
        three_d_candidate = False
    if classification in POSITIVE_3D_LABELS:
        three_d_candidate = True
        reduced_candidate = False

    if reduced_candidate:
        notes.append("positive reduced-model scout evidence only; not 3D validation")
    if classification == "connected_waviness_not_atomization":
        notes.append("connected waviness is negative for atomization/breakup claims")

    return {
        "classification": classification,
        "dimensionality": dimensionality,
        "credible_post_exit_tag_component_count": credible_components,
        "credible_detached_proxy_count": credible_detached,
        "raw_post_exit_tag_component_count": raw_post_components,
        "raw_detached_proxy_count": raw_detached,
        "interface_length_or_area_growth": interface_growth,
        "breakup_proxy_candidate": three_d_candidate,
        "scout_candidate_found": reduced_candidate,
        "classification_notes": "; ".join(notes),
    }


def _load_mapping(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify one Basilisk case summary conservatively. "
            "Use collect_diagnostics.py for route-level consolidation."
        )
    )
    parser.add_argument("json_path", nargs="?", help="JSON object with case or summary fields")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args(argv)

    if not args.json_path:
        parser.print_help()
        return 0

    try:
        row = _load_mapping(Path(args.json_path))
        result = classify_case(row)
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
