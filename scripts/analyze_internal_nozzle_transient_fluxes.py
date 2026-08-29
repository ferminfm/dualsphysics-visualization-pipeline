#!/usr/bin/env python3
"""Compute deterministic transient cross-section metrics from post-projection field exports."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

DEFAULT_PLANES_DH = [0.5, 1.75, 5.25, 14.5, 15.0, 15.25]
DEFAULT_SCHEMA = "internal_nozzle_post_projection_fields_v2"
OFFICIAL_R = 1.0 / 12.0
PLENUM_SCALE = 3.0
PLENUM_DH = 2.0
CONTRACTION_DH = 3.0
STRAIGHT_DH = 10.0
EXIT_DH = PLENUM_DH + CONTRACTION_DH + STRAIGHT_DH
DEFAULT_RHO_L = 1.0
DEFAULT_RHO_G = 1.0 / 27.84
A0 = math.pi * OFFICIAL_R * OFFICIAL_R
W = math.sqrt(2.0 * A0)
H = W / 2.0
DH = 2.0 * W * H / (W + H)

REQUIRED_CONTRACT_KEYS = {
    "schema",
    "pressure_provenance",
    "event_provenance",
    "gravity_enabled",
}
REQUIRED_MANIFEST_KEYS = {
    "case_id",
    "domain_mode",
    "field_frame_index",
    "t",
    "i",
    "filename",
    "sample_count",
    "source_sha256",
    "schedule_version",
    "schedule_sha256",
    "master_tick",
    "target_time",
    "actual_time",
    "restart_lineage",
}
REQUIRED_FIELD_KEYS = {
    "case_id", "source_frame_id", "field_frame_index", "t", "i", "x", "y", "z",
    "f", "ux", "uy", "uz", "p", "cs", "Delta", "pressure_provenance",
    "event_provenance", "gravity_enabled", "source_sha256", "schedule_version",
    "schedule_sha256", "master_tick", "target_time", "actual_time", "restart_lineage",
}

METRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "fluid_area": {
        "name": "fluid_area",
        "status": "derived",
        "unit": "solver_length^2",
        "sign": "non-negative",
        "formula": "sum(exact rectangular aperture/cell overlap area over intersecting leaves)",
    },
    "liquid_area": {
        "name": "liquid_area",
        "status": "derived",
        "unit": "solver_length^2",
        "sign": "non-negative",
        "formula": "sum(f * exact aperture/cell overlap area), with f clipped to [0,1]",
    },
    "Q_l": {
        "name": "Q_l",
        "status": "derived",
        "unit": "solver_length^3/solver_time",
        "sign": "signed with ux",
        "formula": "sum(f * ux * aperture_overlap_area); mirrored by domain factor",
    },
    "mdot_l": {
        "name": "mdot_l",
        "status": "derived",
        "unit": "solver_mass/solver_time",
        "sign": "signed with ux",
        "formula": "rho_l * Q_l",
    },
    "mdot_mix": {
        "name": "mdot_mix",
        "status": "derived",
        "unit": "solver_mass/solver_time",
        "sign": "signed with ux",
        "formula": "sum((rho_g + f*(rho_l-rho_g)) * ux * aperture_overlap_area)",
    },
    "liquid_kinetic_momentum_flux": {
        "name": "liquid_kinetic_momentum_flux",
        "status": "derived",
        "unit": "solver_force_equivalent",
        "sign": "non-negative axial transport contribution",
        "formula": "sum(rho_l * f * ux^2 * aperture_overlap_area)",
    },
    "mixture_kinetic_momentum_flux": {
        "name": "mixture_kinetic_momentum_flux",
        "status": "derived",
        "unit": "solver_force_equivalent",
        "sign": "non-negative axial transport contribution",
        "formula": "sum(rho_mix * ux^2 * aperture_overlap_area); rho_mix = rho_g + f*(rho_l-rho_g)",
    },
    "pressure_contribution": {
        "name": "pressure_contribution",
        "status": "derived",
        "unit": "solver_force_equivalent",
        "sign": "signed by local gauge pressure",
        "formula": "sum((p - p_ambient) * aperture_overlap_area)",
    },
    "J_total": {
        "name": "J_total",
        "status": "derived",
        "unit": "solver_force_equivalent",
        "sign": "signed",
        "formula": "mixture_kinetic_momentum_flux + pressure_contribution",
    },
    "area_weighted_liquid_velocity": {
        "name": "area_weighted_liquid_velocity",
        "status": "derived",
        "unit": "solver_length/solver_time",
        "sign": "signed",
        "formula": "sum(f * ux * aperture_overlap_area) / liquid_area",
    },
    "flux_weighted_liquid_velocity": {
        "name": "flux_weighted_liquid_velocity",
        "status": "derived",
        "unit": "solver_length/solver_time",
        "sign": "signed",
        "formula": "sum(f * ux^2 * aperture_overlap_area) / Q_l",
    },
    "area_mean_pressure": {
        "name": "area_mean_pressure",
        "status": "derived",
        "unit": "solver_pressure",
        "sign": "signed",
        "formula": "sum((p - p_ambient) * aperture_overlap_area) / fluid_area",
    },
    "forcing_to_plane_pressure_drop": {
        "name": "forcing_to_plane_pressure_drop",
        "status": "derived",
        "unit": "solver_pressure",
        "sign": "positive when forcing exceeds local pressure",
        "formula": "pressure_forcing - area_mean_pressure",
    },
    "legacy_Q_l_times_area_weighted_velocity": {
        "name": "legacy_Q_l_times_area_weighted_velocity",
        "status": "derived",
        "unit": "solver_length^4/solver_time^2",
        "sign": "signed with ux",
        "formula": "Q_l * area_weighted_liquid_velocity",
    },
}


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _is_finite(value: object, label: str, failures: list[str]) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        failures.append(f"non-numeric {label}: {value!r}")
        return 0.0
    if not math.isfinite(number):
        failures.append(f"nonfinite {label}: {value!r}")
        return 0.0
    return number


def _read_rows(path: Path, *, required: set[str] | None = None, context: str = "") -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing {context}: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        sample = handle.read()
    if not sample:
        raise ValueError(f"empty file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle), [])
    if len(set(header)) != len(header):
        duplicates = sorted({name for name in header if header.count(name) > 1})
        raise ValueError(f"duplicate header fields in {context}: {', '.join(duplicates)}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if required and reader.fieldnames is not None:
            missing = sorted(required - set(reader.fieldnames))
            if missing:
                raise ValueError(f"missing required fields in {context}: {', '.join(missing)}")
        return list(reader)


def _smoothstep(value: float) -> float:
    value = _clamp01(value)
    return value * value * (3.0 - 2.0 * value)


def _width_internal(x_dh: float) -> float:
    if x_dh <= PLENUM_DH:
        return PLENUM_SCALE * W
    if x_dh <= PLENUM_DH + CONTRACTION_DH:
        blend = _smoothstep((x_dh - PLENUM_DH) / CONTRACTION_DH)
        return (1.0 - blend) * PLENUM_SCALE * W + blend * W
    return W


def _height_internal(x_dh: float) -> float:
    if x_dh <= PLENUM_DH:
        return PLENUM_SCALE * H
    if x_dh <= PLENUM_DH + CONTRACTION_DH:
        blend = _smoothstep((x_dh - PLENUM_DH) / CONTRACTION_DH)
        return (1.0 - blend) * PLENUM_SCALE * H + blend * H
    return H


def _cell_intersects_plane(x: float, delta: float, x_plane: float) -> bool:
    return (x - 0.5 * delta) <= x_plane < (x + 0.5 * delta)


def _inside_aperture(x_dh: float, y: float, z: float, domain_mode: str) -> bool:
    w_half = _width_internal(x_dh) / 2.0
    h_half = _height_internal(x_dh) / 2.0
    if domain_mode == "quarter":
        return (0.0 <= y <= w_half) and (0.0 <= z <= h_half)
    return abs(y) <= w_half and abs(z) <= h_half


def _aperture_overlap_area(
    x_dh: float, y: float, z: float, delta: float, domain_mode: str
) -> float:
    w_half = _width_internal(x_dh) / 2.0
    h_half = _height_internal(x_dh) / 2.0
    ymin, ymax = (0.0, w_half) if domain_mode == "quarter" else (-w_half, w_half)
    zmin, zmax = (0.0, h_half) if domain_mode == "quarter" else (-h_half, h_half)
    dy = max(0.0, min(y + 0.5 * delta, ymax) - max(y - 0.5 * delta, ymin))
    dz = max(0.0, min(z + 0.5 * delta, zmax) - max(z - 0.5 * delta, zmin))
    return dy * dz


def _frame_rows_identity(run_dir: Path, manifest_row: dict[str, str]) -> dict[str, list[dict[str, str]]]:
    filename = manifest_row["filename"].strip()
    path = Path(filename)
    if not path.is_absolute():
        path = run_dir / path
    rows = _read_rows(path, required=REQUIRED_FIELD_KEYS, context=f"field file {path}")
    failures: list[str] = []
    identity_fields = {
        "case_id", "field_frame_index", "t", "i", "source_frame_id",
        "source_sha256", "schedule_version", "schedule_sha256", "master_tick",
        "target_time", "actual_time", "restart_lineage", "pressure_provenance",
        "event_provenance", "gravity_enabled",
    }
    identity_values: dict[str, set[str]] = {key: set() for key in identity_fields}
    for row in rows:
        for key in identity_values:
            value = row.get(key)
            if value is None:
                failures.append(f"missing field identity {key} in {path}")
            else:
                identity_values[key].add(value)
        _is_finite(row.get("x"), f"x in {path}", failures)
        _is_finite(row.get("y"), f"y in {path}", failures)
        _is_finite(row.get("z"), f"z in {path}", failures)
        _is_finite(row.get("f"), f"f in {path}", failures)
        _is_finite(row.get("ux"), f"ux in {path}", failures)
        _is_finite(row.get("uy"), f"uy in {path}", failures)
        _is_finite(row.get("uz"), f"uz in {path}", failures)
        _is_finite(row.get("p"), f"p in {path}", failures)
        _is_finite(row.get("cs"), f"cs in {path}", failures)
        _is_finite(row.get("Delta"), f"Delta in {path}", failures)

    if failures:
        raise ValueError("; ".join(failures))

    for key, values in identity_values.items():
        if len(values) != 1:
            raise ValueError(f"inconsistent frame identity for {path}: {key} has {sorted(values)}")

    for key, expected in [
        ("case_id", manifest_row.get("case_id", "")),
        ("field_frame_index", manifest_row.get("field_frame_index", "")),
        ("t", manifest_row.get("t", "")),
        ("i", manifest_row.get("i", "")),
    ]:
        observed = next(iter(identity_values[key]))
        if observed != expected:
            raise ValueError(
                f"inconsistent frame identity for {path}: manifest {key}={expected!r} != {observed!r}"
            )

    declared = manifest_row.get("sample_count", "")
    if int(float(declared)) != len(rows):
        raise ValueError(
            f"sample_count mismatch for {path}: manifest has {declared}, file has {len(rows)}"
        )

    return {
        "path": path,
        "rows": rows,
        "source_frame_id": next(iter(identity_values["source_frame_id"])) if identity_values["source_frame_id"] else "",
    }


def _compute_plane_metrics(
    plane_dh: float,
    frame_rows: list[dict[str, str]],
    row_ref: dict[str, str],
    rho_l: float,
    rho_g: float,
    pressure_forcing: float,
    p_ambient: float,
) -> tuple[dict[str, float], list[dict[str, str]]]:
    domain_mode = row_ref.get("domain_mode", "full").strip().lower()
    if domain_mode not in {"full", "quarter"}:
        raise ValueError(f"unsupported domain_mode={domain_mode!r}")
    mirror_factor = 4.0 if domain_mode == "quarter" else 1.0

    x_plane = plane_dh * DH
    aperture_plane_dh = min(plane_dh, EXIT_DH)
    contributions: dict[str, list[float]] = {
        name: [] for name in (
            "fluid_area", "liquid_area", "Q_l", "gas_volume_flux",
            "liquid_kinetic_momentum_flux", "mixture_kinetic_momentum_flux",
            "pressure_contribution", "liquid_velocity_numerator",
            "liquid_flux_velocity_numerator",
        )
    }
    selected_cells: list[dict[str, str]] = []
    intersecting_cells = 0

    for row in frame_rows:
        x = float(row["x"])
        delta = float(row["Delta"])
        if not _cell_intersects_plane(x, delta, x_plane):
            continue
        y = float(row["y"])
        z = float(row["z"])
        f = _clamp01(float(row["f"]))
        ux = float(row["ux"])
        uy = float(row["uy"])
        uz = float(row["uz"])
        p = float(row["p"]) - p_ambient
        cs = float(row["cs"])
        if delta <= 0.0 or not 0.0 <= cs <= 1.0:
            raise ValueError(f"invalid Delta/cs in frame {row['source_frame_id']}: {delta}, {cs}")

        area = _aperture_overlap_area(aperture_plane_dh, y, z, delta, domain_mode)
        if area <= 0.0:
            continue
        area *= mirror_factor

        intersecting_cells += 1
        rho_mix = rho_g + f * (rho_l - rho_g)
        contributions["fluid_area"].append(area)
        contributions["liquid_area"].append(f * area)
        contributions["Q_l"].append(f * ux * area)
        contributions["gas_volume_flux"].append((1.0 - f) * ux * area)
        contributions["liquid_kinetic_momentum_flux"].append(rho_l * f * ux * ux * area)
        contributions["mixture_kinetic_momentum_flux"].append(rho_mix * ux * ux * area)
        contributions["pressure_contribution"].append(p * area)
        contributions["liquid_velocity_numerator"].append(f * ux * area)
        contributions["liquid_flux_velocity_numerator"].append(f * ux * ux * area)

        selected_cells.append(
            {
                "case_id": row["case_id"],
                "source_frame_id": row["source_frame_id"],
                "field_frame_index": row["field_frame_index"],
                "t": row["t"],
                "i": row["i"],
                "plane_x_Dh": f"{plane_dh}",
                "x": row["x"],
                "y": row["y"],
                "z": row["z"],
                "f": row["f"],
                "f_clamped": f"{f:.17g}",
                "ux": row["ux"],
                "uy": row["uy"],
                "uz": row["uz"],
                "p": row["p"],
                "cs": row["cs"],
                "Delta": row["Delta"],
                "intersection_weight_area": f"{area:.17g}",
                "in_aperture_mask": "1",
                "mirror_factor": f"{mirror_factor:.1f}",
            }
        )

    if intersecting_cells == 0:
        raise ValueError(f"empty plane x/Dh={plane_dh} in frame {row_ref.get('source_frame_id')}")

    totals = {name: math.fsum(sorted(values)) for name, values in contributions.items()}
    fluid_area = totals["fluid_area"]
    liquid_area = totals["liquid_area"]
    q_l = totals["Q_l"]
    q_g = totals["gas_volume_flux"]
    j_k_liquid = totals["liquid_kinetic_momentum_flux"]
    j_k_mix = totals["mixture_kinetic_momentum_flux"]
    j_p = totals["pressure_contribution"]
    if not math.isfinite(fluid_area) or not math.isfinite(liquid_area) or fluid_area <= 0.0:
        raise ValueError(f"nonfinite or nonpositive fluid area for x/Dh={plane_dh}")
    if not math.isfinite(mix_flux := rho_l * q_l + rho_g * q_g):
        raise ValueError(f"nonfinite mixture mass flux accumulator for x/Dh={plane_dh}")

    area_mean_pressure = j_p / fluid_area
    forcing_pressure_drop = pressure_forcing - area_mean_pressure
    mdot_l = rho_l * q_l
    mdot_mix = rho_l * q_l + rho_g * q_g
    area_weighted_liquid_velocity = totals["liquid_velocity_numerator"] / liquid_area if liquid_area > 0.0 else 0.0
    flux_weighted_liquid_velocity = totals["liquid_flux_velocity_numerator"] / q_l if q_l != 0.0 else 0.0
    legacy_q_l_area_velocity = q_l * area_weighted_liquid_velocity
    j_total = j_k_mix + j_p

    return (
        {
            "fluid_area": fluid_area,
            "liquid_area": liquid_area,
            "Q_l": q_l,
            "mdot_l": mdot_l,
            "mdot_mix": mdot_mix,
            "liquid_kinetic_momentum_flux": j_k_liquid,
            "mixture_kinetic_momentum_flux": j_k_mix,
            "pressure_contribution": j_p,
            "J_total": j_total,
            "area_weighted_liquid_velocity": area_weighted_liquid_velocity,
            "flux_weighted_liquid_velocity": flux_weighted_liquid_velocity,
            "area_mean_pressure": area_mean_pressure,
            "forcing_to_plane_pressure_drop": forcing_pressure_drop,
            "legacy_Q_l_times_area_weighted_velocity": legacy_q_l_area_velocity,
        },
        selected_cells,
    )


def _parse_planes(text: str) -> list[float]:
    if not text:
        return []
    planes: list[float] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        planes.append(float(part))
    if not planes:
        raise ValueError("--planes requires at least one value")
    return planes


def analyze_run(
    run_dir: Path,
    manifest_path: Path,
    contract_path: Path,
    metrics_csv: Path,
    summary_json: Path,
    profile_csv: Path,
    rho_l: float,
    rho_g: float,
    p_ambient: float,
    pressure_forcing: float,
    planes: list[float],
    overwrite: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not overwrite:
        for path in (metrics_csv, summary_json, profile_csv):
            if path.exists():
                raise FileExistsError(f"refusing to overwrite {path}; use --overwrite")

    for path in (metrics_csv.parent, summary_json.parent, profile_csv.parent):
        path.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for value in planes:
        if not math.isfinite(value):
            failures.append(f"nonfinite plane: {value!r}")
    if failures:
        raise ValueError("; ".join(failures))
    for label, value in {
        "rho_l": rho_l, "rho_g": rho_g, "p_ambient": p_ambient,
        "pressure_forcing": pressure_forcing,
    }.items():
        if not math.isfinite(value):
            raise ValueError(f"nonfinite {label}")
    if rho_l <= 0.0 or rho_g <= 0.0:
        raise ValueError("phase densities must be positive")

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for key in REQUIRED_CONTRACT_KEYS:
        if key not in contract:
            raise ValueError(f"missing contract key: {key}")
    if contract["schema"] != DEFAULT_SCHEMA:
        raise ValueError(f"wrong contract schema: {contract['schema']!r}")

    manifest_rows = _read_rows(manifest_path, required=REQUIRED_MANIFEST_KEYS, context=str(manifest_path))
    if not manifest_rows:
        raise ValueError("field manifest is empty")

    frame_indices = [row.get("field_frame_index", "") for row in manifest_rows]
    if len(set(frame_indices)) != len(frame_indices):
        raise ValueError("duplicate field_frame_index values in manifest")

    metrics_rows: list[dict[str, str]] = []
    profile_rows: list[dict[str, str]] = []

    source_frame_provenance: list[dict[str, str]] = []

    for manifest_row in manifest_rows:
        for required_key in REQUIRED_MANIFEST_KEYS:
            if manifest_row.get(required_key, "") == "":
                raise ValueError(f"missing manifest value for {required_key}")

        _is_finite(manifest_row.get("t"), f"manifest t for frame {manifest_row.get('field_frame_index')}", failures)
        _is_finite(manifest_row.get("i"), f"manifest i for frame {manifest_row.get('field_frame_index')}", failures)
        if failures:
            raise ValueError("; ".join(failures))

        frame_data = _frame_rows_identity(run_dir, manifest_row)
        frame_rows = frame_data["rows"]
        source_frame_id = frame_data.get("source_frame_id") or manifest_row["field_frame_index"]
        source_frame_provenance.append(
            {
                "source_frame_id": source_frame_id,
                "field_frame_index": manifest_row["field_frame_index"],
                "filename": manifest_row["filename"],
            }
        )

        for plane_dh in planes:
            plane_metrics, plane_profile = _compute_plane_metrics(
                plane_dh=plane_dh,
                frame_rows=frame_rows,
                row_ref=manifest_row,
                rho_l=rho_l,
                rho_g=rho_g,
                pressure_forcing=pressure_forcing,
                p_ambient=p_ambient,
            )
            row = {
                "case_id": manifest_row["case_id"],
                "source_frame_id": source_frame_id,
                "field_frame_index": manifest_row["field_frame_index"],
                "t": manifest_row["t"],
                "i": manifest_row["i"],
                "domain_mode": manifest_row.get("domain_mode", "full"),
                "plane_x_Dh": f"{plane_dh}",
                "plane_x": f"{plane_dh * DH:.17g}",
                "mirror_factor": "4.0" if manifest_row.get("domain_mode", "full").strip().lower() == "quarter" else "1.0",
            }
            row.update({name: f"{value:.17g}" for name, value in plane_metrics.items()})
            metrics_rows.append(row)

            profile_rows.extend(
                {
                    "case_id": manifest_row["case_id"],
                    **cell,
                    "source_file": manifest_row["filename"],
                }
                for cell in plane_profile
            )

    metric_keys = list(METRIC_DEFINITIONS)

    metrics_path = metrics_csv
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        columns = [
            "case_id",
            "source_frame_id",
            "field_frame_index",
            "t",
            "i",
            "domain_mode",
            "plane_x_Dh",
            "plane_x",
            "mirror_factor",
        ] + metric_keys
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in sorted(
            metrics_rows,
            key=lambda item: (
                item["case_id"],
                int(item["field_frame_index"]),
                float(item["plane_x_Dh"]),
            ),
        ):
            writer.writerow(row)

    with profile_csv.open("w", newline="", encoding="utf-8") as handle:
        cell_columns = [
            "case_id",
            "source_frame_id",
            "field_frame_index",
            "t",
            "i",
            "source_file",
            "plane_x_Dh",
            "x",
            "y",
            "z",
            "f",
            "f_clamped",
            "ux",
            "uy",
            "uz",
            "p",
            "cs",
            "Delta",
            "intersection_weight_area",
            "in_aperture_mask",
            "mirror_factor",
        ]
        writer = csv.DictWriter(handle, fieldnames=cell_columns)
        writer.writeheader()
        for row in sorted(
            profile_rows,
            key=lambda item: (
                item["source_file"],
                item["source_frame_id"],
                float(item["plane_x_Dh"]),
                float(item["x"]),
                float(item["y"]),
                float(item["z"]),
            ),
        ):
            writer.writerow(row)

    summary: dict[str, Any] = {
        "schema": "internal_nozzle_transient_fluxes_v1",
        "run_dir": str(run_dir),
        "contract": {
            "schema": contract.get("schema"),
            "selected_case": contract.get("selected_case", ""),
            "pressure_provenance": contract.get("pressure_provenance"),
            "event_provenance": contract.get("event_provenance"),
            "gravity_enabled": contract.get("gravity_enabled"),
            "instrumentation_changes_solver_state": contract.get("instrumentation_changes_solver_state"),
        },
        "geometry": {
            "official_r": OFFICIAL_R,
            "W": W,
            "H": H,
            "Dh": DH,
            "plenum_Dh": PLENUM_DH,
            "contraction_Dh": CONTRACTION_DH,
            "straight_Dh": STRAIGHT_DH,
        },
        "analysis": {
            "planes_Dh": planes,
            "rho_l": rho_l,
            "rho_g": rho_g,
            "p_ambient": p_ambient,
            "pressure_forcing": pressure_forcing,
            "unit_system": "native nondimensional solver units; no SI conversion is asserted",
        },
        "aperture_mask": {
            "shape": "rectangle",
            "equations": [
                "y in [-W(x)/2,+W(x)/2], z in [-H(x)/2,+H(x)/2] for full",
                "y in [0,W(x)/2], z in [0,H(x)/2] for quarter (mirrored by 4)",
                "W(x)",
                "= 3W for x<=2Dh",
                "= interp(smoothstep((x-2Dh)/3Dh)*W, 3W→W) for 2Dh<x<=5Dh",
                "= W for x>5Dh",
                "H(x) analogously with H",
            ],
        },
        "cut_cell_quadrature": {
            "plane_rule": "half-open interval",
            "intersection": "x - Delta/2 <= x_plane < x + Delta/2",
            "area_weight": "exact overlap of the leaf y-z square and declared rectangular aperture",
            "cs_treatment": "cs must be finite in [0,1] and proves exported fluid-cell provenance; geometric overlap avoids using a volume fraction as a face-area proxy",
            "aperture_projection": "planes at and downstream of 15 Dh use the geometric exit aperture",
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "metric_status": {
            "measured": sorted(REQUIRED_FIELD_KEYS),
            "derived": sorted(metric_keys),
        },
        "source_frame_provenance": source_frame_provenance,
        "results": metrics_rows,
        "n_frame_rows": len(manifest_rows),
        "n_metric_rows": len(metrics_rows),
        "n_profile_rows": len(profile_rows),
    }

    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return metrics_rows, profile_rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--metrics-csv", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--profile-csv", type=Path, required=True)
    parser.add_argument("--rho-liquid", type=float, default=DEFAULT_RHO_L)
    parser.add_argument("--rho-gas", type=float, default=DEFAULT_RHO_G)
    parser.add_argument("--p-ambient", type=float, default=0.0)
    parser.add_argument("--pressure-forcing", type=float, default=351.48)
    parser.add_argument("--planes", type=str, default=",".join(str(x) for x in DEFAULT_PLANES_DH))
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    run_dir = args.run_dir
    manifest = args.manifest or (run_dir / "field_frame_manifest.csv")
    contract = args.contract or (run_dir / "field_export_contract.json")

    if not manifest.exists():
        raise FileNotFoundError(f"missing field manifest: {manifest}")
    if not contract.exists():
        raise FileNotFoundError(f"missing contract: {contract}")

    planes = _parse_planes(args.planes)
    analyze_run(
        run_dir=run_dir,
        manifest_path=manifest,
        contract_path=contract,
        metrics_csv=args.metrics_csv,
        summary_json=args.summary_json,
        profile_csv=args.profile_csv,
        rho_l=args.rho_liquid,
        rho_g=args.rho_gas,
        p_ambient=args.p_ambient,
        pressure_forcing=args.pressure_forcing,
        planes=planes,
        overwrite=args.overwrite,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
