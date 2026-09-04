#!/usr/bin/env python3
"""Derive internal-nozzle dimensionless histories from true plane metrics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


VELOCITY_FIELDS = ("area_weighted", "flux_weighted", "momentum_equivalent")


def finite_positive(value: str | float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def dimensionless(*, velocity: float, rho: float, mu: float, sigma: float,
                  dh: float, pressure_drop: float) -> dict[str, float]:
    if velocity <= 0.0:
        raise ValueError("velocity must be positive")
    return {
        "Re_h": rho * velocity * dh / mu,
        "We_h": rho * velocity**2 * dh / sigma,
        "Ca": mu * velocity / sigma,
        "Oh_h": mu / math.sqrt(rho * sigma * dh),
        "Eu": pressure_drop / (rho * velocity**2),
    }


def derive_row(row: dict[str, str], *, rho: float, mu: float, sigma: float,
               dh: float, reference_velocity: float) -> dict[str, object]:
    area = finite_positive(row["liquid_area"], "liquid_area")
    ql = finite_positive(row["Q_l"], "Q_l")
    jk = finite_positive(row["J_k_liquid"], "J_k_liquid")
    pressure_drop = finite_positive(
        row["forcing_to_plane_pressure_drop"], "forcing_to_plane_pressure_drop"
    )
    t = float(row["t"])
    area_weighted = ql / area
    flux_weighted = jk / (rho * ql)
    momentum_equivalent = math.sqrt(jk / (rho * area))
    velocities = {
        "area_weighted": area_weighted,
        "flux_weighted": flux_weighted,
        "momentum_equivalent": momentum_equivalent,
    }
    return {
        "t": t,
        "t_star": t * reference_velocity / dh,
        "plane_label": row["plane_label"],
        "liquid_area": area,
        "Q_l": ql,
        "J_k_liquid": jk,
        "pressure_drop": pressure_drop,
        "velocities": velocities,
        "beta": jk * area / (rho * ql**2),
        "dimensionless": {
            name: dimensionless(
                velocity=value,
                rho=rho,
                mu=mu,
                sigma=sigma,
                dh=dh,
                pressure_drop=pressure_drop,
            )
            for name, value in velocities.items()
        },
        "flow_through_t_star": {
            name: {
                "plenum_2Dh": 2.0 * reference_velocity / value,
                "contraction_3Dh": 3.0 * reference_velocity / value,
                "straight_10Dh": 10.0 * reference_velocity / value,
                "internal_15Dh": 15.0 * reference_velocity / value,
            }
            for name, value in velocities.items()
        },
    }


def audit(path: Path, *, plane_label: str, rho: float, mu: float,
          sigma: float, dh: float, reference_velocity: float) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {
            "t", "plane_label", "liquid_area", "Q_l", "J_k_liquid",
            "forcing_to_plane_pressure_drop",
        }
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        rows = [
            derive_row(
                row,
                rho=rho,
                mu=mu,
                sigma=sigma,
                dh=dh,
                reference_velocity=reference_velocity,
            )
            for row in reader
            if row["plane_label"] == plane_label
        ]
    if not rows:
        raise ValueError(f"no rows for plane_label={plane_label}")
    rows.sort(key=lambda item: float(item["t"]))
    return {
        "schema": "internal_nozzle_dimensionless_audit_v1",
        "input": str(path),
        "plane_label": plane_label,
        "conventions": {
            "rho": rho,
            "mu": mu,
            "sigma": sigma,
            "Dh": dh,
            "reference_velocity": reference_velocity,
            "t_star": "t*reference_velocity/Dh",
            "Re_h": "rho*U*Dh/mu",
            "We_h": "rho*U^2*Dh/sigma",
            "Ca": "mu*U/sigma",
            "Oh_h": "mu/sqrt(rho*sigma*Dh)",
            "Eu": "pressure_drop/(rho*U^2)",
        },
        "sample_count": len(rows),
        "first": rows[0],
        "last": rows[-1],
        "series": rows,
        "physical_mapping_status": "unresolved",
        "claim_boundary": "native_code_unit_regime_not_SI_dynamic_similarity",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hydraulic-csv", type=Path, required=True)
    parser.add_argument("--plane-label", default="geometric_nozzle_exit")
    parser.add_argument("--rho", type=float, default=1.0)
    parser.add_argument("--mu", type=float, default=1.0)
    parser.add_argument("--sigma", type=float, default=3e-5)
    parser.add_argument("--dh", type=float, required=True)
    parser.add_argument("--reference-velocity", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rho = finite_positive(args.rho, "rho")
    mu = finite_positive(args.mu, "mu")
    sigma = finite_positive(args.sigma, "sigma")
    dh = finite_positive(args.dh, "dh")
    reference_velocity = finite_positive(args.reference_velocity, "reference_velocity")
    result = audit(
        args.hydraulic_csv,
        plane_label=args.plane_label,
        rho=rho,
        mu=mu,
        sigma=sigma,
        dh=dh,
        reference_velocity=reference_velocity,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sample_count": result["sample_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
