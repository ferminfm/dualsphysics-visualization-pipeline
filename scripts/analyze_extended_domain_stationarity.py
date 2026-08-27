#!/usr/bin/env python3
"""Derive reproducible trailing-window hydraulic stationarity statistics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


TSTAR_PER_TIME = 7.180961047245843


def fit(values: list[tuple[float, float]]) -> dict[str, float]:
    xs, ys = zip(*values)
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    return {
        "mean": ybar,
        "relative_slope_percent_per_tstar": 100 * slope / ybar,
        "end_to_end_relative_drift_percent": 100 * (ys[-1] - ys[0]) / ybar,
        "coefficient_of_variation_percent": 100 * (sum((y - ybar) ** 2 for y in ys) / len(ys)) ** 0.5 / ybar,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_summary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = list(csv.DictReader(args.raw_summary.open(encoding="utf-8")))
    samples = [{**row, "tstar": float(row["t"]) * TSTAR_PER_TIME,
                "derived_exit_momentum_proxy": float(row["exit_flow"]) * float(row["mean_exit_velocity"])}
               for row in rows]
    final = samples[-1]["tstar"]
    windows: dict[str, dict[str, object]] = {}
    for width in (1.0, 2.0):
        selected = [row for row in samples if row["tstar"] >= final - width]
        windows[f"final_tstar_{width:g}"] = {
            "sample_count": len(selected),
            "start_tstar": selected[0]["tstar"],
            "end_tstar": final,
            "metrics": {name: fit([(row["tstar"], float(row[column])) for row in selected])
                        for name, column in {"Q": "exit_flow", "Ue": "mean_exit_velocity",
                                             "J_proxy": "derived_exit_momentum_proxy",
                                             "liquid_volume": "liquid_volume"}.items()},
        }
    classification = "TRANSIENT"
    two = windows["final_tstar_2"]["metrics"]
    if all(abs(two[name]["relative_slope_percent_per_tstar"]) <= 0.5 and
           abs(two[name]["end_to_end_relative_drift_percent"]) <= 1.0 for name in ("Q", "Ue", "J_proxy")):
        classification = "OPERATIONAL_QUASI_STEADY"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": "extended_domain_stationarity_v1", "final_tstar": final,
                                        "classification": classification, "windows": windows}, indent=2) + "\n",
                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
