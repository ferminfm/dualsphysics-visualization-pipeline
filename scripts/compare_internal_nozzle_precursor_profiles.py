#!/usr/bin/env python3
"""Compare terminal precursor plane profiles with the exact duct solution.

The utility is deliberately a reducer, not an acceptance classifier.  It
binds one converged terminal precursor state to its full leaf-cell export,
reconstructs the same half-open plane slabs and aperture-overlap weights used
by the Basilisk producer, and reports dimensionless mismatch inputs.  It does
not invent a scientific threshold for whether a developing/contraction-plane
profile is sufficiently Poiseuille-like.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
from types import ModuleType
from typing import Iterable, NamedTuple, Sequence

import numpy as np
from numpy.polynomial.legendre import leggauss


SCHEMA = "internal_nozzle_precursor_profile_comparison_v1"
PRODUCER_SCHEMA = "internal_nozzle_precursor_unsealed_export_v2"
CONVERGENCE_SCHEMA = "internal_nozzle_precursor_convergence_v1"
CHECKPOINT_SCHEMA = "internal_nozzle_precursor_checkpoint_v2"
GEOMETRY_FINGERPRINT = (
    "w2-area-pi-over-144-plenum2dh-contraction3dh-straight10dh-smoothstep-v1"
)
REFERENCE_SCHEMA = "rectangular_poiseuille_reference_v1"
RUN_SCHEMA = "internal_nozzle_precursor_run_v1"
SCHEDULE_VERSION = "internal_nozzle_precursor_schedule_v1"
SCHEDULE_SHA256 = (
    "3598151fc5833c68d778830532e9c90e5d451f0c08b44e5da95a11b2952dcd11"
)
CHECKPOINT_KEYS = {
    "schema", "case_id", "geometry_fingerprint", "source_commit",
    "source_sha256", "maxlevel", "pressure_forcing", "density_liquid",
    "viscosity_liquid", "t", "t_star", "i", "solver_dt",
    "solver_dtmax", "timestep_previous", "previous_profile_available",
    "prediction_closure_schema", "prediction_closure_state",
}
CELL_FIELDS = (
    "source_cell_id", "x", "y", "z", "Delta", "cs", "ux", "uy", "uz", "p",
)
PLANE_HISTORY_FIELDS = (
    "case_id", "t", "t_star", "i", "plane_label", "plane_dh", "area", "Q_l",
    "mdot_l", "J_k", "pressure_mean", "beta", "alpha",
)
PLANES = (
    ("upstream_plenum", 0.5),
    ("contraction_entry", 2.0),
    ("straight_entry", 5.0),
    ("mid_straight", 10.0),
    ("near_exit", 14.5),
)
INTERNAL_LENGTH_DH = 15.0
PLENUM_LENGTH_DH = 2.0
CONTRACTION_LENGTH_DH = 3.0
PLENUM_SCALE = 3.0


class Cell(NamedTuple):
    source_cell_id: int
    x: float
    y: float
    z: float
    delta: float
    cs: float
    ux: float
    uy: float
    uz: float
    pressure: float


class Rectangle(NamedTuple):
    cell: Cell
    y0: float
    y1: float
    z0: float
    z1: float
    area: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular_file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"{label} must be a nonempty regular file")
    return resolved


def checked_file(path: Path, expected_sha256: str, label: str) -> Path:
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError(f"{label} expected SHA-256 is not lowercase hexadecimal")
    resolved = regular_file(path, label)
    if sha256_file(resolved) != expected_sha256:
        raise ValueError(f"{label} SHA-256 mismatch")
    return resolved


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(
            regular_file(path, label).read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid {label} JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def finite(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is not numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} is not finite")
    return number


def exact_int(value: object, label: str) -> int:
    number = finite(value, label)
    integer = int(number)
    if number != integer:
        raise ValueError(f"{label} is not an integer")
    return integer


def canonical_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} is not lowercase SHA-256 hexadecimal")
    return value


def close_number(left: object, right: object, label: str) -> None:
    lhs = finite(left, f"{label} left")
    rhs = finite(right, f"{label} right")
    if not math.isclose(lhs, rhs, rel_tol=2e-11, abs_tol=1e-14):
        raise ValueError(f"{label} mismatch: {lhs:.17g} != {rhs:.17g}")


def identity_error(left: float, right: float) -> float:
    if left == right:
        return 0.0
    return abs(left - right) / max(abs(left), abs(right), 1e-300)


def read_exact_csv(path: Path, fields: tuple[str, ...], label: str) -> list[dict[str, str]]:
    resolved = regular_file(path, label)
    with resolved.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or tuple(reader.fieldnames) != fields:
            raise ValueError(f"{label} has an incompatible exact header")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{label} has duplicate columns")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{label} has no data rows")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{label} contains a malformed row")
    return rows


def read_sidecar(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, line in enumerate(
        regular_file(path, "checkpoint sidecar").read_text(encoding="utf-8").splitlines(), 1
    ):
        if "=" not in line:
            raise ValueError(f"checkpoint sidecar line {number} is malformed")
        key, value = line.split("=", 1)
        if not key or key in values:
            raise ValueError(f"checkpoint sidecar line {number} has duplicate/empty key")
        values[key] = value
    return values


def canonical_local_member(metadata_path: Path, value: object, name: str, label: str) -> Path:
    if value != name:
        raise ValueError(f"{label} must be the canonical member {name}")
    candidate = metadata_path.parent / name
    if candidate.parent.resolve(strict=True) != metadata_path.parent.resolve(strict=True):
        raise ValueError(f"{label} escapes the producer directory")
    return regular_file(candidate, label)


def load_reference(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("bound_rectangular_poiseuille_reference", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load exact-reference module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "velocity", None)) or not callable(
        getattr(module, "reference_metrics", None)
    ):
        raise ValueError("exact-reference module lacks the stable velocity/metrics API")
    return module


def verified_file_record(
    record: object, expected_path: Path, label: str,
) -> tuple[Path, str]:
    if not isinstance(record, dict):
        raise ValueError(f"{label} provenance is missing")
    resolved_value = record.get("resolved_path")
    digest = canonical_sha256(record.get("sha256"), f"{label} SHA-256")
    if not isinstance(resolved_value, str) or not resolved_value:
        raise ValueError(f"{label} resolved path is missing")
    resolved = regular_file(Path(resolved_value), label)
    expected = regular_file(expected_path, f"expected {label}")
    if resolved != expected:
        raise ValueError(f"{label} provenance resolves to the wrong file")
    if sha256_file(resolved) != digest:
        raise ValueError(f"{label} changed after convergence classification")
    return resolved, digest


def verify_reference_artifact(
    report: dict[str, object], reference: ModuleType, *, modes: int,
    quadrature_order: int,
) -> None:
    if report.get("schema") != REFERENCE_SCHEMA:
        raise ValueError("Task 02 reference artifact has an incompatible schema")
    expected_strings = {
        "equation": "mu*(d2u_dy2+d2u_dz2)=dp_dx; pressure_gradient=-dp_dx>0",
        "boundary_condition": "no_slip_all_four_walls",
        "normalization": "width=2,height=1,pressure_gradient=1,viscosity=1",
        "claim_boundary": "mathematical_and_numerical_reference_not_physical_validation",
    }
    for key, expected in expected_strings.items():
        if report.get(key) != expected:
            raise ValueError(f"Task 02 reference artifact mismatch: {key}")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("Task 02 reference artifact lacks metrics")
    exact_settings = {
        "width": 2.0,
        "height": 1.0,
        "aspect_ratio": 2.0,
        "pressure_gradient": 1.0,
        "viscosity": 1.0,
        "modes": modes,
        "quadrature_order": quadrature_order,
    }
    for key, expected in exact_settings.items():
        close_number(metrics.get(key), expected, f"reference setting {key}")
    recomputed = reference.reference_metrics(
        width=2.0, height=1.0, pressure_gradient=1.0, viscosity=1.0,
        modes=modes, quadrature_order=quadrature_order,
    )
    metric_names = (
        "flow_rate", "analytic_flow_rate", "bulk_velocity",
        "centerline_velocity", "centerline_to_bulk", "beta", "alpha",
        "momentum_equivalent_velocity", "momentum_equivalent_to_bulk",
    )
    for name in metric_names:
        close_number(metrics.get(name), recomputed.get(name), f"reference metric {name}")
    convergence = report.get("series_convergence")
    if not isinstance(convergence, list) or not convergence or not all(
        isinstance(row, dict) for row in convergence
    ):
        raise ValueError("Task 02 reference artifact lacks series-convergence evidence")
    matching_rows = [row for row in convergence if exact_int(row.get("modes"), "series modes") == modes]
    if len(matching_rows) != 1:
        raise ValueError("Task 02 reference artifact does not uniquely bind selected modes")
    selected = matching_rows[0]
    for name in ("flow_rate", "beta", "alpha", "centerline_to_bulk"):
        close_number(selected.get(name), metrics.get(name), f"series/metric {name}")
    poisson = report.get("independent_five_point_poisson")
    if not isinstance(poisson, list) or len(poisson) < 2 or not all(
        isinstance(row, dict) for row in poisson
    ):
        raise ValueError("Task 02 reference artifact lacks independent Poisson evidence")
    intervals = [
        exact_int(row.get("short_side_intervals"), "Poisson short-side intervals")
        for row in poisson
    ]
    if intervals != sorted(set(intervals)) or any(value < 8 for value in intervals):
        raise ValueError("Task 02 Poisson resolutions are malformed")
    for row in poisson:
        for name in ("flow_rate", "bulk_velocity", "beta", "alpha"):
            finite(row.get(name), f"Poisson {name}")


def smoothstep(value: float) -> float:
    bounded = min(1.0, max(0.0, value))
    return bounded * bounded * (3.0 - 2.0 * bounded)


def local_dimensions(plane_dh: float, hydraulic_diameter: float) -> tuple[float, float]:
    base_height = 0.75 * hydraulic_diameter
    base_width = 1.5 * hydraulic_diameter
    if plane_dh <= PLENUM_LENGTH_DH:
        scale = PLENUM_SCALE
    elif plane_dh <= PLENUM_LENGTH_DH + CONTRACTION_LENGTH_DH:
        blend = smoothstep((plane_dh - PLENUM_LENGTH_DH) / CONTRACTION_LENGTH_DH)
        scale = (1.0 - blend) * PLENUM_SCALE + blend
    else:
        scale = 1.0
    return scale * base_width, scale * base_height


def parse_cells(rows: Iterable[dict[str, str]]) -> list[Cell]:
    cells: list[Cell] = []
    identifiers: set[int] = set()
    spatial_keys: set[tuple[str, str, str, str]] = set()
    for number, row in enumerate(rows, 2):
        identifier = exact_int(row["source_cell_id"], f"cell row {number}:source_cell_id")
        values = {
            name: finite(row[name], f"cell row {number}:{name}")
            for name in ("x", "y", "z", "Delta", "cs", "ux", "uy", "uz", "p")
        }
        if identifier < 0 or identifier in identifiers:
            raise ValueError(f"cell row {number} has duplicate/negative source_cell_id")
        if values["Delta"] <= 0.0 or not 0.0 < values["cs"] <= 1.0:
            raise ValueError(f"cell row {number} has invalid Delta/cs")
        spatial_key = tuple(float(values[name]).hex() for name in ("x", "y", "z", "Delta"))
        if spatial_key in spatial_keys:
            raise ValueError(f"cell row {number} duplicates a leaf geometry")
        identifiers.add(identifier)
        spatial_keys.add(spatial_key)
        cells.append(
            Cell(identifier, values["x"], values["y"], values["z"], values["Delta"],
                 values["cs"], values["ux"], values["uy"], values["uz"], values["p"])
        )
    if identifiers != set(range(len(cells))):
        raise ValueError("source_cell_id values are not the canonical contiguous enumeration")
    return cells


def clipped_rectangles(
    cells: Sequence[Cell], plane_x: float, width: float, height: float,
) -> list[Rectangle]:
    half_w, half_h = 0.5 * width, 0.5 * height
    rectangles: list[Rectangle] = []
    for cell in cells:
        if cell.x - 0.5 * cell.delta <= plane_x < cell.x + 0.5 * cell.delta:
            y0, y1 = max(cell.y - 0.5 * cell.delta, -half_w), min(
                cell.y + 0.5 * cell.delta, half_w
            )
            z0, z1 = max(cell.z - 0.5 * cell.delta, -half_h), min(
                cell.z + 0.5 * cell.delta, half_h
            )
            if y1 > y0 and z1 > z0:
                rectangles.append(Rectangle(cell, y0, y1, z0, z1, (y1 - y0) * (z1 - z0)))
    if not rectangles:
        raise ValueError("no precursor cells intersect a declared plane")
    return rectangles


def intersection_area(left: Rectangle, right: Rectangle, mirror: str = "none") -> float:
    if mirror == "y":
        ry0, ry1, rz0, rz1 = -right.y1, -right.y0, right.z0, right.z1
    elif mirror == "z":
        ry0, ry1, rz0, rz1 = right.y0, right.y1, -right.z1, -right.z0
    elif mirror == "yz":
        ry0, ry1, rz0, rz1 = -right.y1, -right.y0, -right.z1, -right.z0
    elif mirror == "none":
        ry0, ry1, rz0, rz1 = right.y0, right.y1, right.z0, right.z1
    else:
        raise ValueError("unknown mirror")
    dy = min(left.y1, ry1) - max(left.y0, ry0)
    dz = min(left.z1, rz1) - max(left.z0, rz0)
    return max(0.0, dy) * max(0.0, dz)


def verify_partition(rectangles: Sequence[Rectangle], expected_area: float) -> dict[str, float]:
    summed = math.fsum(item.area for item in rectangles)
    overlap = 0.0
    ordered = sorted(rectangles, key=lambda item: item.y0)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if right.y0 >= left.y1:
                break
            overlap += intersection_area(left, right)
    tolerance = max(1e-14, 2e-11 * expected_area)
    if overlap > tolerance:
        raise ValueError(f"plane leaf projection overlaps by {overlap:.17g}")
    if abs(summed - expected_area) > tolerance:
        raise ValueError(
            f"plane leaf projection does not tile aperture: {summed:.17g} != {expected_area:.17g}"
        )
    return {
        "summed_aperture_overlap_area": summed,
        "expected_aperture_area": expected_area,
        "absolute_area_closure_error": abs(summed - expected_area),
        "detected_overlap_area": overlap,
    }


def symmetry_metrics(rectangles: Sequence[Rectangle], bulk: float, mirror: str) -> dict[str, float]:
    numerator = 0.0
    coverage = 0.0
    denominator = math.fsum(item.area * item.cell.ux * item.cell.ux for item in rectangles)
    maximum = 0.0
    for left in rectangles:
        left_coverage = 0.0
        for right in rectangles:
            area = intersection_area(left, right, mirror)
            if area:
                difference = left.cell.ux - right.cell.ux
                numerator += area * difference * difference
                left_coverage += area
                maximum = max(maximum, abs(difference))
        if abs(left_coverage - left.area) > max(1e-14, 2e-11 * left.area):
            raise ValueError(f"{mirror}-mirror lookup does not cover a leaf rectangle")
        coverage += left_coverage
    return {
        "normalized_weighted_l2": math.sqrt(numerator / max(denominator, 1e-300)),
        "normalized_linf": maximum / abs(bulk),
        "covered_area": coverage,
    }


def reference_cell_average(
    reference: ModuleType, rectangle: Rectangle, *, width: float, height: float,
    modes: int, order: int,
) -> float:
    nodes, weights = leggauss(order)
    ys = 0.5 * (rectangle.y1 - rectangle.y0) * nodes + 0.5 * (rectangle.y1 + rectangle.y0)
    zs = 0.5 * (rectangle.z1 - rectangle.z0) * nodes + 0.5 * (rectangle.z1 + rectangle.z0)
    yy, zz = np.meshgrid(ys, zs, indexing="ij")
    values = reference.velocity(
        yy, zz, width=width, height=height, pressure_gradient=1.0,
        viscosity=1.0, modes=modes,
    )
    return float(np.sum(weights[:, None] * weights[None, :] * values) / 4.0)


def wall_metrics(
    samples: Sequence[dict[str, object]], *, width: float, height: float, bulk: float,
) -> dict[str, object]:
    limits = {
        "negative_y": -0.5 * width,
        "positive_y": 0.5 * width,
        "negative_z": -0.5 * height,
        "positive_z": 0.5 * height,
    }
    grouped: dict[str, list[dict[str, object]]] = {name: [] for name in limits}
    tolerance = max(1e-14, 2e-12 * max(width, height))
    for sample in samples:
        bounds = sample["bounds"]
        assert isinstance(bounds, tuple)
        y0, y1, z0, z1 = bounds
        if abs(y0 - limits["negative_y"]) <= tolerance:
            grouped["negative_y"].append(sample)
        if abs(y1 - limits["positive_y"]) <= tolerance:
            grouped["positive_y"].append(sample)
        if abs(z0 - limits["negative_z"]) <= tolerance:
            grouped["negative_z"].append(sample)
        if abs(z1 - limits["positive_z"]) <= tolerance:
            grouped["positive_z"].append(sample)
    result: dict[str, object] = {}
    for wall, entries in grouped.items():
        if not entries:
            raise ValueError(f"no wall-adjacent numerical cells on {wall}")
        weights = [float(item["area_weight"]) for item in entries]
        area = math.fsum(weights)
        numerical = [abs(float(item["numerical_ux"]) / bulk) for item in entries]
        analytic = [abs(float(item["reference_normalized"])) for item in entries]
        result[wall] = {
            "cell_count": len(entries),
            "area_weighted_mean_abs_numerical_u_over_bulk": math.fsum(
                w * u for w, u in zip(weights, numerical)
            ) / area,
            "area_weighted_mean_abs_reference_cell_average_over_bulk": math.fsum(
                w * u for w, u in zip(weights, analytic)
            ) / area,
            "maximum_abs_numerical_u_over_bulk": max(numerical),
            "interpretation": (
                "wall-adjacent cell-average resolution check; embedded no-slip is established "
                "by source BC evidence, not by treating a cell-center value as a wall value"
            ),
        }
    return result


def analyze_plane(
    cells: Sequence[Cell], history: dict[str, object], reference: ModuleType,
    *, plane_label: str, plane_dh: float, hydraulic_diameter: float,
    density: float, modes: int, reference_quadrature_order: int,
    cell_quadrature_order: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    width, height = local_dimensions(plane_dh, hydraulic_diameter)
    area = width * height
    plane_x = plane_dh * hydraulic_diameter
    rectangles = clipped_rectangles(cells, plane_x, width, height)
    partition = verify_partition(rectangles, area)
    flow = math.fsum(item.area * item.cell.ux for item in rectangles)
    if not flow > 0.0:
        raise ValueError(f"{plane_label} has non-positive reconstructed flow")
    bulk = flow / area
    second = math.fsum(item.area * item.cell.ux**2 for item in rectangles)
    third = math.fsum(item.area * item.cell.ux**3 for item in rectangles)
    pressure_mean = math.fsum(
        item.area * item.cell.pressure for item in rectangles
    ) / area
    beta = second * area / (flow * flow)
    alpha = third * area * area / (flow * flow * flow)
    crossflow_rms = math.sqrt(
        math.fsum(item.area * (item.cell.uy**2 + item.cell.uz**2) for item in rectangles) / area
    )
    exact = reference.reference_metrics(
        width=width, height=height, pressure_gradient=1.0, viscosity=1.0,
        modes=modes, quadrature_order=reference_quadrature_order,
    )
    reference_bulk = finite(exact["bulk_velocity"], "reference bulk velocity")
    if not reference_bulk > 0.0:
        raise ValueError("exact reference has non-positive bulk velocity")
    sample_rows: list[dict[str, object]] = []
    numerator = 0.0
    denominator = 0.0
    maximum = 0.0
    discrete_reference_flow = 0.0
    for rectangle in rectangles:
        average = reference_cell_average(
            reference, rectangle, width=width, height=height, modes=modes,
            order=cell_quadrature_order,
        )
        reference_normalized = average / reference_bulk
        numerical_normalized = rectangle.cell.ux / bulk
        difference = numerical_normalized - reference_normalized
        numerator += rectangle.area * difference * difference
        denominator += rectangle.area * reference_normalized * reference_normalized
        maximum = max(maximum, abs(difference))
        discrete_reference_flow += rectangle.area * average
        sample_rows.append({
            "plane_label": plane_label,
            "plane_dh": plane_dh,
            "plane_x": plane_x,
            "source_cell_id": rectangle.cell.source_cell_id,
            "x": rectangle.cell.x,
            "y": rectangle.cell.y,
            "z": rectangle.cell.z,
            "Delta": rectangle.cell.delta,
            "cs": rectangle.cell.cs,
            "area_weight": rectangle.area,
            "numerical_ux": rectangle.cell.ux,
            "numerical_uy": rectangle.cell.uy,
            "numerical_uz": rectangle.cell.uz,
            "numerical_u_over_bulk": numerical_normalized,
            "reference_cell_average": average,
            "reference_normalized": reference_normalized,
            "normalized_difference": difference,
            "bounds": (rectangle.y0, rectangle.y1, rectangle.z0, rectangle.z1),
        })
    reconstructed = {
        "area": area,
        "Q_l": flow,
        "mdot_l": density * flow,
        "J_k": density * second,
        "pressure_mean": pressure_mean,
        "beta": beta,
        "alpha": alpha,
    }
    history_values = {
        key: finite(history[key], f"{plane_label} history {key}")
        for key in reconstructed
    }
    identity_errors = {
        key: identity_error(value, history_values[key])
        for key, value in reconstructed.items()
    }
    for key, value in reconstructed.items():
        close_number(value, history_values[key], f"{plane_label} reconstructed {key}")
    wall_points = np.linspace(-0.5, 0.5, 17)
    reference_wall_values = np.concatenate((
        np.asarray(reference.velocity(-0.5 * width, wall_points * height, width=width,
                                      height=height, modes=modes)).ravel(),
        np.asarray(reference.velocity(0.5 * width, wall_points * height, width=width,
                                      height=height, modes=modes)).ravel(),
        np.asarray(reference.velocity(wall_points * width, -0.5 * height, width=width,
                                      height=height, modes=modes)).ravel(),
        np.asarray(reference.velocity(wall_points * width, 0.5 * height, width=width,
                                      height=height, modes=modes)).ravel(),
    ))
    reference_no_slip_max = float(np.max(np.abs(reference_wall_values)))
    if reference_no_slip_max > 2e-13:
        raise ValueError("exact-reference wall no-slip check failed")
    result = {
        "plane_label": plane_label,
        "plane_dh": plane_dh,
        "plane_x": plane_x,
        "width": width,
        "height": height,
        "area": area,
        "cell_count": len(rectangles),
        "partition": partition,
        "numerical": {
            "Q_l_reconstructed": flow,
            "Q_l_terminal_history": history_values["Q_l"],
            "mdot_l_reconstructed": reconstructed["mdot_l"],
            "J_k_reconstructed": reconstructed["J_k"],
            "pressure_mean_reconstructed": pressure_mean,
            "terminal_history_identity_errors": identity_errors,
            "bulk_velocity": bulk,
            "beta": beta,
            "alpha": alpha,
            "crossflow_rms_over_bulk": crossflow_rms / abs(bulk),
        },
        "exact_reference": {
            "bulk_velocity_for_unit_pressure_gradient": reference_bulk,
            "beta": finite(exact["beta"], "reference beta"),
            "alpha": finite(exact["alpha"], "reference alpha"),
            "centerline_to_bulk": finite(exact["centerline_to_bulk"], "reference centerline ratio"),
            "discrete_leaf_quadrature_bulk_relative_error": abs(
                discrete_reference_flow / area - reference_bulk
            ) / reference_bulk,
            "wall_velocity_max_abs": reference_no_slip_max,
        },
        "profile_comparison": {
            "bulk_normalized_weighted_l2": math.sqrt(numerator / max(denominator, 1e-300)),
            "bulk_normalized_linf": maximum,
            "beta_relative_difference": abs(beta - float(exact["beta"])) / abs(float(exact["beta"])),
            "alpha_relative_difference": abs(alpha - float(exact["alpha"])) / abs(float(exact["alpha"])),
        },
        "symmetry": {
            mirror: symmetry_metrics(rectangles, bulk, mirror) for mirror in ("y", "z", "yz")
        },
        "wall_adjacent": wall_metrics(sample_rows, width=width, height=height, bulk=bulk),
        "classification_input_only": True,
    }
    return result, sample_rows


def provenance_record(path: Path) -> dict[str, object]:
    resolved = regular_file(path, "provenance input")
    return {
        "path": str(path),
        "resolved_path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def verify_convergence_binding(
    convergence: dict[str, object], producer: dict[str, object],
    producer_path: Path, canonical_history: Path, sidecar: Path,
    checkpoint: Path, closure: Path, *, expected_source_commit: str,
    expected_source_sha256: str,
) -> tuple[dict[str, object], dict[str, str]]:
    case_id = producer["case_id"]
    if (
        convergence.get("schema") != CONVERGENCE_SCHEMA
        or convergence.get("pass") is not True
        or convergence.get("classification") != "precursor_converged"
        or convergence.get("case_id") != case_id
        or convergence.get("failures") != []
    ):
        raise ValueError("comparison requires one internally consistent passing convergence report")
    metrics = convergence.get("metrics")
    auxiliary = convergence.get("auxiliary")
    if (
        not isinstance(metrics, dict)
        or set(metrics) != {"Q_l", "J_k", "pressure_drop"}
        or any(not isinstance(item, dict) or item.get("pass") is not True
               for item in metrics.values())
        or not isinstance(auxiliary, dict)
        or not isinstance(auxiliary.get("tests"), dict)
        or not auxiliary["tests"]
        or any(value is not True for value in auxiliary["tests"].values())
    ):
        raise ValueError("convergence report pass projection is incomplete or inconsistent")
    inputs = convergence.get("inputs")
    if not isinstance(inputs, list) or not inputs or not isinstance(inputs[-1], dict):
        raise ValueError("convergence report lacks final input provenance")
    final = inputs[-1]
    history_path, history_hash = verified_file_record(
        final.get("history"), canonical_history, "convergence final history"
    )
    contract_path, contract_hash = verified_file_record(
        final.get("run_contract"), producer_path.parent / "run_contract.json",
        "convergence final run contract",
    )
    contract = load_json(contract_path, "final run contract")
    expected_contract = {
        "schema": RUN_SCHEMA,
        "case_id": case_id,
        "geometry_fingerprint": GEOMETRY_FINGERPRINT,
        "source_commit": expected_source_commit,
        "source_sha256": expected_source_sha256,
    }
    for key, expected in expected_contract.items():
        if contract.get(key) != expected:
            raise ValueError(f"final run contract mismatch: {key}")
    for key in (
        "pressure_forcing", "density_liquid", "viscosity_liquid",
        "delta_min_Dh",
    ):
        close_number(contract.get(key), producer.get(key), f"producer/contract {key}")
    if exact_int(contract.get("maxlevel"), "contract maxlevel") != exact_int(
        producer.get("maxlevel"), "producer maxlevel"
    ):
        raise ValueError("producer/contract maxlevel mismatch")
    sidecar_values = read_sidecar(sidecar)
    if exact_int(sidecar_values.get("maxlevel"), "sidecar maxlevel") != exact_int(
        contract.get("maxlevel"), "contract maxlevel"
    ):
        raise ValueError("sidecar/contract maxlevel mismatch")
    for key in ("pressure_forcing", "density_liquid", "viscosity_liquid"):
        close_number(sidecar_values.get(key), contract.get(key), f"sidecar/contract {key}")
    terminal_checkpoint = final.get("terminal_checkpoint")
    if not isinstance(terminal_checkpoint, dict):
        raise ValueError("convergence report lacks terminal-checkpoint provenance")
    _, dump_hash = verified_file_record(
        terminal_checkpoint.get("dump"), checkpoint, "terminal precursor checkpoint"
    )
    _, sidecar_hash = verified_file_record(
        terminal_checkpoint.get("metadata"), sidecar, "terminal checkpoint sidecar"
    )
    _, closure_hash = verified_file_record(
        terminal_checkpoint.get("prediction_closure"), closure,
        "terminal prediction closure",
    )
    identity = terminal_checkpoint.get("validated_identity")
    if not isinstance(identity, dict):
        raise ValueError("terminal checkpoint lacks validated identity")
    expected_identity = {
        "case_id": case_id,
        "source_commit": expected_source_commit,
        "source_sha256": expected_source_sha256,
        "schedule_version": SCHEDULE_VERSION,
        "schedule_sha256": SCHEDULE_SHA256,
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            raise ValueError(f"terminal checkpoint identity mismatch: {key}")
    return contract, {
        "history": history_hash,
        "run_contract": contract_hash,
        "checkpoint": dump_hash,
        "sidecar": sidecar_hash,
        "closure": closure_hash,
        "history_path": str(history_path),
        "run_contract_path": str(contract_path),
    }


def terminal_plane_rows(
    rows: Sequence[dict[str, str]], *, case_id: str, terminal_t: float,
    terminal_t_star: float, terminal_i: int,
) -> dict[str, dict[str, object]]:
    expected_planes = dict(PLANES)
    terminal: dict[str, dict[str, object]] = {}
    seen: set[tuple[str, str, int, str]] = set()
    for number, row in enumerate(rows, 2):
        if row["case_id"] != case_id:
            raise ValueError(f"plane row {number} has the wrong case_id")
        label = row["plane_label"]
        if label not in expected_planes:
            raise ValueError(f"plane row {number} has an unknown plane label")
        plane_dh = finite(row["plane_dh"], f"plane row {number}:plane_dh")
        if plane_dh != expected_planes[label]:
            raise ValueError(f"plane row {number} has the wrong plane coordinate")
        row_t = finite(row["t"], f"plane row {number}:t")
        row_t_star = finite(row["t_star"], f"plane row {number}:t_star")
        row_i = exact_int(row["i"], f"plane row {number}:i")
        for key in ("area", "Q_l", "mdot_l", "J_k", "pressure_mean", "beta", "alpha"):
            finite(row[key], f"plane row {number}:{key}")
        key = (float(row_t).hex(), float(row_t_star).hex(), row_i, label)
        if key in seen:
            raise ValueError(f"duplicate plane-history identity at row {number}")
        seen.add(key)
        if row_t == terminal_t and row_t_star == terminal_t_star and row_i == terminal_i:
            terminal[label] = dict(row)
    if set(terminal) != set(expected_planes):
        raise ValueError("terminal plane history does not contain exactly the declared planes")
    return terminal


def analyze(
    *, producer_metadata: Path, convergence_report: Path, plane_history: Path,
    reference_script: Path, reference_report: Path, expected_source_commit: str,
    expected_source_sha256: str,
    expected_producer_sha256: str, expected_cells_sha256: str,
    expected_plane_history_sha256: str, expected_convergence_sha256: str,
    expected_reference_sha256: str, expected_reference_report_sha256: str,
    modes: int = 256,
    reference_quadrature_order: int = 256, cell_quadrature_order: int = 8,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if len(expected_source_commit) != 40 or any(
        c not in "0123456789abcdef" for c in expected_source_commit
    ):
        raise ValueError("expected source commit must be lowercase SHA-1 hexadecimal")
    expected_source_sha256 = canonical_sha256(
        expected_source_sha256, "expected source-bundle SHA-256"
    )
    if modes < 32 or reference_quadrature_order < 32 or cell_quadrature_order < 2:
        raise ValueError("reference resolution is below the deterministic minimum")
    producer_path = checked_file(
        producer_metadata, expected_producer_sha256, "producer metadata"
    )
    convergence_path = checked_file(
        convergence_report, expected_convergence_sha256, "convergence report"
    )
    history_path = checked_file(
        plane_history, expected_plane_history_sha256, "plane history"
    )
    reference_path = checked_file(
        reference_script, expected_reference_sha256, "exact-reference script"
    )
    reference_report_path = checked_file(
        reference_report, expected_reference_report_sha256,
        "Task 02 reference artifact",
    )
    producer = load_json(producer_path, "producer metadata")
    convergence = load_json(convergence_path, "convergence report")
    reference_artifact = load_json(reference_report_path, "Task 02 reference artifact")
    expected_scalars = {
        "schema": PRODUCER_SCHEMA,
        "geometry_fingerprint": GEOMETRY_FINGERPRINT,
        "source_commit": expected_source_commit,
        "source_sha256": expected_source_sha256,
        "field_state": "post_projection_terminal_native_checkpoint",
    }
    for key, value in expected_scalars.items():
        if producer.get(key) != value:
            raise ValueError(f"producer metadata mismatch: {key}")
    case_id = producer.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("producer case_id is missing")
    cells_path = canonical_local_member(
        producer_path, producer.get("cells_file"), "precursor-transfer-cells.csv", "cell export"
    )
    checked_file(cells_path, expected_cells_sha256, "cell export")
    if history_path.parent != producer_path.parent or history_path.name != "precursor_plane_history.csv":
        raise ValueError("plane history is not the canonical producer-directory member")
    canonical_history = canonical_local_member(
        producer_path, producer.get("history_file"), "precursor_history.csv", "precursor history"
    )
    sidecar = canonical_local_member(
        producer_path, producer.get("checkpoint_metadata_file"),
        "precursor-final.dump.meta", "checkpoint sidecar",
    )
    checkpoint = canonical_local_member(
        producer_path, producer.get("checkpoint_file"),
        "precursor-final.dump", "precursor checkpoint",
    )
    closure = canonical_local_member(
        producer_path, producer.get("prediction_closure_file"),
        "precursor-final.dump.prediction-closure-v4", "prediction closure",
    )
    sidecar_values = read_sidecar(sidecar)
    if set(sidecar_values) != CHECKPOINT_KEYS:
        raise ValueError("checkpoint sidecar has an incompatible exact key set")
    if (
        sidecar_values.get("schema") != CHECKPOINT_SCHEMA
        or sidecar_values.get("case_id") != case_id
        or sidecar_values.get("geometry_fingerprint") != GEOMETRY_FINGERPRINT
        or sidecar_values.get("source_commit") != expected_source_commit
        or sidecar_values.get("source_sha256") != expected_source_sha256
        or sidecar_values.get("prediction_closure_schema")
        != "internal_nozzle_prediction_closure_v4"
        or sidecar_values.get("prediction_closure_state") != closure.name
    ):
        raise ValueError("checkpoint sidecar identity does not match producer")
    terminal_t = finite(sidecar_values.get("t"), "checkpoint t")
    terminal_t_star = finite(sidecar_values.get("t_star"), "checkpoint t_star")
    terminal_i = exact_int(sidecar_values.get("i"), "checkpoint iteration")
    if (
        terminal_t != finite(producer.get("t"), "producer t")
        or terminal_t_star != finite(producer.get("t_star"), "producer t_star")
        or terminal_t_star != finite(convergence.get("window", {}).get("end_t_star")
                                     if isinstance(convergence.get("window"), dict) else None,
                                     "convergence end t_star")
    ):
        raise ValueError("producer/checkpoint/convergence terminal time mismatch")
    contract, bound_hashes = verify_convergence_binding(
        convergence, producer, producer_path, canonical_history, sidecar,
        checkpoint, closure, expected_source_commit=expected_source_commit,
        expected_source_sha256=expected_source_sha256,
    )
    if (
        terminal_t != finite(
            convergence["inputs"][-1]["terminal_checkpoint"]["validated_identity"].get("t"),
            "convergence terminal t",
        )
        or terminal_t_star != finite(
            convergence["inputs"][-1]["terminal_checkpoint"]["validated_identity"].get("t_star"),
            "convergence terminal t_star",
        )
        or terminal_i != exact_int(
            convergence["inputs"][-1]["terminal_checkpoint"]["validated_identity"].get("i"),
            "convergence terminal iteration",
        )
    ):
        raise ValueError("convergence terminal identity does not match producer/checkpoint")
    cell_rows = read_exact_csv(cells_path, CELL_FIELDS, "cell export")
    cells = parse_cells(cell_rows)
    if exact_int(producer.get("cell_count"), "producer cell_count") != len(cells):
        raise ValueError("producer cell_count does not match cell export")
    plane_rows = read_exact_csv(history_path, PLANE_HISTORY_FIELDS, "plane history")
    terminal_rows = terminal_plane_rows(
        plane_rows, case_id=case_id, terminal_t=terminal_t,
        terminal_t_star=terminal_t_star, terminal_i=terminal_i,
    )
    reference = load_reference(reference_path)
    verify_reference_artifact(
        reference_artifact, reference, modes=modes,
        quadrature_order=reference_quadrature_order,
    )
    results: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    domain_size = finite(producer.get("domain_size"), "producer domain_size")
    if domain_size <= 0.0:
        raise ValueError("producer domain_size is not positive")
    official_radius = 1.0 / 12.0
    exact_area = math.pi * official_radius * official_radius
    exact_width = math.sqrt(2.0 * exact_area)
    exact_height = 0.5 * exact_width
    hydraulic_diameter = 2.0 * exact_width * exact_height / (exact_width + exact_height)
    close_number(
        domain_size, INTERNAL_LENGTH_DH * hydraulic_diameter,
        "producer domain size/W2 geometry",
    )
    density = finite(contract.get("density_liquid"), "contract density_liquid")
    if density <= 0.0:
        raise ValueError("contract density_liquid is not positive")
    for label, location in PLANES:
        if finite(terminal_rows[label]["plane_dh"], f"{label}:plane_dh") != location:
            raise ValueError(f"{label} plane coordinate differs from the declared source plane")
        result, plane_samples = analyze_plane(
            cells, terminal_rows[label], reference, plane_label=label,
            plane_dh=location, hydraulic_diameter=hydraulic_diameter,
            density=density, modes=modes,
            reference_quadrature_order=reference_quadrature_order,
            cell_quadrature_order=cell_quadrature_order,
        )
        results.append(result)
        samples.extend(plane_samples)
    before_hashes = {
        "producer_metadata": expected_producer_sha256,
        "cells": expected_cells_sha256,
        "plane_history": expected_plane_history_sha256,
        "convergence_report": expected_convergence_sha256,
        "reference_script": expected_reference_sha256,
        "reference_report": expected_reference_report_sha256,
        "precursor_history": bound_hashes["history"],
        "run_contract": bound_hashes["run_contract"],
        "checkpoint": bound_hashes["checkpoint"],
        "checkpoint_sidecar": bound_hashes["sidecar"],
        "prediction_closure": bound_hashes["closure"],
    }
    after_hashes = {
        "producer_metadata": sha256_file(producer_path),
        "cells": sha256_file(cells_path),
        "plane_history": sha256_file(history_path),
        "convergence_report": sha256_file(convergence_path),
        "reference_script": sha256_file(reference_path),
        "reference_report": sha256_file(reference_report_path),
        "precursor_history": sha256_file(canonical_history),
        "run_contract": sha256_file(Path(bound_hashes["run_contract_path"])),
        "checkpoint": sha256_file(checkpoint),
        "checkpoint_sidecar": sha256_file(sidecar),
        "prediction_closure": sha256_file(closure),
    }
    if before_hashes != after_hashes:
        raise ValueError("an input changed during profile comparison")
    payload = {
        "schema": SCHEMA,
        "case_id": case_id,
        "source_commit": expected_source_commit,
        "geometry_fingerprint": GEOMETRY_FINGERPRINT,
        "terminal": {"t": terminal_t, "t_star": terminal_t_star, "iteration": terminal_i},
        "geometry": {
            "hydraulic_diameter": hydraulic_diameter,
            "internal_length_dh": INTERNAL_LENGTH_DH,
            "aspect_ratio": 2.0,
            "maxlevel": exact_int(producer.get("maxlevel"), "producer maxlevel"),
            "delta_min_Dh": finite(producer.get("delta_min_Dh"), "producer delta_min_Dh"),
        },
        "reference": {
            "schema": REFERENCE_SCHEMA,
            "module_api": ["velocity", "reference_metrics"],
            "modes": modes,
            "reference_quadrature_order": reference_quadrature_order,
            "cell_average_quadrature_order": cell_quadrature_order,
            "task02_artifact_binding": "exact_hash_and_recomputed_declared_settings",
        },
        "method": {
            "numerical_plane_reconstruction": (
                "half_open_x_slab_and_exact_rectangular_aperture_overlap_matching_producer"
            ),
            "numerical_interpolation": "piecewise_constant_terminal_leaf_cell_value",
            "reference_interpolation": "tensor_gauss_area_average_on_each_leaf_aperture_overlap",
            "norms": "aperture_area_weighted_bulk_normalized",
            "symmetry": "exact_overlap_integral_against_reflected_leaf_partition",
        },
        "inputs": {
            "producer_metadata": provenance_record(producer_path),
            "cells": provenance_record(cells_path),
            "plane_history": provenance_record(history_path),
            "convergence_report": provenance_record(convergence_path),
            "checkpoint_sidecar": provenance_record(sidecar),
            "checkpoint": provenance_record(checkpoint),
            "prediction_closure": provenance_record(closure),
            "run_contract": provenance_record(Path(bound_hashes["run_contract_path"])),
            "reference_script": provenance_record(reference_path),
            "reference_report": provenance_record(reference_report_path),
        },
        "planes": results,
        "classification_inputs": {
            "profile_l2_by_plane": {
                str(item["plane_label"]): item["profile_comparison"]["bulk_normalized_weighted_l2"]
                for item in results
            },
            "beta_relative_difference_by_plane": {
                str(item["plane_label"]): item["profile_comparison"]["beta_relative_difference"]
                for item in results
            },
            "alpha_relative_difference_by_plane": {
                str(item["plane_label"]): item["profile_comparison"]["alpha_relative_difference"]
                for item in results
            },
            "scientific_classification": "not_assigned_by_reducer",
        },
        "checks": {
            "converged_terminal_state_bound": True,
            "input_hashes_stable": True,
            "all_declared_planes_present": True,
            "leaf_partitions_close": True,
            "plane_history_metric_identities": True,
            "checkpoint_and_convergence_lineage_bound": True,
            "source_bundle_identity_bound": True,
            "task02_reference_artifact_bound": True,
            "reference_no_slip": True,
            "numerical_wall_adjacent_coverage": True,
        },
        "claim_boundary": (
            "profile-shape diagnostic and classification inputs only; no stationarity, "
            "physical validation, or fully-developed-flow classification is assigned"
        ),
    }
    return payload, samples


SAMPLE_FIELDS = (
    "plane_label", "plane_dh", "plane_x", "source_cell_id", "x", "y", "z",
    "Delta", "cs", "area_weight", "numerical_ux", "numerical_uy", "numerical_uz",
    "numerical_u_over_bulk", "reference_cell_average", "reference_normalized",
    "normalized_difference", "y_lower", "y_upper", "z_lower", "z_upper",
)


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write_outputs(output_dir: Path, payload: dict[str, object], samples: Sequence[dict[str, object]]) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("refusing to overwrite profile-comparison output directory")
    output_dir.mkdir(parents=True)
    try:
        atomic_json(output_dir / "precursor-poiseuille-profile-comparison.json", payload)
        with (output_dir / "precursor-poiseuille-profile-samples.csv").open(
            "x", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=SAMPLE_FIELDS)
            writer.writeheader()
            for sample in samples:
                row = {key: sample[key] for key in SAMPLE_FIELDS if key in sample}
                bounds = sample["bounds"]
                assert isinstance(bounds, tuple)
                row.update(dict(zip(("y_lower", "y_upper", "z_lower", "z_upper"), bounds)))
                writer.writerow(row)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        # Leave any partial directory visible and fail closed; never overwrite it on retry.
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer-metadata", type=Path, required=True)
    parser.add_argument("--convergence-report", type=Path, required=True)
    parser.add_argument("--plane-history", type=Path, required=True)
    parser.add_argument("--reference-script", type=Path, required=True)
    parser.add_argument("--reference-report", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-producer-sha256", required=True)
    parser.add_argument("--expected-cells-sha256", required=True)
    parser.add_argument("--expected-plane-history-sha256", required=True)
    parser.add_argument("--expected-convergence-sha256", required=True)
    parser.add_argument("--expected-reference-sha256", required=True)
    parser.add_argument("--expected-reference-report-sha256", required=True)
    parser.add_argument("--modes", type=int, default=256)
    parser.add_argument("--reference-quadrature-order", type=int, default=256)
    parser.add_argument("--cell-quadrature-order", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload, samples = analyze(
        producer_metadata=args.producer_metadata,
        convergence_report=args.convergence_report,
        plane_history=args.plane_history,
        reference_script=args.reference_script,
        reference_report=args.reference_report,
        expected_source_commit=args.expected_source_commit,
        expected_source_sha256=args.expected_source_sha256,
        expected_producer_sha256=args.expected_producer_sha256,
        expected_cells_sha256=args.expected_cells_sha256,
        expected_plane_history_sha256=args.expected_plane_history_sha256,
        expected_convergence_sha256=args.expected_convergence_sha256,
        expected_reference_sha256=args.expected_reference_sha256,
        expected_reference_report_sha256=args.expected_reference_report_sha256,
        modes=args.modes,
        reference_quadrature_order=args.reference_quadrature_order,
        cell_quadrature_order=args.cell_quadrature_order,
    )
    write_outputs(args.output_dir, payload, samples)
    print(json.dumps({
        "schema": payload["schema"], "case_id": payload["case_id"],
        "plane_count": len(payload["planes"]), "output_dir": str(args.output_dir),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
