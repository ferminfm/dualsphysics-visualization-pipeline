#!/usr/bin/env python3
"""Validate a matched quarter/full smoke pair and render-only reconstruction."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def read_one_csv(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"expected one data row in {path}, found {len(rows)}")
    return rows[0]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def finite(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite value: {value}")
    return result


def relative_error(quarter: float, full: float, factor: float = 4.0) -> float:
    return abs(factor * quarter - full) / max(abs(full), 1e-12)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-root", type=Path, required=True)
    parser.add_argument("--reconstruction-manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--relative-tolerance", type=float, default=0.35)
    parser.add_argument("--symmetry-leakage-tolerance", type=float, default=1e-8)
    args = parser.parse_args()

    quarter_root = args.smoke_root / "quarter"
    full_root = args.smoke_root / "full"
    quarter = read_one_csv(quarter_root / "visual_pipeline_case_summary.csv")
    full = read_one_csv(full_root / "visual_pipeline_case_summary.csv")
    quarter_manifest = json.loads((quarter_root / "raw_export_manifest.json").read_text(encoding="utf-8"))
    full_manifest = json.loads((full_root / "raw_export_manifest.json").read_text(encoding="utf-8"))
    reconstruction = json.loads(args.reconstruction_manifest.read_text(encoding="utf-8"))

    matched_fields = [
        "case_mode", "t", "maxlevel", "baselevel", "base_pressure_value",
        "perturb_amp", "perturb_period", "target_u", "width", "height",
        "Dh", "area", "external_Dh", "diagnostic_dt", "visual_dt",
        "checkpoint_dt", "raw_export", "native_frames", "facet_export",
    ]
    mismatches = {
        field: {"quarter": quarter[field], "full": full[field]}
        for field in matched_fields
        if quarter[field] != full[field]
    }

    metric_errors = {
        "exit_flow_4x_relative_error": relative_error(
            finite(quarter["exit_flow"]), finite(full["exit_flow"])
        ),
        "exit_liquid_area_4x_relative_error": relative_error(
            finite(quarter["exit_liquid_area"]), finite(full["exit_liquid_area"])
        ),
        "liquid_volume_4x_relative_error": relative_error(
            finite(quarter["liquid_volume"]), finite(full["liquid_volume"])
        ),
        "interface_proxy_4x_relative_error": relative_error(
            finite(quarter["max_interface_proxy"]), finite(full["max_interface_proxy"])
        ),
    }

    qframes = {finite(row["t"]): row for row in read_csv(quarter_root / "raw_frame_summary.csv")}
    fframes = {finite(row["t"]): row for row in read_csv(full_root / "raw_frame_summary.csv")}
    shared_times = sorted(set(qframes) & set(fframes))
    frame_checks = []
    for time in shared_times:
        qrow, frow = qframes[time], fframes[time]
        frame_checks.append(
            {
                "t": time,
                "exit_flow_4x_relative_error": relative_error(
                    finite(qrow["exit_flow"]), finite(frow["exit_flow"])
                ),
                "liquid_volume_4x_relative_error": relative_error(
                    finite(qrow["liquid_volume"]), finite(frow["liquid_volume"])
                ),
            }
        )

    symmetry_leakage = finite(quarter["symmetry_leakage"])
    gates = {
        "matched_configuration": not mismatches,
        "domain_labels": quarter["domain_mode"] == "quarter" and full["domain_mode"] == "full",
        "stable_smokes": quarter["stable_flag"] == "1" and full["stable_flag"] == "1",
        "nonzero_exit_flow": abs(finite(full["exit_flow"])) > 1e-12,
        "flux_match": metric_errors["exit_flow_4x_relative_error"] <= args.relative_tolerance,
        "area_match": metric_errors["exit_liquid_area_4x_relative_error"] <= args.relative_tolerance,
        "mass_match": metric_errors["liquid_volume_4x_relative_error"] <= args.relative_tolerance,
        "interface_measure_match": metric_errors["interface_proxy_4x_relative_error"] <= args.relative_tolerance,
        "symmetry_plane_no_penetration": symmetry_leakage <= args.symmetry_leakage_tolerance,
        "no_periodic_radial_boundaries": (
            quarter_manifest.get("transverse_periodic_boundaries") is False
            and full_manifest.get("transverse_periodic_boundaries") is False
        ),
        "quarter_boundary_manifest": quarter_manifest.get("boundary_model") == "reflection_planes_y0_z0",
        "render_only_reconstruction": (
            reconstruction.get("passed") is True
            and reconstruction.get("independent_full_domain_physics") is False
            and reconstruction.get("breakup_evidence_allowed") is False
            and "RENDER ONLY" in reconstruction.get("persistent_label", "")
        ),
        "shared_frame_times": bool(shared_times),
    }
    passed = all(gates.values())
    result = {
        "classification": "quarter_domain_symmetry_smoke_qa",
        "smoke_root": str(args.smoke_root),
        "relative_tolerance": args.relative_tolerance,
        "symmetry_leakage_tolerance": args.symmetry_leakage_tolerance,
        "matched_field_mismatches": mismatches,
        "metric_errors": metric_errors,
        "symmetry_leakage": symmetry_leakage,
        "shared_frame_count": len(shared_times),
        "frame_checks": frame_checks,
        "gates": gates,
        "passed": passed,
        "task03_authorization": "go_bounded_benchmark" if passed else "no_go_repair_task02",
        "claim_boundary": (
            "Quarter reconstruction is render-only scout evidence. It is not an "
            "independent full-domain sample and supports no breakup claim."
        ),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    gate_lines = "\n".join(
        f"- {'PASS' if value else 'FAIL'}: `{name}`" for name, value in gates.items()
    )
    metric_lines = "\n".join(f"- `{name}`: `{value:.6g}`" for name, value in metric_errors.items())
    args.output_report.write_text(
        "# Quarter-domain smoke QA\n\n"
        f"Overall: **{'PASS' if passed else 'FAIL'}**\n\n"
        "## Gates\n\n" + gate_lines + "\n\n"
        "## Four-times-quarter versus full errors\n\n" + metric_lines + "\n\n"
        f"- symmetry leakage: `{symmetry_leakage:.6g}`\n"
        f"- shared frame times: `{len(shared_times)}`\n"
        f"- Task 03 decision: `{result['task03_authorization']}`\n\n"
        "The four mirrored quadrants are render-only copies of one simulation. "
        "They are not independent full-domain physics and are not breakup evidence.\n",
        encoding="utf-8",
    )
    print(f"QUARTER_QA={args.output_json}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
