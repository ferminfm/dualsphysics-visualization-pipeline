#!/usr/bin/env python3
"""Validate the 2:1 area-matched rectangular inlet profiles."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Callable


RADIUS = 1.0 / 12.0
AREA = math.pi * RADIUS**2
HEIGHT = math.sqrt(AREA / 2.0)
WIDTH = 2.0 * HEIGHT
HALF_WIDTH = WIDTH / 2.0
HALF_HEIGHT = HEIGHT / 2.0
HYDRAULIC_DIAMETER = 2.0 * WIDTH * HEIGHT / (WIDTH + HEIGHT)


def inside_rectangle(y: float, z: float) -> bool:
    return abs(y) <= HALF_WIDTH and abs(z) <= HALF_HEIGHT


def top_hat(y: float, z: float) -> float:
    return 1.0 if abs(y) < HALF_WIDTH and abs(z) < HALF_HEIGHT else 0.0


def separable_parabolic(y: float, z: float) -> float:
    if not inside_rectangle(y, z):
        return 0.0
    yn = y / HALF_WIDTH
    zn = z / HALF_HEIGHT
    return 2.25 * max(0.0, 1.0 - yn * yn) * max(0.0, 1.0 - zn * zn)


def poiseuille_raw(y: float, z: float, terms: int) -> float:
    if not inside_rectangle(y, z):
        return 0.0
    a = HALF_WIDTH
    b = HALF_HEIGHT
    total = 0.0
    for k in range(terms):
        n = 2 * k + 1
        sign = -1.0 if k % 2 else 1.0
        nd = float(n)
        wall = 1.0 - math.cosh(nd * math.pi * z / (2.0 * a)) / math.cosh(
            nd * math.pi * b / (2.0 * a)
        )
        total += sign * wall * math.cos(nd * math.pi * y / (2.0 * a)) / nd**3
    return total


def midpoint_average(func: Callable[[float, float], float], ny: int, nz: int) -> float:
    total = 0.0
    for iy in range(ny):
        y = -HALF_WIDTH + (iy + 0.5) * WIDTH / ny
        for iz in range(nz):
            z = -HALF_HEIGHT + (iz + 0.5) * HEIGHT / nz
            total += func(y, z)
    return total / (ny * nz)


def midpoint_integral(func: Callable[[float, float], float], ny: int, nz: int) -> float:
    return midpoint_average(func, ny, nz) * WIDTH * HEIGHT


def wall_max_abs(func: Callable[[float, float], float], samples: int) -> float:
    values: list[float] = []
    for i in range(samples):
        s = -1.0 + 2.0 * i / (samples - 1)
        values.append(abs(func(HALF_WIDTH, s * HALF_HEIGHT)))
        values.append(abs(func(-HALF_WIDTH, s * HALF_HEIGHT)))
        values.append(abs(func(s * HALF_WIDTH, HALF_HEIGHT)))
        values.append(abs(func(s * HALF_WIDTH, -HALF_HEIGHT)))
    return max(values)


def peak_value(func: Callable[[float, float], float], ny: int, nz: int) -> float:
    peak = 0.0
    for iy in range(ny):
        y = -HALF_WIDTH + (iy + 0.5) * WIDTH / ny
        for iz in range(nz):
            z = -HALF_HEIGHT + (iz + 0.5) * HEIGHT / nz
            peak = max(peak, func(y, z))
    peak = max(peak, func(0.0, 0.0))
    return peak


def validate(args: argparse.Namespace) -> tuple[list[dict[str, object]], dict[str, object]]:
    raw_mean = midpoint_average(lambda y, z: poiseuille_raw(y, z, args.terms), args.ny, args.nz)
    profiles: dict[str, Callable[[float, float], float]] = {
        "rect_area_top_hat": top_hat,
        "rect_area_separable_parabolic": separable_parabolic,
        "rect_area_poisseuille_series": lambda y, z: max(
            0.0, poiseuille_raw(y, z, args.terms) / raw_mean
        ),
    }
    rows: list[dict[str, object]] = []
    for name, func in profiles.items():
        area_average = midpoint_average(func, args.ny, args.nz)
        integral = midpoint_integral(func, args.ny, args.nz)
        wall_zero = wall_max_abs(func, args.wall_samples)
        peak = peak_value(func, args.peak_ny, args.peak_nz)
        for time_value in args.times:
            umean = args.u0 * (1.0 + args.pulse_amplitude * math.sin(2.0 * math.pi * time_value / args.pulse_period))
            mass_flow = integral * umean
            expected_mass_flow = AREA * umean
            rows.append(
                {
                    "profile_mode": name,
                    "time": time_value,
                    "area_average": area_average,
                    "area_average_error_fraction": abs(area_average - 1.0),
                    "wall_max_abs": wall_zero,
                    "integrated_profile_area": integral,
                    "analytic_area": AREA,
                    "area_error_fraction": abs(integral - AREA) / AREA,
                    "umean": umean,
                    "mass_flow": mass_flow,
                    "expected_mass_flow": expected_mass_flow,
                    "mass_flow_error_fraction": abs(mass_flow - expected_mass_flow) / expected_mass_flow,
                    "peak_over_mean": peak / area_average if area_average else math.nan,
                    "negative_inlet_velocity": umean < 0.0,
                    "passes": (
                        abs(area_average - 1.0) <= args.average_tolerance
                        and wall_zero <= args.wall_tolerance
                        and abs(mass_flow - expected_mass_flow) / expected_mass_flow <= args.mass_tolerance
                        and umean >= 0.0
                    ),
                }
            )
    summary = {
        "rectangular_profile_validated": all(bool(row["passes"]) for row in rows),
        "profile_count": len(profiles),
        "row_count": len(rows),
        "geometry": {
            "radius": RADIUS,
            "A0": AREA,
            "W": WIDTH,
            "H": HEIGHT,
            "half_W": HALF_WIDTH,
            "half_H": HALF_HEIGHT,
            "hydraulic_diameter": HYDRAULIC_DIAMETER,
            "aspect_ratio_W_over_H": WIDTH / HEIGHT,
        },
        "poisseuille_series": {
            "terms": args.terms,
            "raw_midpoint_mean": raw_mean,
            "alias_note": "The runbook spelling rect_area_poisseuille_series is kept as the canonical mode string; rect_area_poiseuille_series is an accepted source alias.",
        },
        "tolerances": {
            "average": args.average_tolerance,
            "wall": args.wall_tolerance,
            "mass": args.mass_tolerance,
        },
    }
    return rows, summary


def write_definition(path: Path, summary: dict[str, object]) -> None:
    geometry = summary["geometry"]
    poiseuille = summary["poisseuille_series"]
    body = f"""# Rectangular Profile Definition

