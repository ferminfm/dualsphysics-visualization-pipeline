#!/usr/bin/env python3
"""Classify operational stationarity from profile-integrated hydraulic metrics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from audit_internal_nozzle_transient_mechanism import finite, ols


EPS = 1e-30
EXIT_DH = 15.0
UPSTREAM_DH = 0.5
METRICS = {
    "Q_l": "Q_l",
    "mdot_l": "mdot_l",
    "area_weighted_velocity": "area_weighted_liquid_velocity",
    "flux_weighted_velocity": "flux_weighted_liquid_velocity",
    "J_k": "J_k_mixture",
    "J_total": "J_total",
    "pressure_drop": "forcing_to_plane_pressure_drop",
}
REQUIRED = ("Q_l", "area_weighted_velocity", "J_k", "J_total", "pressure_drop")


def read_csv(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as stream:
            rows.extend(csv.DictReader(stream))
    return rows


def plane_series(paths: list[Path], plane_dh: float, tstar_factor: float) -> list[dict[str, float]]:
    selected: dict[float, dict[str, float]] = {}
    for row in read_csv(paths):
        if abs(finite(row["plane_x_Dh"], "plane_x_Dh") - plane_dh) > 1e-9:
            continue
        t = finite(row["t"], "t")
        record = {"t": t, "tstar": t * tstar_factor}
        for label, column in METRICS.items():
            record[label] = finite(row[column], column)
        selected[round(t, 12)] = record
    return [selected[key] for key in sorted(selected)]


def raw_inventory(paths: list[Path], tstar_factor: float) -> list[dict[str, float]]:
    selected: dict[float, dict[str, float]] = {}
    for row in read_csv(paths):
        t = finite(row["t"], "raw t")
        selected[round(t, 12)] = {
            "t": t,
            "tstar": t * tstar_factor,
            "liquid_inventory": finite(row["liquid_volume"], "liquid_volume"),
            "cumulative_inflow": finite(row["cumulative_liquid_inflow"], "cumulative_liquid_inflow"),
            "cumulative_outflow": finite(row["cumulative_liquid_outflow"], "cumulative_liquid_outflow"),
        }
    return [selected[key] for key in sorted(selected)]


def window(series: list[dict[str, float]], end: float, width: float) -> list[dict[str, float]]:
    tolerance = 1e-10
    return [row for row in series if end - width - tolerance <= row["tstar"] <= end + tolerance]


def window_audit(series: list[dict[str, float]], end: float, width: float,
                 columns: tuple[str, ...]) -> dict[str, object]:
    rows = window(series, end, width)
    if len(rows) < 3 or rows[-1]["tstar"] - rows[0]["tstar"] < 0.9 * width:
        return {"status": "insufficient", "sample_count": len(rows)}
    return {
        "status": "available",
        "sample_count": len(rows),
        "start_tstar": rows[0]["tstar"],
        "end_tstar": rows[-1]["tstar"],
        "metrics": {
            name: ols([(row["tstar"], row[name]) for row in rows]) for name in columns
        },
    }


def slope_magnitude(metric: dict[str, object]) -> float:
    return max(abs(float(metric["relative_slope_percent_per_tstar"])),
               abs(float(metric["robust_relative_slope_percent_per_tstar"])))


def classify(final_two: dict[str, object], preceding_two: dict[str, object],
             mechanism_status: str) -> tuple[str, dict[str, object]]:
    if final_two.get("status") != "available":
        return "insufficient", {"reason": "final t-star=2 window unavailable"}
    metrics = final_two["metrics"]
    if any(name not in metrics for name in REQUIRED):
        return "insufficient", {"reason": "required true hydraulic metric unavailable"}
    quasi_checks = {
        name: {
            "slope_percent_per_tstar": slope_magnitude(metrics[name]),
            "drift_percent": abs(float(metrics[name]["end_to_end_relative_drift_percent"])),
            "passes": slope_magnitude(metrics[name]) <= 0.5
            and abs(float(metrics[name]["end_to_end_relative_drift_percent"])) <= 1.0,
        }
        for name in REQUIRED
    }
    if all(item["passes"] for item in quasi_checks.values()):
        return "operational_quasi_steady", {"quasi_steady_checks": quasi_checks}

    approaching_checks: dict[str, object] = {}
    if preceding_two.get("status") == "available":
        previous = preceding_two["metrics"]
        for name in REQUIRED:
            current_slope = slope_magnitude(metrics[name])
            previous_slope = slope_magnitude(previous[name])
            reduction = 1.0 - current_slope / max(previous_slope, EPS)
            approaching_checks[name] = {
                "current_slope_percent_per_tstar": current_slope,
                "preceding_slope_percent_per_tstar": previous_slope,
                "fractional_reduction": reduction,
                "passes": current_slope <= 2.0 and reduction >= 0.5,
            }
        if all(item["passes"] for item in approaching_checks.values()):
            return "approaching_quasi_steady", {
                "quasi_steady_checks": quasi_checks,
                "approaching_checks": approaching_checks,
            }

    terminal = ("persistent_transient_mechanism_identified"
                if mechanism_status == "identified" else "persistent_transient_unresolved")
    return terminal, {
        "quasi_steady_checks": quasi_checks,
        "approaching_checks": approaching_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plane-metrics", action="append", required=True, type=Path)
    parser.add_argument("--raw-summary", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--series-output", required=True, type=Path)
    parser.add_argument("--tstar-factor", type=float, default=7.180961047245843)
    parser.add_argument("--mechanism-status", choices=("identified", "unresolved"),
                        default="unresolved")
    args = parser.parse_args()
    if not math.isfinite(args.tstar_factor) or args.tstar_factor <= 0.:
        raise ValueError("tstar factor must be finite and positive")

    exit_series = plane_series(args.plane_metrics, EXIT_DH, args.tstar_factor)
    upstream_series = plane_series(args.plane_metrics, UPSTREAM_DH, args.tstar_factor)
    inventory_series = raw_inventory(args.raw_summary, args.tstar_factor)
    if len(exit_series) < 3:
        raise SystemExit("insufficient exit-plane coverage")
    final_tstar = exit_series[-1]["tstar"]
    windows: dict[str, object] = {}
    for width in (1.0, 2.0, 4.0):
        windows[f"final_{width:g}"] = window_audit(exit_series, final_tstar, width, tuple(METRICS))
        windows[f"preceding_{width:g}"] = window_audit(
            exit_series, final_tstar - width, width, tuple(METRICS)
        )
    inventory = {
        f"final_{width:g}": window_audit(
            inventory_series, final_tstar, width,
            ("liquid_inventory", "cumulative_inflow", "cumulative_outflow"),
        )
        for width in (1.0, 2.0, 4.0)
    }
    upstream = {
        f"final_{width:g}": window_audit(
            upstream_series, final_tstar, width, ("pressure_drop",),
        )
        for width in (1.0, 2.0, 4.0)
    }
    stationarity, gate = classify(windows["final_2"], windows["preceding_2"],
                                  args.mechanism_status)
    output = {
        "schema": "internal_nozzle_operational_stationarity_audit_v1",
        "coverage": {
            "start_tstar": exit_series[0]["tstar"],
            "final_tstar": final_tstar,
            "exit_sample_count": len(exit_series),
            "upstream_sample_count": len(upstream_series),
            "inventory_sample_count": len(inventory_series),
        },
        "stationarity_class": stationarity,
        "classification_gate": gate,
        "hydraulic_windows": windows,
        "inventory_windows": inventory,
        "upstream_windows": upstream,
        "criteria": {
            "operational_quasi_steady": "all required final t-star=2 slopes <=0.5%/t-star and drifts <=1%",
            "approaching_quasi_steady": "all required final slopes <=2%/t-star and at least 50% lower than preceding matched window",
        },
        "claim_boundary": "operational comparison state only; not mathematical stationarity, convergence, or physical validation",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.series_output.parent.mkdir(parents=True, exist_ok=True)
    with args.series_output.open("w", newline="", encoding="utf-8") as stream:
        names = ["tstar", *METRICS]
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        for row in exit_series:
            writer.writerow({name: f"{row[name]:.17g}" for name in names})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
