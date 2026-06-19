#!/usr/bin/env python3
"""Collect Basilisk route diagnostics into conservative comparison tables."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from basilisk_classify_morphology import classify_case, infer_dimensionality


DEFAULT_ROOTS = [
    "/home/franco/stack-validation/20260618-basilisk-atomisation-route",
    "/home/franco/stack-validation/20260618-basilisk-official-atomisation-wrapper",
    "/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan",
    "/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation",
    "/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout",
    "/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80",
    "/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map",
]

ROUTE_IDS = {
    "20260618-basilisk-atomisation-route": "basilisk_atomisation_route",
    "20260618-basilisk-official-atomisation-wrapper": "basilisk_official_atomisation_wrapper",
    "20260618-basilisk-rectangular-slot-gas-weber-scan": "basilisk_rectangular_slot_gas_weber_scan",
    "20260618-basilisk-rect-slot-morphology-escalation": "basilisk_rectangular_slot_morphology_escalation",
    "20260618-basilisk-2d-shear-sigma-scout": "basilisk_2d_shear_sigma_scout",
    "20260618-basilisk-3d-micro-translation-we80": "basilisk_3d_micro_translation_we80",
    "20260618-basilisk-3d-adaptive-refinement-map": "basilisk_3d_adaptive_refinement_map",
}

CASE_TABLE_FIELDS = [
    "route_id",
    "case_id",
    "model_type",
    "dimensionality",
    "source_case",
    "output_root",
    "status",
    "run_status",
    "We_g",
    "We_l",
    "density_ratio",
    "viscosity_ratio",
    "sigma_or_scaling",
    "gas_forcing",
    "perturbation",
    "maxlevel",
    "resolution_width_height_or_cells_across_sheet",
    "end_time",
    "active_front",
    "active_front_Dh",
    "tag_component_count",
    "post_exit_tag_component_count",
    "detached_proxy_count",
    "credible_post_exit_tag_component_count",
    "credible_detached_proxy_count",
    "interface_length_or_area_growth",
    "liquid_volume_or_area_proxy",
    "centroid",
    "spread",
    "aspect_ratio",
    "classification",
    "breakup_proxy_candidate",
    "scout_candidate_found",
    "public_ready",
    "exact_blocker",
    "next_step",
    "artifact_paths",
    "metrics_paths",
    "classification_notes",
    "no_push_confirmed",
]


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.stdout.strip()


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
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


def _get(mapping: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def route_id_for(root: Path) -> str:
    return ROUTE_IDS.get(root.name, root.name.replace("-", "_"))


def discover_files(root: Path, patterns: Iterable[str]) -> list[str]:
    if not root.exists():
        return []
    found: set[Path] = set()
    for pattern in patterns:
        found.update(root.rglob(pattern))
    return [str(path) for path in sorted(found)]


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def primary_summary(paths: list[str]) -> tuple[str, dict[str, Any]]:
    if not paths:
        return "", {}

    def rank(path: str) -> tuple[int, str]:
        name = Path(path).name
        if name.startswith("CODEX_") and name.endswith("_SUMMARY.json"):
            return (0, path)
        if "diagnostics_summary" in name:
            return (2, path)
        return (1, path)

    for path in sorted(paths, key=rank):
        try:
            return path, load_json(path)
        except Exception:
            continue
    return "", {}


def route_inventory(root: Path) -> dict[str, Any]:
    summaries = discover_files(root, ["*SUMMARY.json", "*summary.json", "*diagnostics_summary.json"])
    summary_path, summary = primary_summary(summaries)
    return {
        "route_id": route_id_for(root),
        "root_path": str(root),
        "exists": root.exists(),
        "summary_json_paths": summaries,
        "report_markdown_paths": discover_files(root, ["*REPORT.md"]),
        "metrics_paths": discover_files(root, ["metrics/*.csv", "metrics/*.json"]),
        "artifact_manifests": discover_files(root, ["artifact_manifest.txt"]),
        "mp4_contact_sheet_paths": discover_files(root, ["*.mp4", "*.png", "*/*.mp4", "*/*.png"]),
        "case_source": _get(summary, "case_source", "wrapper_source", "case_path"),
        "commit_hash": _get(summary, "commit_hash"),
        "status": _get(summary, "status"),
        "morphology_classification": _get(summary, "morphology_classification", "classification"),
        "public_ready": summary.get("public_ready", ""),
        "exact_blocker": _get(summary, "exact_blocker"),
        "next_step": _get(summary, "next_step", "recommended_followup"),
        "primary_summary_path": summary_path,
    }


def _read_csv_rows(path: str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _case_summary_paths(metrics_paths: list[str]) -> list[str]:
    return [p for p in metrics_paths if Path(p).name.endswith("case_summary.csv")]


def _flatten_gas_weber(summary: Mapping[str, Any], route_id: str) -> dict[str, Any]:
    dim = summary.get("dimensionless_parameters", {})
    morph = summary.get("morphology", {})
    resolution = summary.get("resolution", {})
    perturb = summary.get("perturbation", {})
    return {
        "case_id": route_id,
        "run_status": summary.get("status"),
        "we_g": dim.get("We_g_achieved") or dim.get("We_g_target"),
        "we_l": dim.get("We_l"),
        "density_ratio": dim.get("density_ratio_l_over_g"),
        "viscosity_ratio": dim.get("viscosity_ratio_l_over_g"),
        "sigma_or_scaling": dim.get("sigma") or "",
        "perturbation": perturb,
        "resolution_width_height": resolution.get("primary_slot_cells_width_height"),
        "max_tag_component_count": morph.get("max_tag_component_count"),
        "max_detached_proxy_count": morph.get("max_detached_proxy_count"),
        "max_active_front_Dh": morph.get("max_active_front_Dh"),
        "morphology_classification": morph.get("classification"),
        "public_ready": morph.get("public_ready"),
    }


def extract_case_rows(inventory: Mapping[str, Any], summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    route_id = _as_text(inventory.get("route_id"))
    metrics_paths = list(inventory.get("metrics_paths", []))
    rows: list[dict[str, Any]] = []

    for path in _case_summary_paths(metrics_paths):
        for row in _read_csv_rows(path):
            row["_metrics_source"] = path
            rows.append(row)
    if rows:
        return rows

    cases = summary.get("cases_run")
    if isinstance(cases, list) and cases and all(isinstance(item, Mapping) for item in cases):
        return [dict(item) for item in cases]

    if "dimensionless_parameters" in summary and "morphology" in summary:
        return [_flatten_gas_weber(summary, route_id)]

    return [
        {
            "case_id": summary.get("best_case") or route_id,
            "run_status": summary.get("run_status") or summary.get("status"),
            "model_type": summary.get("best_case_model_type") or "",
            "we_g": summary.get("best_case_we_g"),
            "sigma": summary.get("best_case_sigma_or_scaling"),
            "gas_forcing": summary.get("best_case_gas_forcing"),
            "resolution_width_height": summary.get("best_case_resolution_width_height") or summary.get("best_case_resolution"),
            "active_front_Dh": summary.get("best_case_active_front_Dh") or summary.get("best_case_active_front"),
            "max_tag_component_count": summary.get("max_tag_component_count"),
            "max_detached_proxy_count": summary.get("max_detached_proxy_count"),
            "max_credible_post_tag_component_count": summary.get("max_credible_tag_component_count"),
            "max_credible_detached_proxy_count": summary.get("max_credible_detached_proxy_count"),
            "max_interface_area_growth": summary.get("max_interface_area_growth"),
            "max_interface_length_growth": summary.get("max_interface_length_growth"),
            "morphology_classification": summary.get("morphology_classification"),
            "scout_candidate_found": summary.get("scout_candidate_found"),
            "micro_translation_candidate_found": summary.get("micro_translation_candidate_found"),
            "adaptive_candidate_found": summary.get("adaptive_candidate_found"),
            "breakup_proxy_candidate": summary.get("breakup_proxy_candidate"),
        }
    ]


def _perturbation(row: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    direct = _get(row, "perturbation", "best_case_perturbation")
    if direct:
        return _as_text(direct)
    pieces = []
    for key in ("perturb_amp", "perturb_period", "waves_y", "waves_z", "width/height wave numbers"):
        if row.get(key) not in (None, ""):
            pieces.append(f"{key}={row.get(key)}")
    if pieces:
        return "; ".join(pieces)
    return _as_text(summary.get("perturbation") or summary.get("best_case_perturbation") or "")


def normalize_case(
    root: Path,
    inventory: Mapping[str, Any],
    summary: Mapping[str, Any],
    row: Mapping[str, Any],
) -> dict[str, Any]:
    route_id = _as_text(inventory.get("route_id"))
    metrics_paths = list(inventory.get("metrics_paths", []))
    artifacts = list(inventory.get("mp4_contact_sheet_paths", []))
    normalized: dict[str, Any] = {
        "route_id": route_id,
        "case_id": _as_text(_get(row, "case_id", "name", default=summary.get("best_case") or route_id)),
        "model_type": _as_text(_get(row, "model_type", default=summary.get("best_case_model_type") or "")),
        "source_case": _as_text(_get(summary, "case_source", "wrapper_source", "case_path", default=inventory.get("case_source"))),
        "output_root": str(root),
        "status": _as_text(summary.get("status") or ""),
        "run_status": _as_text(_get(row, "run_status", "status", default=summary.get("run_status") or summary.get("status") or "")),
        "We_g": _as_text(_get(row, "we_g", "We_g", default=summary.get("best_case_we_g") or "")),
        "We_l": _as_text(_get(row, "we_l", "We_l")),
        "density_ratio": _as_text(_get(row, "density_ratio", "density_ratio_l_over_g")),
        "viscosity_ratio": _as_text(_get(row, "viscosity_ratio", "viscosity_ratio_l_over_g")),
        "sigma_or_scaling": _as_text(_get(row, "sigma", "sigma_or_scaling", default=summary.get("best_case_sigma_or_scaling") or "")),
        "gas_forcing": _as_text(_get(row, "gas_forcing", "gas_mode", default=summary.get("best_case_gas_forcing") or "")),
        "perturbation": _perturbation(row, summary),
        "maxlevel": _as_text(_get(row, "maxlevel")),
        "resolution_width_height_or_cells_across_sheet": _as_text(
            _get(
                row,
                "resolution_width_height",
                "resolution_width_height_or_cells_across_sheet",
                "cells_across_sheet",
                "resolution_cells_across_sheet",
                "slot_cells_w",
                default=summary.get("best_case_resolution_width_height") or summary.get("best_case_resolution") or "",
            )
        ),
        "end_time": _as_text(_get(row, "end_time", "final_time", "time_final", "last_output_time")),
        "active_front": _as_text(_get(row, "active_front", "active_front_x")),
        "active_front_Dh": _as_text(
            _get(row, "active_front_Dh", "max_active_front_Dh", default=summary.get("best_case_active_front_Dh") or summary.get("best_case_active_front") or "")
        ),
        "tag_component_count": _as_text(_get(row, "tag_component_count", "max_all_tag_component_count", "max_tag_component_count", default=summary.get("max_tag_component_count") or "")),
        "post_exit_tag_component_count": _as_text(_get(row, "post_exit_tag_component_count", "max_post_tag_component_count", "max_post_tag_component_count", default=summary.get("max_tag_component_count") or "")),
        "detached_proxy_count": _as_text(_get(row, "detached_proxy_count", "max_detached_proxy_count", "max_post_detached_proxy_count", default=summary.get("max_detached_proxy_count") or "")),
        "credible_post_exit_tag_component_count": _as_text(_get(row, "max_credible_post_tag_component_count", "credible_post_exit_tag_component_count", default=summary.get("max_credible_tag_component_count") or "")),
        "credible_detached_proxy_count": _as_text(_get(row, "max_credible_detached_proxy_count", "credible_detached_proxy_count", default=summary.get("max_credible_detached_proxy_count") or "")),
        "frames_with_post_components_gt1": _as_text(_get(row, "frames_with_post_components_gt1")),
        "frames_with_credible_post_components_gt1": _as_text(_get(row, "frames_with_credible_post_components_gt1")),
        "interface_length_or_area_growth": _as_text(
            _get(row, "max_interface_length_growth", "max_interface_area_growth", "interface_length_or_area_growth", default=summary.get("max_interface_length_growth") or summary.get("max_interface_area_growth") or "")
        ),
        "liquid_volume_or_area_proxy": _as_text(_get(row, "max_post_exit_volume_proxy", "max_post_exit_area_proxy", "liquid_volume_or_area_proxy")),
        "centroid": _as_text(_get(row, "centroid", "centroid_x")),
        "spread": _as_text(_get(row, "spread", "width_y", "y_extent")),
        "aspect_ratio": _as_text(_get(row, "aspect_ratio", "aspect_ratio_yz_covariance")),
        "classification": _as_text(_get(row, "morphology_classification", "classification", default=summary.get("morphology_classification") or "")),
        "breakup_proxy_candidate": _as_text(_get(row, "breakup_proxy_candidate", default=summary.get("breakup_proxy_candidate") or False)),
        "scout_candidate_found": _as_text(_get(row, "scout_candidate_found", default=summary.get("scout_candidate_found") or False)),
        "public_ready": _as_text(row.get("public_ready") if row.get("public_ready") not in (None, "") else summary.get("public_ready", False)),
        "exact_blocker": _as_text(summary.get("exact_blocker") or ""),
        "next_step": _as_text(summary.get("next_step") or summary.get("recommended_followup") or ""),
        "artifact_paths": json.dumps(artifacts, sort_keys=True),
        "metrics_paths": json.dumps(metrics_paths, sort_keys=True),
        "no_push_confirmed": _as_text(summary.get("no_push_confirmed", True)),
    }
    normalized["dimensionality"] = infer_dimensionality(normalized)

    classify_input = dict(normalized)
    classify_input.update(row)
    classified = classify_case(classify_input)
    normalized.update(classified)
    normalized["public_ready"] = "False" if not _as_bool(normalized.get("public_ready")) else "True"
    return {field: _as_text(normalized.get(field, "")) for field in CASE_TABLE_FIELDS}


def collect_roots(roots: Iterable[str | Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    for root_like in roots:
        root = Path(root_like)
        item = route_inventory(root)
        inventory.append(item)
        if not item["exists"]:
            continue
        summary_path, summary = primary_summary(list(item.get("summary_json_paths", [])))
        if not summary:
            continue
        for row in extract_case_rows(item, summary):
            cases.append(normalize_case(root, item, summary, row))
    return inventory, cases


def write_csv(path: Path, rows: list[Mapping[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def summarize_routes(cases: list[Mapping[str, Any]], inventory: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in cases:
        grouped.setdefault(_as_text(row.get("route_id")), []).append(row)

    summaries: list[dict[str, Any]] = []
    for item in inventory:
        route_id = _as_text(item.get("route_id"))
        rows = grouped.get(route_id, [])
        exists = bool(item.get("exists"))
        if not exists:
            summaries.append(
                {
                    "route_id": route_id,
                    "route_family": "missing",
                    "best_case": "",
                    "best_evidence_type": "missing",
                    "strongest_positive_metric": "",
                    "strongest_negative_evidence": "result root missing",
                    "transfer_status": "missing",
                    "recommended_next_step": "No action unless this optional route is needed.",
                }
            )
            continue

        route_family = route_family_for(route_id, rows)
        positives_2d = [r for r in rows if r.get("scout_candidate_found") == "True"]
        positives_3d = [r for r in rows if r.get("breakup_proxy_candidate") == "True"]
        public_ready = any(r.get("public_ready") == "True" for r in rows)
        best_row = choose_best_row(rows)

        if positives_3d:
            transfer_status = "3D candidate"
            evidence = "credible 3D breakup-proxy candidate"
            positive_metric = strongest_metric(positives_3d)
            negative = ""
        elif positives_2d:
            transfer_status = "2D-only"
            evidence = "positive reduced-model scout evidence"
            positive_metric = strongest_metric(positives_2d)
            negative = "not 3D validation"
        elif "official" in route_id or route_id == "basilisk_atomisation_route":
            transfer_status = "internal"
            evidence = "internal preliminary evidence"
            positive_metric = strongest_metric(rows)
            negative = "not public-ready; no stationary or validation claim"
        else:
            transfer_status = "3D negative"
            evidence = "negative conservative morphology result"
            positive_metric = ""
            negative = strongest_negative(rows)

        if not rows:
            evidence = "diagnostics_blocked"
            transfer_status = "blocked"
            negative = "no parseable case rows"

        summaries.append(
            {
                "route_id": route_id,
                "route_family": route_family,
                "best_case": _as_text(best_row.get("case_id") if best_row else ""),
                "best_evidence_type": evidence,
                "strongest_positive_metric": positive_metric,
                "strongest_negative_evidence": negative,
                "transfer_status": transfer_status,
                "public_ready_any_case": public_ready,
                "recommended_next_step": recommended_next_step(route_id, rows, transfer_status),
            }
        )
    return summaries


def route_family_for(route_id: str, rows: list[Mapping[str, Any]]) -> str:
    if "2d" in route_id:
        return "2D scout"
    if "official" in route_id:
        return "official atomisation wrapper"
    if route_id == "basilisk_atomisation_route":
        return "bounded VOF proof"
    if "3d" in route_id or "rectangular_slot" in route_id:
        return "3D rectangular-slot"
    dim = rows[0].get("dimensionality") if rows else ""
    return _as_text(dim or "unknown")


def choose_best_row(rows: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not rows:
        return None

    def score(row: Mapping[str, Any]) -> tuple[float, float, float]:
        candidate = 10 if row.get("breakup_proxy_candidate") == "True" else 0
        scout = 5 if row.get("scout_candidate_found") == "True" else 0
        growth = _as_float(row.get("interface_length_or_area_growth"))
        active = _as_float(row.get("active_front_Dh"))
        return (candidate + scout + growth, active, growth)

    return sorted(rows, key=score, reverse=True)[0]


def strongest_metric(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    best = choose_best_row(rows)
    if not best:
        return ""
    return (
        f"case={best.get('case_id')}; classification={best.get('classification')}; "
        f"credible_components={best.get('credible_post_exit_tag_component_count')}; "
        f"credible_detached={best.get('credible_detached_proxy_count')}; "
        f"interface_growth={best.get('interface_length_or_area_growth')}; "
        f"active_front_Dh={best.get('active_front_Dh')}"
    )


def strongest_negative(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    labels = sorted({str(row.get("classification")) for row in rows})
    max_active = max(_as_float(row.get("active_front_Dh")) for row in rows)
    max_credible = max(_as_float(row.get("credible_detached_proxy_count")) for row in rows)
    return f"classifications={labels}; max_active_front_Dh={max_active:g}; max_credible_detached_proxy_count={max_credible:g}"


def recommended_next_step(route_id: str, rows: list[Mapping[str, Any]], transfer_status: str) -> str:
    if transfer_status == "2D-only":
        return "Use as parameter-scout evidence only; translate cautiously to bounded 3D branches."
    if transfer_status == "3D candidate":
        return "Repeat and sensitivity-check before any public communication."
    if transfer_status == "3D negative":
        return "Do not repeat equivalent settings; change physics controls, refinement strategy, or solver route."
    if transfer_status == "internal":
        return "Keep internal unless a separate quality/statistics task supports public use."
    return "Inspect blockers or missing summaries before further analysis."


def write_markdown_inventory(path: Path, inventory: list[Mapping[str, Any]]) -> None:
    lines = [
        "# Basilisk Diagnostics Harness Input Inventory",
        "",
        "| route_id | exists | status | classification | public_ready | summaries | metrics | artifacts | blocker | next_step |",
        "|---|---:|---|---|---|---:|---:|---:|---|---|",
    ]
    for item in inventory:
        lines.append(
            "| {route_id} | {exists} | {status} | {classification} | {public_ready} | {summaries} | {metrics} | {artifacts} | {blocker} | {next_step} |".format(
                route_id=item.get("route_id", ""),
                exists=str(item.get("exists", "")).lower(),
                status=item.get("status", ""),
                classification=item.get("morphology_classification", ""),
                public_ready=item.get("public_ready", ""),
                summaries=len(item.get("summary_json_paths", [])),
                metrics=len(item.get("metrics_paths", [])),
                artifacts=len(item.get("mp4_contact_sheet_paths", [])),
                blocker=_as_text(item.get("exact_blocker", "")).replace("|", "/")[:140],
                next_step=_as_text(item.get("next_step", "")).replace("|", "/")[:140],
            )
        )
    lines.append("")
    lines.append("Heavy artifacts are inventoried by path only; the harness does not parse raw frames or videos.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_route_comparison(path: Path, summaries: list[Mapping[str, Any]]) -> None:
    lines = [
        "# Basilisk Route Comparison",
        "",
        "| route_id | family | transfer_status | best_case | evidence | public_ready | next_step |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in summaries:
        lines.append(
            "| {route_id} | {route_family} | {transfer_status} | {best_case} | {best_evidence_type} | {public_ready} | {next_step} |".format(
                route_id=row.get("route_id", ""),
                route_family=row.get("route_family", ""),
                transfer_status=row.get("transfer_status", ""),
                best_case=row.get("best_case", ""),
                best_evidence_type=row.get("best_evidence_type", ""),
                public_ready=str(row.get("public_ready_any_case", "")).lower(),
                next_step=_as_text(row.get("recommended_next_step", "")).replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The 2D shear-sigma branch is positive reduced-model scout evidence only.",
            "- The current 3D rectangular-slot branches remain negative under the conservative credible-component gate.",
            "- Official atomisation-wrapper evidence is internal/preliminary and not public-ready.",
            "- No route is treated as validation, production CFD, stationary spray evidence, or final atomisation prediction.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_classification_audit(path: Path, cases: list[Mapping[str, Any]], route_summaries: list[Mapping[str, Any]]) -> dict[str, bool]:
    by_route: dict[str, list[Mapping[str, Any]]] = {}
    for row in cases:
        by_route.setdefault(_as_text(row.get("route_id")), []).append(row)

    checks = {
        "2d_shear_sigma_positive_reduced_model": any(
            row.get("scout_candidate_found") == "True"
            and row.get("classification") == "2d_instability_scout_candidate_rollup_detached_proxy"
            for row in by_route.get("basilisk_2d_shear_sigma_scout", [])
        ),
        "3d_morphology_escalation_negative": all(
            row.get("breakup_proxy_candidate") != "True"
            for row in by_route.get("basilisk_rectangular_slot_morphology_escalation", [])
        ),
        "3d_gas_weber_scan_negative": all(
            row.get("breakup_proxy_candidate") != "True"
            for row in by_route.get("basilisk_rectangular_slot_gas_weber_scan", [])
        ),
        "3d_micro_translation_negative_if_present": all(
            row.get("breakup_proxy_candidate") != "True"
            for row in by_route.get("basilisk_3d_micro_translation_we80", [])
        ),
        "3d_adaptive_map_negative_with_debris_gate": all(
            row.get("breakup_proxy_candidate") != "True"
            and _as_float(row.get("credible_detached_proxy_count")) == 0.0
            for row in by_route.get("basilisk_3d_adaptive_refinement_map", [])
        ),
        "official_wrapper_internal_not_public": all(
            row.get("public_ready") != "True"
            for row in by_route.get("basilisk_official_atomisation_wrapper", [])
        ),
    }
    missing_routes = [
        row["route_id"]
        for row in route_summaries
        if row.get("transfer_status") == "missing"
    ]
    lines = ["# Basilisk Classification Audit", ""]
    for key, value in checks.items():
        lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
    lines.append("")
    lines.append(f"- Missing optional roots: {missing_routes if missing_routes else 'none'}")
    lines.append("")
    lines.append("## Notes")
    lines.append("- Connected waviness remains a negative morphology label.")
    lines.append("- 2D positive scout evidence is not promoted to 3D validation.")
    lines.append("- Raw 3D component counts rejected by credible gates remain internal diagnostics, not atomization claims.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checks


def write_usage(path: Path) -> None:
    lines = [
        "# Basilisk Diagnostics Harness Usage",
        "",
        "The harness consolidates existing Basilisk summaries and metrics. It does not rerun simulations, parse raw frame data, or create public-quality videos.",
        "",
        "```bash",
        "python3 scripts/basilisk_collect_diagnostics.py \\",
        "  --output-root /home/franco/stack-validation/20260618-basilisk-diagnostics-harness \\",
        "  /home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout \\",
        "  /home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan \\",
        "  /home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation \\",
        "  /home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80 \\",
        "  /home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map \\",
        "  /home/franco/stack-validation/20260618-basilisk-official-atomisation-wrapper \\",
        "  /home/franco/stack-validation/20260618-basilisk-atomisation-route",
        "```",
        "",
        "Classification policy:",
        "",
        "- Connected waviness is not atomization.",
        "- 2D scout positives are reduced-model evidence only.",
        "- 3D breakup-proxy labels require credible post-exit components or detached-volume proxies.",
        "- Public readiness remains false unless a separate publication-quality task establishes it.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_preflight(path: Path, output_root: Path, roots: list[str]) -> None:
    repo = Path.cwd()
    lines = [
        "# Basilisk Diagnostics Harness Preflight",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Repo: `{repo}`",
        f"- Output root: `{output_root}`",
        "- No push will be run.",
        "- No simulations are rerun by this harness.",
        "",
        "## Disk",
        "```text",
        _run(["df", "-h", "/", "/home"], repo),
        "```",
        "",
        "## Git Status",
        "```text",
        _run(["git", "status", "--short", "--branch"], repo),
        "```",
        "",
        "## Git Log",
        "```text",
        _run(["git", "log", "--oneline", "--decorate", "-15"], repo),
        "```",
        "",
        "## Python",
        "```text",
        _run(["python3", "--version"], repo),
        "```",
        "",
        "## Roots Requested",
    ]
    for root in roots:
        lines.append(f"- `{root}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(output_root: Path, roots: list[str]) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    inventory, cases = collect_roots(roots)
    route_summaries = summarize_routes(cases, inventory)

    write_preflight(output_root / "preflight.md", output_root, roots)
    write_markdown_inventory(output_root / "input_inventory.md", inventory)
    (output_root / "input_inventory.json").write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "roots": inventory}, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    write_csv(output_root / "consolidated_basilisk_case_table.csv", cases, CASE_TABLE_FIELDS)
    (output_root / "consolidated_basilisk_case_table.json").write_text(
        json.dumps(cases, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    write_route_comparison(output_root / "basilisk_route_comparison.md", route_summaries)
    (output_root / "basilisk_route_comparison.json").write_text(
        json.dumps(route_summaries, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    checks = write_classification_audit(output_root / "classification_audit.md", cases, route_summaries)
    write_usage(output_root / "diagnostics_harness_usage.md")
    return {
        "inventory": inventory,
        "cases": cases,
        "route_summaries": route_summaries,
        "classification_checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect existing Basilisk summaries/metrics into conservative diagnostics tables."
    )
    parser.add_argument("roots", nargs="*", help="Basilisk output roots to scan")
    parser.add_argument(
        "--output-root",
        default="/home/franco/stack-validation/20260618-basilisk-diagnostics-harness",
        help="Directory for consolidated CSV/JSON/Markdown outputs",
    )
    parser.add_argument("--default-roots", action="store_true", help="Use the known 20260618 Basilisk roots")
    args = parser.parse_args(argv)

    roots = args.roots
    if args.default_roots or not roots:
        roots = list(DEFAULT_ROOTS)
    result = write_outputs(Path(args.output_root), roots)
    print(f"scanned_roots={len(result['inventory'])}")
    print(f"case_rows={len(result['cases'])}")
    print(f"output_root={args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