The rectangular route is an imposed inlet-boundary benchmark, not an
internal-nozzle-flow simulation.

## Geometry

- Official circular radius: `{geometry["radius"]:.15g}`
- Official circular area `A0 = pi*r^2`: `{geometry["A0"]:.15g}`
- Area-matched 2:1 rectangle height `H = sqrt(A0/2)`: `{geometry["H"]:.15g}`
- Area-matched 2:1 rectangle width `W = 2H = sqrt(2A0)`: `{geometry["W"]:.15g}`
- Half-width: `{geometry["half_W"]:.15g}`
- Half-height: `{geometry["half_H"]:.15g}`
- Hydraulic diameter `2WH/(W+H)`: `{geometry["hydraulic_diameter"]:.15g}`

## Profiles

- `rect_area_top_hat`: unit profile inside the rectangle, zero outside.
- `rect_area_separable_parabolic`: `(9/4)*(1-(y/a)^2)*(1-(z/b)^2)` for
  half-width `a` and half-height `b`, normalized analytically to unit area mean.
- `rect_area_poisseuille_series`: truncated rectangular-duct Poiseuille series,
  normalized numerically to unit area mean. The source also accepts the corrected
  spelling alias `rect_area_poiseuille_series`.

The pulse multiplies the requested bulk mean velocity:

`Umean(t) = u0*(1 + pulse_amplitude*sin(2*pi*t/T0))`

The validation used `{poiseuille["terms"]}` odd Poiseuille-series terms and a
raw midpoint mean of `{poiseuille["raw_midpoint_mean"]:.15g}` before
normalization.
"""
    path.write_text(body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ny", type=int, default=600)
    parser.add_argument("--nz", type=int, default=300)
    parser.add_argument("--peak-ny", type=int, default=401)
    parser.add_argument("--peak-nz", type=int, default=201)
    parser.add_argument("--wall-samples", type=int, default=501)
    parser.add_argument("--terms", type=int, default=61)
    parser.add_argument("--u0", type=float, default=1.0)
    parser.add_argument("--pulse-amplitude", type=float, default=0.05)
    parser.add_argument("--pulse-period", type=float, default=0.1)
    parser.add_argument("--times", type=float, nargs="+", default=[0.0, 0.025, 0.05, 0.075])
    parser.add_argument("--average-tolerance", type=float, default=0.005)
    parser.add_argument("--wall-tolerance", type=float, default=1e-10)
    parser.add_argument("--mass-tolerance", type=float, default=0.01)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows, summary = validate(args)
    csv_path = args.output_dir / "profile_validation.csv"
    json_path = args.output_dir / "profile_validation.json"
    definition_path = args.output_dir / "RECTANGULAR_PROFILE_DEFINITION.md"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_definition(definition_path, summary)

    print(f"PROFILE_VALIDATION_CSV={csv_path}")
    print(f"PROFILE_VALIDATION_JSON={json_path}")
    print(f"PROFILE_DEFINITION={definition_path}")
    return 0 if summary["rectangular_profile_validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
