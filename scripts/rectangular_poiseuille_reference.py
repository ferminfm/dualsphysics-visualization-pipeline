#!/usr/bin/env python3
"""Exact laminar rectangular-duct reference and independent Poisson check.

The series solves mu (u_yy + u_zz) = dp/dx with no slip on a full width by
height rectangle. pressure_gradient is the positive quantity -dp/dx. The
utility is deterministic and makes no physical-validation or stationarity
claim.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.fft import dstn, idstn
from numpy.polynomial.legendre import leggauss


CONDUCTANCE_REFERENCE_MODES = 1024


def _odd_modes(count: int) -> np.ndarray:
    if count < 1:
        raise ValueError("mode count must be positive")
    return np.arange(1, 2 * count, 2, dtype=float)


def _cosh_ratio(argument: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Return cosh(argument)/cosh(denominator) without overflow."""
    log_num = np.logaddexp(argument, -argument)
    log_den = np.logaddexp(denominator, -denominator)
    return np.exp(log_num - log_den)


def velocity(
    y: np.ndarray | float,
    z: np.ndarray | float,
    *,
    width: float = 2.0,
    height: float = 1.0,
    pressure_gradient: float = 1.0,
    viscosity: float = 1.0,
    modes: int = 128,
) -> np.ndarray:
    """Evaluate the rapidly convergent exact series."""
    if width <= 0 or height <= 0 or pressure_gradient < 0 or viscosity <= 0:
        raise ValueError("invalid geometry or forcing")
    yy, zz = np.broadcast_arrays(np.asarray(y, dtype=float), np.asarray(z, dtype=float))
    a, b = 0.5 * width, 0.5 * height
    tolerance = 64.0 * np.finfo(float).eps
    if np.any(np.abs(yy) > a * (1.0 + tolerance)) or np.any(np.abs(zz) > b * (1.0 + tolerance)):
        raise ValueError("point lies outside the duct")

    n = _odd_modes(modes)
    k = n * math.pi / (2.0 * b)
    alternating = np.where((np.arange(modes) % 2) == 0, 1.0, -1.0)
    flat_y = yy.ravel()
    flat_z = zz.ravel()
    ratio = _cosh_ratio(k[:, None] * flat_y[None, :], (k * a)[:, None])
    cosine = np.cos(k[:, None] * flat_z[None, :])
    correction = np.sum(
        (alternating / n**3)[:, None] * ratio * cosine,
        axis=0,
    )
    result = pressure_gradient / (2.0 * viscosity) * (
        b * b
        - flat_z * flat_z
        - (32.0 * b * b / math.pi**3) * correction
    )
    result = result.reshape(yy.shape)
    on_wall = np.isclose(np.abs(yy), a, rtol=0.0, atol=2e-14 * max(1.0, a)) | np.isclose(
        np.abs(zz), b, rtol=0.0, atol=2e-14 * max(1.0, b)
    )
    return np.where(on_wall, 0.0, result)


