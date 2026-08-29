#!/usr/bin/env python3
"""Compare continuous and checkpoint/restored internal-nozzle endpoints."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path


KEY_FIELDS = ("x", "y", "z", "level", "Delta")
STATE_FIELDS = ("f", "ux", "uy", "uz", "p", "cs")
HYDRAULIC_FIELDS = (
    "fluid_area", "liquid_area", "Q_l", "mdot_l", "mdot_mix",
    "J_k_liquid", "J_k_mixture", "J_p", "J_total",
    "area_weighted_liquid_velocity", "flux_weighted_liquid_velocity",
    "area_mean_pressure", "forcing_to_plane_pressure_drop",
)


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _relative_l2(sum_sq_diff: float, sum_sq_reference: float) -> float:
    if sum_sq_reference == 0.0:
        return math.sqrt(sum_sq_diff)
    return math.sqrt(sum_sq_diff / sum_sq_reference)


def compare_fields(left_path: Path, right_path: Path) -> dict[str, object]:
    left: dict[tuple[str, ...], tuple[float, ...]] = {}
    left_time: tuple[str, str] | None = None
    with left_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = tuple(row[name] for name in KEY_FIELDS)
            if key in left:
                raise ValueError(f"duplicate left cell key: {key}")
            left[key] = tuple(float(row[name]) for name in STATE_FIELDS)
            left_time = left_time or (row["t"], row["i"])

    accum = {name: [0.0, 0.0, 0.0] for name in STATE_FIELDS}
    matched = 0
    right_only = 0
    seen: set[tuple[str, ...]] = set()
    right_time: tuple[str, str] | None = None
    with right_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = tuple(row[name] for name in KEY_FIELDS)
            if key in seen:
                raise ValueError(f"duplicate right cell key: {key}")
            seen.add(key)
            right_time = right_time or (row["t"], row["i"])
            reference = left.get(key)
            if reference is None:
                right_only += 1
                continue
            matched += 1
            for index, name in enumerate(STATE_FIELDS):
                observed = float(row[name])
                diff = observed - reference[index]
                accum[name][0] += diff * diff
                accum[name][1] += reference[index] * reference[index]
                accum[name][2] = max(accum[name][2], abs(diff))

    left_only = len(left) - matched
    per_field = {
        name: {
            "relative_l2": _relative_l2(values[0], values[1]),
            "max_absolute_difference": values[2],
        }
        for name, values in accum.items()
    }
    return {
        "left_time_iteration": left_time,
        "right_time_iteration": right_time,
        "matched_rows": matched,
        "left_only_rows": left_only,
        "right_only_rows": right_only,
        "per_field": per_field,
        "field_relative_l2_max": max(value["relative_l2"] for value in per_field.values()),
    }


def _terminal_rows(path: Path, identity: str) -> dict[str, dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        rows.extend(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"no rows in {path}")
    terminal_t = max(float(row["t"]) for row in rows)
    selected = [row for row in rows if math.isclose(float(row["t"]), terminal_t, abs_tol=1e-12)]
    result = {row[identity]: row for row in selected}
    if len(result) != len(selected):
        raise ValueError(f"duplicate terminal {identity} in {path}")
    return result


def compare_hydraulics(left_path: Path, right_path: Path) -> dict[str, object]:
    left = _terminal_rows(left_path, "plane_label")
    right = _terminal_rows(right_path, "plane_label")
    common = sorted(left.keys() & right.keys())
    comparisons: dict[str, dict[str, float]] = {}
    maximum = 0.0
    for plane in common:
        values: dict[str, float] = {}
        for field in HYDRAULIC_FIELDS:
            reference = float(left[plane][field])
            observed = float(right[plane][field])
            scale = max(abs(reference), 1e-300)
            relative = abs(observed - reference) / scale
            values[field] = relative
            maximum = max(maximum, relative)
        comparisons[plane] = values
    return {
        "common_planes": common,
        "left_only_planes": sorted(left.keys() - right.keys()),
        "right_only_planes": sorted(right.keys() - left.keys()),
        "relative_difference_max": maximum,
        "relative_differences": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continuous-field", type=Path, required=True)
    parser.add_argument("--segmented-field", type=Path, required=True)
    parser.add_argument("--continuous-hydraulics", type=Path, required=True)
    parser.add_argument("--segmented-hydraulics", type=Path, required=True)
    parser.add_argument("--relative-tolerance", type=float, default=1e-7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    fields = compare_fields(args.continuous_field, args.segmented_field)
    hydraulics = compare_hydraulics(args.continuous_hydraulics, args.segmented_hydraulics)
    endpoint_equal = fields["left_time_iteration"] == fields["right_time_iteration"]
    passed = bool(
        endpoint_equal
        and fields["left_only_rows"] == 0
        and fields["right_only_rows"] == 0
        and fields["field_relative_l2_max"] <= args.relative_tolerance
        and not hydraulics["left_only_planes"]
        and not hydraulics["right_only_planes"]
    )
    payload = {
        "schema": "internal_nozzle_restart_control_comparison_v1",
        "acceptance": {
            "relative_l2_tolerance": args.relative_tolerance,
            "endpoint_equal": endpoint_equal,
            "passed": passed,
        },
        "fields": fields,
        "hydraulics": hydraulics,
    }
    _atomic_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
