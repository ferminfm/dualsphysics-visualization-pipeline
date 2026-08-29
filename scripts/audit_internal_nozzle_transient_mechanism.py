#!/usr/bin/env python3
"""Audit restart, diagnostic, hydraulic, and transient mechanisms deterministically."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Callable, Iterable


TSTAR_PER_TIME = 7.180961047245843
EPS = 1e-30


def finite(value: str | float | int, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"nonfinite {name}: {value!r}")
    return number


def read_rows(paths: Iterable[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def dedupe_time(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    selected: dict[float, dict[str, str]] = {}
    for row in rows:
        selected[round(finite(row["t"], "t"), 12)] = row
    return [selected[key] for key in sorted(selected)]


def ols(points: list[tuple[float, float]]) -> dict[str, float | int | str]:
    if len(points) < 3:
        raise ValueError("at least three points are required")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    xbar = statistics.fmean(xs)
    ybar = statistics.fmean(ys)
    denom = math.fsum((x - xbar) ** 2 for x in xs)
    if denom <= 0.0:
        raise ValueError("time coordinates are degenerate")
    slope = math.fsum((x - xbar) * (y - ybar) for x, y in points) / denom
    intercept = ybar - slope * xbar
    residuals = [y - (intercept + slope * x) for x, y in points]
    sse = math.fsum(r * r for r in residuals)
    sst = math.fsum((y - ybar) ** 2 for y in ys)
    steps = [ys[n + 1] - ys[n] for n in range(len(ys) - 1)]
    direction = 1.0 if slope >= 0.0 else -1.0
    monotone_fraction = statistics.fmean(
        1.0 if direction * delta >= 0.0 else 0.0 for delta in steps
    )
    pair_slopes = [
        (ys[j] - ys[i]) / (xs[j] - xs[i])
        for i in range(len(xs))
        for j in range(i + 1, len(xs))
        if xs[j] > xs[i]
    ]
    robust_slope = statistics.median(pair_slopes)
    cv = math.sqrt(math.fsum((y - ybar) ** 2 for y in ys) / len(ys)) / max(abs(ybar), EPS)
    return {
        "sample_count": len(points),
        "start_tstar": xs[0],
        "end_tstar": xs[-1],
        "mean": ybar,
        "slope": slope,
        "robust_slope": robust_slope,
        "relative_slope_percent_per_tstar": 100.0 * slope / max(abs(ybar), EPS),
        "robust_relative_slope_percent_per_tstar": 100.0 * robust_slope / max(abs(ybar), EPS),
        "end_to_end_relative_drift_percent": 100.0 * (ys[-1] - ys[0]) / max(abs(ybar), EPS),
        "coefficient_of_variation_percent": 100.0 * cv,
        "r_squared": 1.0 - sse / sst if sst > 0.0 else 1.0,
        "rmse": math.sqrt(sse / len(points)),
        "monotone_with_fitted_trend_fraction": monotone_fraction,
    }


def linear_coefficients(points: list[tuple[float, float]]) -> tuple[float, float]:
    result = ols(points)
    slope = float(result["slope"])
    xbar = statistics.fmean(p[0] for p in points)
    ybar = statistics.fmean(p[1] for p in points)
    return ybar - slope * xbar, slope


def two_basis_fit(
    points: list[tuple[float, float]], basis: Callable[[float], float]
) -> tuple[float, float, float]:
    zs = [basis(x) for x, _ in points]
    ys = [y for _, y in points]
    zbar, ybar = statistics.fmean(zs), statistics.fmean(ys)
    denom = math.fsum((z - zbar) ** 2 for z in zs)
    if denom <= 0.0:
        return ybar, 0.0, math.inf
    b = math.fsum((z - zbar) * (y - ybar) for z, y in zip(zs, ys)) / denom
    a = ybar - b * zbar
    sse = math.fsum((y - (a + b * z)) ** 2 for z, y in zip(zs, ys))
    return a, b, sse


def aicc(sse: float, n: int, parameters: int) -> float:
    safe = max(sse / n, 1e-300)
    base = n * math.log(safe) + 2.0 * parameters
    return base + 2.0 * parameters * (parameters + 1) / max(1, n - parameters - 1)


def fit_models(points: list[tuple[float, float]]) -> dict[str, object]:
    n = len(points)
    split = max(3, min(n - 2, int(math.floor(0.8 * n))))
    train, holdout = points[:split], points[split:]
    x0 = points[0][0]

    def score_model(
        name: str,
        parameters: int,
        predictor: Callable[[float], float],
        sse: float,
        details: dict[str, object],
    ) -> dict[str, object]:
        holdout_sse = math.fsum((y - predictor(x)) ** 2 for x, y in holdout)
        return {
            "name": name,
            "parameters": parameters,
            "aicc": aicc(sse, n, parameters),
            "rmse": math.sqrt(sse / n),
            "rolling_holdout_rmse": math.sqrt(holdout_sse / len(holdout)),
            **details,
        }

    la, lb = linear_coefficients(points)
    linear_sse = math.fsum((y - (la + lb * x)) ** 2 for x, y in points)
    models: list[dict[str, object]] = [
        score_model("linear", 2, lambda x: la + lb * x, linear_sse,
                    {"intercept": la, "slope": lb, "asymptote": None})
    ]

    best_exp: tuple[float, float, float, float] | None = None
    for logk in [math.log(1e-3) + j * (math.log(20.0) - math.log(1e-3)) / 239 for j in range(240)]:
        k = math.exp(logk)
        basis = lambda x, kk=k: math.exp(-kk * (x - x0))
        a, b, sse = two_basis_fit(points, basis)
        if best_exp is None or sse < best_exp[3]:
            best_exp = (k, a, b, sse)
    assert best_exp is not None
    ek, ea, eb, esse = best_exp
    exp_predict = lambda x: ea + eb * math.exp(-ek * (x - x0))
    exp_model = score_model(
        "exponential_finite_asymptote", 3, exp_predict, esse,
        {"rate": ek, "asymptote": ea,
         "observed_time_constants": (points[-1][0] - x0) * ek},
    )
    exp_model["asymptote_identifiable"] = bool(
        float(exp_model["observed_time_constants"]) >= 2.0
        and float(exp_model["aicc"]) + 6.0 < float(models[0]["aicc"])
        and 1.05e-3 < ek < 19.0
        and float(exp_model["rolling_holdout_rmse"]) < float(models[0]["rolling_holdout_rmse"])
    )
    models.append(exp_model)

    best_power: tuple[float, float, float, float] | None = None
    for power in [0.1 + j * 3.9 / 195 for j in range(196)]:
        basis = lambda x, pp=power: (1.0 + x - x0) ** (-pp)
        a, b, sse = two_basis_fit(points, basis)
        if best_power is None or sse < best_power[3]:
            best_power = (power, a, b, sse)
    assert best_power is not None
    pp, pa, pb, psse = best_power
    power_predict = lambda x: pa + pb * (1.0 + x - x0) ** (-pp)
    power_model = score_model(
        "power_relaxation_finite_asymptote", 3, power_predict, psse,
        {"power": pp, "asymptote": pa},
    )
    power_model["asymptote_identifiable"] = bool(
        float(power_model["aicc"]) + 6.0 < float(models[0]["aicc"])
        and float(power_model["rolling_holdout_rmse"]) < float(models[0]["rolling_holdout_rmse"])
    )
    models.append(power_model)

    piecewise: dict[str, object] | None = None
    min_side = max(4, n // 8)
    for split_index in range(min_side, n - min_side + 1):
        left, right = points[:split_index], points[split_index:]
        if len(right) < 3:
            continue
        l_a, l_b = linear_coefficients(left)
        r_a, r_b = linear_coefficients(right)
        sse = math.fsum((y - (l_a + l_b * x)) ** 2 for x, y in left)
        sse += math.fsum((y - (r_a + r_b * x)) ** 2 for x, y in right)
        candidate = {
            "name": "piecewise_linear", "parameters": 4, "aicc": aicc(sse, n, 4),
            "rmse": math.sqrt(sse / n), "break_tstar": right[0][0],
            "left_slope": l_b, "right_slope": r_b,
        }
        if piecewise is None or float(candidate["aicc"]) < float(piecewise["aicc"]):
            piecewise = candidate
    if piecewise is not None:
        models.append(piecewise)
    models.sort(key=lambda item: float(item["aicc"]))
    best_aicc = float(models[0]["aicc"])
    for model in models:
        model["delta_aicc"] = float(model["aicc"]) - best_aicc
    return {
        "models": models,
        "preferred_by_aicc": models[0]["name"],
        "finite_asymptote_identified": any(
            bool(model.get("asymptote_identifiable")) for model in models
        ),
        "claim_guard": "no stationary asymptote is claimed unless model and coverage criteria both pass",
    }


def normalize_plane(row: dict[str, str]) -> dict[str, float | str]:
    aliases = {
        "J_k_liquid": "liquid_kinetic_momentum_flux",
        "J_k_mixture": "mixture_kinetic_momentum_flux",
        "J_p": "pressure_contribution",
    }
    normalized: dict[str, float | str] = {
        "case_id": row.get("case_id", ""),
        "t": finite(row["t"], "plane t"),
        "tstar": finite(row["t"], "plane t") * TSTAR_PER_TIME,
        "plane_x_Dh": finite(row["plane_x_Dh"], "plane_x_Dh"),
        "restart_lineage": row.get("restart_lineage", ""),
    }
    for name in (
        "fluid_area", "liquid_area", "Q_l", "mdot_l", "mdot_mix",
        "liquid_kinetic_momentum_flux", "mixture_kinetic_momentum_flux",
        "pressure_contribution", "J_total", "area_weighted_liquid_velocity",
        "flux_weighted_liquid_velocity", "area_mean_pressure",
        "forcing_to_plane_pressure_drop", "legacy_Q_l_times_area_weighted_velocity",
    ):
        source = name
        if source not in row:
            source = next((key for key, value in aliases.items() if value == name and key in row), source)
        if source in row and row[source] != "":
            normalized[name] = finite(row[source], name)
    return normalized


def closest(rows: list[dict[str, float | str]], t: float, tolerance: float = 0.001) -> dict[str, float | str] | None:
    candidate = min(rows, key=lambda row: abs(float(row["t"]) - t), default=None)
    if candidate is None or abs(float(candidate["t"]) - t) > tolerance:
        return None
    return candidate


def pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    xb, yb = statistics.fmean(xs), statistics.fmean(ys)
    xx = math.fsum((x - xb) ** 2 for x in xs)
    yy = math.fsum((y - yb) ** 2 for y in ys)
    if xx <= 0.0 or yy <= 0.0:
        return None
    return math.fsum((x - xb) * (y - yb) for x, y in pairs) / math.sqrt(xx * yy)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-summary", action="append", type=Path, required=True)
    parser.add_argument("--plane-metrics", action="append", type=Path, required=True)
    parser.add_argument("--health-metrics", action="append", type=Path, default=[])
    parser.add_argument("--field-manifest", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--series-output", type=Path, required=True)
    args = parser.parse_args()

    raw = dedupe_time(read_rows(args.raw_summary))
    if len(raw) < 10:
        raise SystemExit("insufficient raw summary coverage")
    for row in raw:
        row["tstar"] = str(finite(row["t"], "raw t") * TSTAR_PER_TIME)

    plane_map: dict[tuple[float, float], dict[str, float | str]] = {}
    for row in read_rows(args.plane_metrics):
        normalized = normalize_plane(row)
        plane_map[(round(float(normalized["t"]), 12), float(normalized["plane_x_Dh"]))] = normalized
    planes = [plane_map[key] for key in sorted(plane_map)]
    exit_rows = [row for row in planes if abs(float(row["plane_x_Dh"]) - 15.0) < 1e-9]
    inner_rows = [row for row in planes if abs(float(row["plane_x_Dh"]) - 14.5) < 1e-9]
    near_rows = [row for row in planes if abs(float(row["plane_x_Dh"]) - 15.25) < 1e-9]
    upstream_rows = [row for row in planes if abs(float(row["plane_x_Dh"]) - 0.5) < 1e-9]
    if len(exit_rows) < 5 or len(upstream_rows) < 5:
        raise SystemExit("insufficient true-flux plane coverage")

    legacy_matches: list[dict[str, float]] = []
    for row in inner_rows:
        match = min(raw, key=lambda item: abs(finite(item["t"], "raw t") - float(row["t"])))
        delta = abs(finite(match["t"], "raw t") - float(row["t"]))
        if delta <= 0.001:
            true_q = float(row["Q_l"])
            legacy_q = finite(match["exit_flow"], "exit_flow")
            legacy_matches.append({
                "t": float(row["t"]), "true_Q_l_inner_plane": true_q,
                "legacy_exit_flow": legacy_q, "legacy_to_true_ratio": legacy_q / max(abs(true_q), EPS),
            })

    boundary_steps: list[dict[str, float | str]] = []
    ordinary_step_changes: list[float] = []
    for previous, current in zip(raw, raw[1:]):
        q0 = finite(previous["exit_flow"], "exit_flow")
        q1 = finite(current["exit_flow"], "exit_flow")
        rel = 100.0 * (q1 - q0) / max(abs(q0), EPS)
        if previous.get("restart_lineage", "") != current.get("restart_lineage", ""):
            boundary_steps.append({
                "tstar": finite(current["tstar"], "tstar"),
                "relative_Q_step_percent": rel,
                "from": previous.get("restart_lineage", ""),
                "to": current.get("restart_lineage", ""),
            })
        else:
            ordinary_step_changes.append(abs(rel))
    typical_step = statistics.median(ordinary_step_changes) if ordinary_step_changes else 0.0
    max_boundary_step = max((abs(float(row["relative_Q_step_percent"])) for row in boundary_steps), default=0.0)
    # Raw output has no paired pre/post-restore samples at an identical time.
    # Its finite-time steps can expose suspicious rate changes but cannot by
    # themselves establish an instantaneous checkpoint jump.
    checkpoint_discontinuity = False

    final_tstar = finite(raw[-1]["tstar"], "final tstar")
    metric_columns = {
        "legacy_Q": "exit_flow", "legacy_Ue": "mean_exit_velocity",
        "liquid_volume": "liquid_volume", "cumulative_inflow": "cumulative_liquid_inflow",
        "interface_proxy": "interface_proxy", "active_front_Dh": "active_front_Dh",
    }
    raw_windows: dict[str, object] = {}
    for width in (1.0, 2.0, 4.0):
        selected = [row for row in raw if finite(row["tstar"], "tstar") >= final_tstar - width]
        if len(selected) >= 3:
            raw_windows[f"final_{width:g}"] = {
                name: ols([(finite(row["tstar"], "tstar"), finite(row[column], column)) for row in selected])
                for name, column in metric_columns.items()
            }
        else:
            raw_windows[f"final_{width:g}"] = {
                "status": "insufficient", "sample_count": len(selected)
            }

    true_windows: dict[str, object] = {}
    for width in (1.0, 2.0, 4.0):
        selected = [row for row in exit_rows if float(row["tstar"]) >= final_tstar - width]
        if len(selected) >= 3:
            true_windows[f"final_{width:g}"] = {
                name: ols([(float(row["tstar"]), float(row[column])) for row in selected])
                for name, column in {
                    "Q_l": "Q_l", "J_k": "mixture_kinetic_momentum_flux",
                    "J_p": "pressure_contribution", "J_total": "J_total",
                    "exit_liquid_area": "liquid_area", "area_weighted_velocity": "area_weighted_liquid_velocity",
                }.items()
            }

    pressure_fit = ols([(float(row["tstar"]), float(row["area_mean_pressure"])) for row in upstream_rows])
    inventory_start = finite(raw[0]["liquid_volume"], "liquid_volume")
    inventory_end = finite(raw[-1]["liquid_volume"], "liquid_volume")
    cumulative_inflow = finite(raw[-1]["cumulative_liquid_inflow"], "cumulative_liquid_inflow")

    plane_sensitivity: list[dict[str, float]] = []
    for exit_row in exit_rows:
        inner = closest(inner_rows, float(exit_row["t"]), 1e-9)
        near = closest(near_rows, float(exit_row["t"]), 1e-9)
        if inner is not None and near is not None:
            q = float(exit_row["Q_l"])
            plane_sensitivity.append({
                "t": float(exit_row["t"]),
                "inner_vs_exit_Q_percent": 100.0 * (float(inner["Q_l"]) - q) / max(abs(q), EPS),
                "near_vs_exit_Q_percent": 100.0 * (float(near["Q_l"]) - q) / max(abs(q), EPS),
            })

    interface_pairs: list[tuple[float, float]] = []
    for row in exit_rows:
        match = min(raw, key=lambda item: abs(finite(item["t"], "raw t") - float(row["t"])))
        if abs(finite(match["t"], "raw t") - float(row["t"])) <= 0.001:
            interface_pairs.append((float(row["Q_l"]), finite(match["interface_proxy"], "interface_proxy")))

    health_rows = dedupe_time(read_rows(args.health_metrics)) if args.health_metrics else []
    health_summary: dict[str, object] = {"available": bool(health_rows)}
    if health_rows:
        for name in ("mgp_i", "mgpf_i", "mgu_i", "total_grid_cells", "dt"):
            values = [finite(row[name], name) for row in health_rows]
            health_summary[name] = {
                "min": min(values), "max": max(values), "final": values[-1],
            }

    field_rows = dedupe_time(read_rows(args.field_manifest)) if args.field_manifest else []
    field_summary: dict[str, object] = {"available": bool(field_rows), "frame_count": len(field_rows)}
    if field_rows and "sample_count" in field_rows[0]:
        counts = [int(row["sample_count"]) for row in field_rows]
        field_summary.update({"sample_count_min": min(counts), "sample_count_max": max(counts), "sample_count_final": counts[-1]})

    model_series = {
        "legacy_Q": [(finite(row["tstar"], "tstar"), finite(row["exit_flow"], "exit_flow")) for row in raw],
        "legacy_Ue": [(finite(row["tstar"], "tstar"), finite(row["mean_exit_velocity"], "mean_exit_velocity")) for row in raw],
        "true_Q_exit": [(float(row["tstar"]), float(row["Q_l"])) for row in exit_rows],
        "true_J_total_exit": [(float(row["tstar"]), float(row["J_total"])) for row in exit_rows],
    }
    model_audit = {name: fit_models(points) for name, points in model_series.items() if len(points) >= 10}

    evidence = {
        "legacy_exit_flow_double_layer_bias": {
            "matched_count": len(legacy_matches),
            "median_legacy_to_true_Q_ratio": statistics.median(row["legacy_to_true_ratio"] for row in legacy_matches),
            "classification": "diagnostic_magnitude_artifact_confirmed",
        },
        "momentum_proxy": {
            "classification": "proxy_limitation_confirmed",
            "reason": "legacy Q times mean velocity is neither the profile-integrated kinetic flux nor pressure-inclusive total axial flux",
        },
        "checkpoint_continuity": {
            "transition_count": len(boundary_steps),
            "typical_nonboundary_Q_step_percent": typical_step,
            "max_boundary_Q_step_percent": max_boundary_step,
            "discontinuity_supported": checkpoint_discontinuity,
            "direct_matched_control_required": True,
            "interpretation": "finite-time boundary steps are not instantaneous pre/post-restore pairs",
            "transitions": boundary_steps,
        },
        "upstream_pressure": {
            "start": float(upstream_rows[0]["area_mean_pressure"]),
            "end": float(upstream_rows[-1]["area_mean_pressure"]),
            "trend": pressure_fit,
            "decay_supported": pressure_fit["relative_slope_percent_per_tstar"] < -0.5,
        },
        "liquid_inventory": {
            "start": inventory_start, "end": inventory_end,
            "relative_change_percent": 100.0 * (inventory_end - inventory_start) / max(abs(inventory_start), EPS),
            "cumulative_inflow": cumulative_inflow,
            "finite_inventory_depletion_supported": inventory_end < inventory_start,
        },
        "exit_plane_sensitivity": {
            "sample_count": len(plane_sensitivity),
            "median_abs_inner_vs_exit_Q_percent": statistics.median(abs(row["inner_vs_exit_Q_percent"]) for row in plane_sensitivity),
            "median_abs_near_vs_exit_Q_percent": statistics.median(abs(row["near_vs_exit_Q_percent"]) for row in plane_sensitivity),
        },
        "external_interface_correlation_with_true_Q": pearson(interface_pairs),
    }

    output = {
        "schema": "internal_nozzle_transient_mechanism_audit_v1",
        "tstar_per_physical_time": TSTAR_PER_TIME,
        "coverage": {
            "raw_samples": len(raw), "true_plane_samples": len(planes),
            "true_exit_samples": len(exit_rows), "start_tstar": finite(raw[0]["tstar"], "start tstar"),
            "final_tstar": final_tstar,
        },
        "raw_trailing_windows": raw_windows,
        "true_flux_trailing_windows": true_windows,
        "model_audit": model_audit,
        "evidence": evidence,
        "solver_health": health_summary,
        "field_population": field_summary,
        "baseline_validity": "retained" if not checkpoint_discontinuity and not evidence["upstream_pressure"]["decay_supported"] else "requires_control",
        "mechanism_candidates": {
            "diagnostic_artifact": "confirmed_for_legacy_magnitude_not_trend",
            "momentum_proxy_limitation": "confirmed",
            "checkpoint_or_segmentation_discontinuity": "not_supported" if not checkpoint_discontinuity else "supported",
            "finite_inventory_or_pressure_decay": "not_supported" if not evidence["liquid_inventory"]["finite_inventory_depletion_supported"] and not evidence["upstream_pressure"]["decay_supported"] else "supported",
            "pressure_forcing_implementation": "continuous_source_and_pressure_readback_supported_but_short_operational_control_required",
            "exit_area_or_profile_evolution": "quantified_requires_control_interpretation",
            "external_two_phase_coupling": "correlation_only_not_causal",
            "amr_or_numerical_drift": "instrumentation_added_for_continuation" if not health_rows else "quantified",
            "dominant_cause": "not_yet_assigned_before_controls",
        },
        "claim_boundary": "retrospective evidence does not establish stationarity, convergence, physical validation, or a causal asymptote",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    args.series_output.parent.mkdir(parents=True, exist_ok=True)
    with args.series_output.open("w", newline="", encoding="utf-8") as handle:
        names = ["series", "tstar", "value"]
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for name, points in model_series.items():
            for tstar, value in points:
                writer.writerow({"series": name, "tstar": f"{tstar:.17g}", "value": f"{value:.17g}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