def conductance_factor(width: float = 2.0, height: float = 1.0, modes: int = 128) -> float:
    """Return the bracket in Q = G W H^3 F/(12 mu)."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    ratio = width / height
    n = _odd_modes(modes)
    series = np.sum(np.tanh(0.5 * math.pi * ratio * n) / n**5)
    return float(1.0 - 192.0 * series / (math.pi**5 * ratio))


def reference_metrics(
    *,
    width: float = 2.0,
    height: float = 1.0,
    pressure_gradient: float = 1.0,
    viscosity: float = 1.0,
    modes: int = 128,
    quadrature_order: int = 160,
) -> dict[str, float]:
    """Return integrated profile constants using tensor Gauss quadrature."""
    if quadrature_order < 8:
        raise ValueError("quadrature order must be at least eight")
    nodes, weights = leggauss(quadrature_order)
    y = 0.5 * width * nodes
    z = 0.5 * height * nodes
    wy = 0.5 * width * weights
    wz = 0.5 * height * weights
    yy, zz = np.meshgrid(y, z, indexing="ij")
    values = velocity(
        yy,
        zz,
        width=width,
        height=height,
        pressure_gradient=pressure_gradient,
        viscosity=viscosity,
        modes=modes,
    )
    tensor_weights = wy[:, None] * wz[None, :]
    area = width * height
    q = float(np.sum(tensor_weights * values))
    bulk = q / area
    second = float(np.sum(tensor_weights * values**2))
    third = float(np.sum(tensor_weights * values**3))
    beta = second / (area * bulk**2)
    alpha = third / (area * bulk**3)
    center = float(
        velocity(
            0.0,
            0.0,
            width=width,
            height=height,
            pressure_gradient=pressure_gradient,
            viscosity=viscosity,
            modes=modes,
        )
    )
    # Conductance is a cheap one-dimensional n^-5 sum, so bind the analytic
    # flow-rate check to a high-mode value independently of the more expensive
    # velocity tensor used by the requested profile/quadrature calculation.
    conductance_modes = max(modes, CONDUCTANCE_REFERENCE_MODES)
    conductance = conductance_factor(width, height, modes=conductance_modes)
    analytic_q = (
        pressure_gradient
        * width
        * height**3
        * conductance
        / (12.0 * viscosity)
    )
    dh = 2.0 * width * height / (width + height)
    return {
        "width": width,
        "height": height,
        "aspect_ratio": width / height,
        "area": area,
        "hydraulic_diameter": dh,
        "pressure_gradient": pressure_gradient,
        "viscosity": viscosity,
        "modes": modes,
        "quadrature_order": quadrature_order,
        "conductance_modes": conductance_modes,
        "conductance_factor": conductance,
        "flow_rate": q,
        "analytic_flow_rate": analytic_q,
        "relative_flow_quadrature_error": abs(q - analytic_q) / abs(analytic_q),
        "bulk_velocity": bulk,
        "centerline_velocity": center,
        "centerline_to_bulk": center / bulk,
        "beta": beta,
        "alpha": alpha,
        "momentum_equivalent_velocity": math.sqrt(second / area),
        "momentum_equivalent_to_bulk": math.sqrt(beta),
        # From f_D = (-dp/dx) Dh/(0.5 rho U_b^2) and Re = rho U_b Dh/mu.
        # The Fanning convention is f_F = f_D/4.
        "darcy_f_re": 2.0 * pressure_gradient * dh**2 / (viscosity * bulk),
        "fanning_f_re": 0.5 * pressure_gradient * dh**2 / (viscosity * bulk),
    }


def finite_difference_metrics(short_side_intervals: int) -> dict[str, float]:
    """Independent five-point Dirichlet Poisson solve for the 2:1 duct."""
    n = int(short_side_intervals)
    if n < 8:
        raise ValueError("short-side intervals must be at least eight")
    if n % 2:
        raise ValueError("short-side intervals must be even for composite Simpson integration")
    nx_intervals, nz_intervals = 2 * n, n
    h = 1.0 / n
    rhs = np.ones((nx_intervals - 1, nz_intervals - 1), dtype=float)
    transformed = dstn(rhs, type=1, norm="ortho")
    kx = np.arange(1, nx_intervals, dtype=float)[:, None]
    kz = np.arange(1, nz_intervals, dtype=float)[None, :]
    eigenvalues = 4.0 / h**2 * (
        np.sin(math.pi * kx / (2.0 * nx_intervals)) ** 2
        + np.sin(math.pi * kz / (2.0 * nz_intervals)) ** 2
    )
    solution = idstn(transformed / eigenvalues, type=1, norm="ortho")
    # Integrate the independent nodal Dirichlet solution with tensor-product
    # composite Simpson weights.  Including the exactly zero boundary nodes is
    # essential; a plain interior-node rectangle sum limits the apparent
    # convergence of beta and alpha despite the second-order Poisson solve.
    full = np.zeros((nx_intervals + 1, nz_intervals + 1), dtype=float)
    full[1:-1, 1:-1] = solution
    wy = np.ones(nx_intervals + 1, dtype=float)
    wz = np.ones(nz_intervals + 1, dtype=float)
    wy[1:-1:2] = 4.0
    wy[2:-1:2] = 2.0
    wz[1:-1:2] = 4.0
    wz[2:-1:2] = 2.0
    tensor_weights = wy[:, None] * wz[None, :]
    area = 2.0
    q = float(np.sum(tensor_weights * full) * h**2 / 9.0)
    bulk = q / area
    second = float(np.sum(tensor_weights * full**2) * h**2 / 9.0)
    third = float(np.sum(tensor_weights * full**3) * h**2 / 9.0)
    return {
        "short_side_intervals": n,
        "grid_spacing": h,
        "flow_rate": q,
        "bulk_velocity": bulk,
        "beta": second / (area * bulk**2),
        "alpha": third / (area * bulk**3),
    }


def convergence_study(
    mode_counts: list[int], quadrature_order: int,
) -> list[dict[str, float | int | None]]:
    rows: list[dict[str, float | int | None]] = []
    previous: dict[str, float] | None = None
    for count in mode_counts:
        metrics = reference_metrics(modes=count, quadrature_order=quadrature_order)
        row = {
            "modes": count,
            "flow_rate": metrics["flow_rate"],
            "beta": metrics["beta"],
            "alpha": metrics["alpha"],
            "centerline_to_bulk": metrics["centerline_to_bulk"],
            "delta_beta": None if previous is None else metrics["beta"] - previous["beta"],
            "delta_alpha": None if previous is None else metrics["alpha"] - previous["alpha"],
        }
        rows.append(row)
        previous = metrics
    return rows


def conductance_convergence_study(
    mode_counts: list[int],
) -> list[dict[str, float | int | None]]:
    """Track the inexpensive conductance series independently of velocity modes."""
    rows: list[dict[str, float | int | None]] = []
    previous: float | None = None
    for count in mode_counts:
        factor = conductance_factor(modes=count)
        rows.append({
            "modes": count,
            "conductance_factor": factor,
            "delta": None if previous is None else factor - previous,
        })
        previous = factor
    return rows


def _write_cut(path: Path, coordinate: np.ndarray, values: np.ndarray, coordinate_name: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[coordinate_name, "velocity"])
        writer.writeheader()
        for position, value in zip(coordinate, values):
            writer.writerow({coordinate_name: f"{position:.17g}", "velocity": f"{value:.17g}"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--modes", type=int, default=256)
    parser.add_argument("--quadrature-order", type=int, default=256)
    parser.add_argument("--cut-points", type=int, default=401)
    parser.add_argument("--fd-levels", default="64,128,256,512")
    args = parser.parse_args()

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    mode_counts = sorted(set([32, 64, 128, args.modes]))
    convergence = convergence_study(mode_counts, args.quadrature_order)
    conductance_mode_counts = sorted(set([64, 128, 256, 512, CONDUCTANCE_REFERENCE_MODES]))
    conductance_convergence = conductance_convergence_study(conductance_mode_counts)
    finite_difference = [
        finite_difference_metrics(int(value))
        for value in args.fd_levels.split(",")
        if value.strip()
    ]
    metrics = reference_metrics(modes=args.modes, quadrature_order=args.quadrature_order)
    payload = {
        "schema": "rectangular_poiseuille_reference_v1",
        "equation": "mu*(d2u_dy2+d2u_dz2)=dp_dx; pressure_gradient=-dp_dx>0",
        "boundary_condition": "no_slip_all_four_walls",
        "normalization": "width=2,height=1,pressure_gradient=1,viscosity=1",
        "metrics": metrics,
        "series_convergence": convergence,
        "conductance_series_convergence": conductance_convergence,
        "independent_five_point_poisson": finite_difference,
        "claim_boundary": "mathematical_and_numerical_reference_not_physical_validation",
    }
    (output / "reference.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    y = np.linspace(-1.0, 1.0, args.cut_points)
    z = np.linspace(-0.5, 0.5, args.cut_points)
    _write_cut(output / "long_axis_cut.csv", y, velocity(y, 0.0, modes=args.modes), "y")
    _write_cut(output / "short_axis_cut.csv", z, velocity(0.0, z, modes=args.modes), "z")
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
