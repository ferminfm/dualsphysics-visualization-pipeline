#!/usr/bin/env python3
"""Build and validate the steady-precursor Task 09 visual-review package.

The renderer is intentionally a local postprocessor.  It consumes hash-bound
case packages and retained CSV field exports, never a Basilisk checkpoint or
solver executable.  Matched A/B/C panels use one set of limits derived from
the union of the selected samples.  Only observed master ticks are rendered;
no temporal interpolation or invented frames are permitted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle
from PIL import Image


MANIFEST_SCHEMA = "internal_nozzle_steady_precursor_visual_review_v1"
PACKAGE_SCHEMA = "sealed_internal_nozzle_case_package_v2"
REFERENCE_SCHEMA = "rectangular_poiseuille_reference_v1"
PROFILE_SCHEMA = "internal_nozzle_precursor_profile_comparison_v1"
PRECURSOR_SCHEMA = "internal_nozzle_precursor_unsealed_export_v2"
CONVERGENCE_SCHEMA = "internal_nozzle_precursor_convergence_v1"
CASE_LABELS = {
    "A": "A: pressure driven, rest start",
    "B": "B: pressure driven, precursor start",
    "C": "C: flow-controlled diagnostic",
}
REVIEW_FIRST = (
    "contact-sheets/abc_liquid_tstar_0_2_4.png",
    "scalar-and-flux-history/abc_q_j_pressure.png",
    "poiseuille-reference/precursor_vs_exact_profiles.png",
    "exit-profiles/abc_exit_profiles_tstar_0_2_4.png",
    "precursor-convergence/precursor_convergence.png",
)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular_file(path: Path, context: str, *, nonempty: bool = True) -> Path:
    if path.is_symlink():
        raise ValueError(f"{context}: symlink forbidden: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{context}: missing file: {path}") from error
    if not resolved.is_file() or (nonempty and resolved.stat().st_size <= 0):
        raise ValueError(f"{context}: expected a nonempty regular file: {path}")
    return resolved


def load_json(path: Path, context: str) -> dict[str, object]:
    resolved = regular_file(path, context)
    try:
        value = json.loads(
            resolved.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{context}: invalid JSON object: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{context}: expected JSON object")
    return value


def csv_rows(path: Path, context: str) -> list[dict[str, str]]:
    resolved = regular_file(path, context)
    with resolved.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{context}: missing or duplicate CSV headers")
        return list(reader)


def finite(value: object, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{context}: invalid number {value!r}") from error
    if not math.isfinite(result):
        raise ValueError(f"{context}: nonfinite number")
    return result


def git_commit(value: object, context: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError(f"{context}: expected a 40-character lowercase Git SHA")
    return value


def exact_int(value: object, context: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{context}: invalid integer") from error
    if str(parsed) != str(value):
        raise ValueError(f"{context}: noncanonical integer")
    return parsed


def safe_under(root: Path, relative: str, context: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise ValueError(f"{context}: unsafe relative path {relative!r}")
    unresolved = root / candidate
    if unresolved.is_symlink():
        raise ValueError(f"{context}: symlink forbidden")
    resolved = regular_file(unresolved, context)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise ValueError(f"{context}: path escapes root") from error
    return resolved


def file_record(path: Path, *, base: Path | None = None) -> dict[str, object]:
    resolved = regular_file(path, "file record")
    display = str(resolved if base is None else resolved.relative_to(base.resolve(strict=True)))
    return {
        "path": display,
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def verify_member(root: Path, package: dict[str, object], name: str) -> Path:
    members = package.get("members")
    if not isinstance(members, dict) or not isinstance(members.get(name), dict):
        raise ValueError(f"sealed package lacks member {name}")
    record = members[name]
    relative = record.get("path")
    if not isinstance(relative, str) or relative != name:
        raise ValueError(f"sealed package member {name} has unexpected path")
    path = safe_under(root, relative, f"sealed member {name}")
    if record.get("size_bytes") != path.stat().st_size or record.get("sha256") != sha256_file(path):
        raise ValueError(f"sealed package member {name} identity mismatch")
    return path


@dataclass(frozen=True)
class FieldFrame:
    role: str
    tick: int
    t: float
    t_star: float
    path: Path
    manifest_row: dict[str, str]


@dataclass
class SliceData:
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    f: np.ndarray
    ux: np.ndarray
    p: np.ndarray
    cs: np.ndarray
    delta: np.ndarray


@dataclass
class CaseData:
    role: str
    root: Path
    package_path: Path
    package: dict[str, object]
    schedule: dict[str, object]
    metrics_path: Path
    profiles_path: Path
    health_path: Path
    metric_rows: list[dict[str, str]]
    profile_rows: list[dict[str, str]]
    field_frames: dict[int, FieldFrame]
    slices: dict[int, SliceData]


def load_case(
    role: str, root_arg: Path, package_arg: Path, ticks: Sequence[int], dh: float,
    expected_commit: str,
) -> CaseData:
    root = root_arg.resolve(strict=True)
    package_path = regular_file(package_arg, f"Case {role} package")
    package = load_json(package_path, f"Case {role} package")
    if package.get("schema") != PACKAGE_SCHEMA or package.get("case_role") != role:
        raise ValueError(f"Case {role}: sealed package schema/role mismatch")
    if Path(str(package.get("run_root"))).resolve(strict=True) != root:
        raise ValueError(f"Case {role}: sealed package run_root mismatch")
    if package.get("scientific_source_commit") != expected_commit:
        raise ValueError(f"Case {role}: scientific source commit mismatch")
    case_id = package.get("case_id")
    source_sha = package.get("source_sha256")
    schedule_sha = package.get("schedule_sha256")
    schedule_version = package.get("schedule_version")
    if not all(isinstance(value, str) and value for value in (
            case_id, source_sha, schedule_sha, schedule_version)):
        raise ValueError(f"Case {role}: incomplete sealed identity")

    metrics_path = verify_member(root, package, "hydraulic_plane_metrics.csv")
    profiles_path = verify_member(root, package, "hydraulic_plane_profiles.csv")
    health_path = verify_member(root, package, "solver_health_metrics.csv")
    schedule_path = verify_member(root, package, "run_schedule_contract.json")
    raw_path = verify_member(root, package, "raw_export_manifest.json")
    if role in "BC":
        verify_member(root, package, "precursor_transfer_projection.csv")
        verify_member(root, package, "precursor_transfer_projection_acceptance.json")
    if role == "C":
        verify_member(root, package, "poiseuille_profile_validation.csv")
        verify_member(root, package, "poiseuille_profile_acceptance.json")
    schedule = load_json(schedule_path, f"Case {role} schedule")
    if schedule.get("schema") != "internal_nozzle_launch_schedule_v1":
        raise ValueError(f"Case {role}: unsupported schedule schema")
    if schedule.get("schedule_version") != schedule_version:
        raise ValueError(f"Case {role}: schedule version mismatch")
    if sha256_file(schedule_path) != schedule_sha:
        raise ValueError(f"Case {role}: schedule hash mismatch")
    tick_dt = finite(schedule.get("master_tick_dt"), f"Case {role}:master_tick_dt")
    if tick_dt <= 0 or not math.isclose(tick_dt / dh, 0.1, rel_tol=0, abs_tol=2e-12):
        raise ValueError(f"Case {role}: master tick is not the declared 0.1 t-star")

    raw = load_json(raw_path, f"Case {role} raw export manifest")
    files = raw.get("files")
    if not isinstance(files, dict) or files.get("field_manifest") != "field_frame_manifest.csv":
        raise ValueError(f"Case {role}: raw manifest does not bind field manifest")
    manifest_path = safe_under(root, "field_frame_manifest.csv", f"Case {role} field manifest")
    manifest_rows = csv_rows(manifest_path, f"Case {role} field manifest")
    selected: dict[int, FieldFrame] = {}
    for row_number, row in enumerate(manifest_rows, 2):
        tick = exact_int(row.get("master_tick"), f"Case {role} field row {row_number}:tick")
        if tick not in ticks:
            continue
        if tick in selected:
            raise ValueError(f"Case {role}: duplicate field frame at master tick {tick}")
        if (row.get("case_id") != case_id or row.get("domain_mode") != "full" or
                row.get("source_sha256") != source_sha or
                row.get("schedule_sha256") != schedule_sha or
                row.get("schedule_version") != schedule_version):
            raise ValueError(f"Case {role}: field manifest identity mismatch at tick {tick}")
        target = finite(row.get("target_time"), f"Case {role}:target_time")
        actual = finite(row.get("actual_time"), f"Case {role}:actual_time")
        t_value = finite(row.get("t"), f"Case {role}:t")
        if (not math.isclose(target, tick * tick_dt, rel_tol=0, abs_tol=1e-12) or
                not math.isclose(actual, target, rel_tol=0, abs_tol=1e-12) or
                not math.isclose(t_value, actual, rel_tol=0, abs_tol=1e-12)):
            raise ValueError(f"Case {role}: off-schedule field frame at tick {tick}")
        filename = row.get("filename")
        if not isinstance(filename, str):
            raise ValueError(f"Case {role}: missing field filename")
        path = safe_under(root, filename, f"Case {role} field tick {tick}")
        selected[tick] = FieldFrame(role, tick, t_value, t_value / dh, path, row)
    missing = sorted(set(ticks) - set(selected))
    if missing:
        raise ValueError(f"Case {role}: missing selected master ticks {missing}")

    metrics = csv_rows(metrics_path, f"Case {role} metrics")
    profiles = csv_rows(profiles_path, f"Case {role} profiles")
    health = csv_rows(health_path, f"Case {role} health")
    for context, rows in (("metrics", metrics), ("profiles", profiles), ("health", health)):
        if not rows:
            raise ValueError(f"Case {role}: empty {context}")
        if any(row.get("case_id") != case_id for row in rows):
            raise ValueError(f"Case {role}: mixed case identity in {context}")
        if "case_role" in rows[0] and any(row.get("case_role") != role for row in rows):
            raise ValueError(f"Case {role}: mixed case role in {context}")

    slices = {tick: read_midplane(frame, role, source_sha, schedule_sha)
              for tick, frame in selected.items()}
    return CaseData(
        role, root, package_path, package, schedule, metrics_path, profiles_path,
        health_path, metrics, profiles, selected, slices,
    )


def read_midplane(frame: FieldFrame, role: str, source_sha: str, schedule_sha: str) -> SliceData:
    values: dict[str, list[float]] = {
        name: [] for name in ("x", "y", "z", "f", "ux", "p", "cs", "Delta")
    }
    with frame.path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = set(values) | {
            "case_id", "master_tick", "source_sha256", "schedule_sha256",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"Case {role}: field CSV lacks required columns")
        expected_case = frame.manifest_row["case_id"]
        for row_number, row in enumerate(reader, 2):
            if (row["case_id"] != expected_case or
                    exact_int(row["master_tick"], f"field row {row_number}:tick") != frame.tick or
                    row["source_sha256"] != source_sha or row["schedule_sha256"] != schedule_sha):
                raise ValueError(f"Case {role}: field-row provenance mismatch")
            delta = finite(row["Delta"], "field Delta")
            z = finite(row["z"], "field z")
            if abs(z) > 0.51 * delta:
                continue
            for name in values:
                values[name].append(finite(row[name], f"field {name}"))
    if not values["x"]:
        raise ValueError(f"Case {role}: no midplane cells at tick {frame.tick}")
    return SliceData(**{name.lower(): np.asarray(item) for name, item in values.items()})


def image_record(path: Path, root: Path, *, roles: Sequence[str] = (),
                 ticks: Sequence[int] = ()) -> dict[str, object]:
    resolved = regular_file(path, "visual product")
    with Image.open(resolved) as image:
        image.verify()
    with Image.open(resolved) as image:
        width, height = image.size
        media_format = image.format
    if width < 480 or height < 300 or media_format != "PNG":
        raise ValueError(f"invalid PNG dimensions/format: {resolved}")
    record = file_record(resolved, base=root)
    record.update({
        "media_type": "image/png", "width": width, "height": height,
        "case_roles": list(roles), "master_ticks": list(ticks),
    })
    return record


def save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=145, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def shared_limits(cases: dict[str, CaseData], ticks: Sequence[int], exit_x: float) -> dict[str, object]:
    pressure: list[np.ndarray] = []
    velocity: list[np.ndarray] = []
    for role in "ABC":
        for tick in ticks:
            data = cases[role].slices[tick]
            mask = (data.cs > 1e-8) & (data.x <= exit_x + 1e-12)
            if not np.any(mask):
                raise ValueError(f"Case {role}: no internal samples at tick {tick}")
            pressure.append(data.p[mask])
            velocity.append(data.ux[mask])
    p = np.concatenate(pressure)
    u = np.concatenate(velocity)
    p_limits = [float(np.min(p)), float(np.max(p))]
    u_limits = [float(np.min(u)), float(np.max(u))]
    for name, limits in (("pressure", p_limits), ("axial_velocity", u_limits)):
        if not all(math.isfinite(value) for value in limits):
            raise ValueError(f"nonfinite shared {name} limits")
        if limits[0] == limits[1]:
            pad = max(abs(limits[0]), 1.0) * 1e-12
            limits[0] -= pad
            limits[1] += pad
    return {
        "shared_across_cases": True,
        "derivation": "exact_minimum_and_maximum_over_all_selected_internal_midplane_samples",
        "pressure": p_limits,
        "axial_velocity": u_limits,
        "liquid_volume_fraction": [0.0, 1.0],
    }


def field_panel(axis: plt.Axes, data: SliceData, *, quantity: str, dh: float,
                exit_x: float, limits: Sequence[float], title: str,
                internal_only: bool = False) -> None:
    mask = np.ones(data.x.shape, dtype=bool)
    if internal_only:
        mask &= (data.cs > 1e-8) & (data.x <= exit_x + 1e-12)
    x = data.x[mask] / dh
    y = data.y[mask] / dh
    values = getattr(data, quantity)[mask]
    cmap = {"f": "Blues", "ux": "magma", "p": "viridis"}[quantity]
    image = axis.scatter(
        x, y, c=values, s=2, marker="s", linewidths=0, rasterized=True,
        cmap=cmap, vmin=float(limits[0]), vmax=float(limits[1]),
    )
    axis.axvline(exit_x / dh, color="black", linestyle="--", linewidth=.8)
    axis.set_xlim((0.0, 15.0 if internal_only else 36.0))
    axis.set_ylim((-2.5, 2.5) if internal_only else (-4.0, 4.0))
    axis.set_title(title, fontsize=8)
    axis.set_xlabel(r"$x/D_h$")
    axis.set_ylabel(r"$y/D_h$")
    return image


def render_field_products(cases: dict[str, CaseData], ticks: Sequence[int], output: Path,
                          dh: float, exit_x: float, scales: dict[str, object]) -> list[tuple[Path, tuple[str, ...], tuple[int, ...]]]:
    products: list[tuple[Path, tuple[str, ...], tuple[int, ...]]] = []
    tick_text = "_".join(str(int(round(cases["A"].field_frames[t].t_star))) for t in ticks)
    case_dirs = {"A": "rest-start", "B": "precursor-start", "C": "profile-controlled"}
    for role in "ABC":
        fig, axes = plt.subplots(1, len(ticks), figsize=(5 * len(ticks), 4), constrained_layout=True)
        axes_seq = np.atleast_1d(axes)
        last = None
        for axis, tick in zip(axes_seq, ticks):
            frame = cases[role].field_frames[tick]
            last = field_panel(
                axis, cases[role].slices[tick], quantity="f", dh=dh, exit_x=exit_x,
                limits=(0.0, 1.0), title=f"{CASE_LABELS[role]} | t*={frame.t_star:.3f}",
            )
        fig.colorbar(last, ax=list(axes_seq), label="liquid volume fraction")
        target = output / case_dirs[role] / f"liquid_tstar_{tick_text}.png"
        save(fig, target)
        products.append((target, (role,), tuple(ticks)))

    for quantity, directory, filename, label in (
        ("p", "internal-pressure", f"abc_pressure_tstar_{tick_text}.png", "gauge pressure"),
        ("ux", "internal-velocity", f"abc_axial_velocity_tstar_{tick_text}.png", "axial velocity"),
    ):
        fig, axes = plt.subplots(len(ticks), 3, figsize=(14, 3.7 * len(ticks)), constrained_layout=True)
        last = None
        key = "pressure" if quantity == "p" else "axial_velocity"
        for row_index, tick in enumerate(ticks):
            for column, role in enumerate("ABC"):
                frame = cases[role].field_frames[tick]
                last = field_panel(
                    axes[row_index, column], cases[role].slices[tick], quantity=quantity,
                    dh=dh, exit_x=exit_x, limits=scales[key],
                    title=f"{CASE_LABELS[role]} | t*={frame.t_star:.3f}", internal_only=True,
                )
        fig.colorbar(last, ax=axes.ravel().tolist(), label=label)
        target = output / directory / filename
        save(fig, target)
        products.append((target, tuple("ABC"), tuple(ticks)))

    sequence_paths: list[Path] = []
    for tick in ticks:
        fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
        last = None
        for column, role in enumerate("ABC"):
            frame = cases[role].field_frames[tick]
            last = field_panel(
                axes[column], cases[role].slices[tick], quantity="f", dh=dh,
                exit_x=exit_x, limits=(0.0, 1.0),
                title=f"{CASE_LABELS[role]} | t*={frame.t_star:.3f}",
            )
        fig.colorbar(last, ax=list(axes), label="liquid volume fraction")
        path = output / "matched-comparisons" / "frame-sequence" / f"abc_tstar_{cases['A'].field_frames[tick].t_star:07.3f}.png"
        save(fig, path)
        sequence_paths.append(path)
        products.append((path, tuple("ABC"), (tick,)))

    images = [Image.open(path).convert("RGB") for path in sequence_paths]
    try:
        width = max(image.width for image in images)
        sheet = Image.new("RGB", (width, sum(image.height for image in images)), "white")
        offset = 0
        for image in images:
            sheet.paste(image, (0, offset))
            offset += image.height
        target = output / "contact-sheets" / "abc_liquid_tstar_0_2_4.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target)
    finally:
        for image in images:
            image.close()
    products.append((target, tuple("ABC"), tuple(ticks)))
    return products


def exit_rows(case: CaseData) -> list[dict[str, str]]:
    rows = [row for row in case.metric_rows
            if row.get("plane_label") == "geometric_nozzle_exit" or
            math.isclose(finite(row.get("plane_x_Dh"), "plane_x_Dh"), 15.0, abs_tol=1e-10)]
    if not rows:
        raise ValueError(f"Case {case.role}: no geometric exit metrics")
    selected: dict[int, dict[str, str]] = {}
    for row in rows:
        tick = exact_int(row.get("master_tick"), "hydraulic master_tick")
        if tick in selected:
            raise ValueError(f"Case {case.role}: duplicate exit metric tick {tick}")
        selected[tick] = row
    return [selected[tick] for tick in sorted(selected)]


def render_histories(cases: dict[str, CaseData], output: Path, dh: float) -> list[tuple[Path, tuple[str, ...], tuple[int, ...]]]:
    colors = {"A": "#3366cc", "B": "#009966", "C": "#cc6600"}
    products: list[tuple[Path, tuple[str, ...], tuple[int, ...]]] = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for role in "ABC":
        rows = exit_rows(cases[role])
        tstar = [finite(row["actual_time"], "actual_time") / dh for row in rows]
        for axis, field, label in (
            (axes[0, 0], "Q_l", r"$Q_l$"),
            (axes[0, 1], "J_k_liquid", r"$J_k$ liquid"),
            (axes[1, 0], "J_p", r"$J_p$"),
            (axes[1, 1], "J_total", r"$J_{total}$"),
        ):
            axis.plot(tstar, [finite(row[field], field) for row in rows], color=colors[role], label=CASE_LABELS[role])
            axis.set(xlabel=r"$t^*$", ylabel=label)
            axis.grid(alpha=.25)
    for axis in axes.ravel():
        axis.legend(fontsize=7)
    path = output / "scalar-and-flux-history" / "abc_q_j_pressure.png"
    save(fig, path)
    products.append((path, tuple("ABC"), ()))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for role in "ABC":
        rows = exit_rows(cases[role])
        tstar = [finite(row["actual_time"], "actual_time") / dh for row in rows]
        for axis, field, label in (
            (axes[0], "beta", r"momentum factor $\beta$"),
            (axes[1], "alpha", r"energy factor $\alpha$"),
        ):
            axis.plot(tstar, [finite(row[field], field) for row in rows], color=colors[role], label=CASE_LABELS[role])
            axis.set(xlabel=r"$t^*$", ylabel=label)
            axis.grid(alpha=.25)
            axis.legend(fontsize=7)
    path = output / "scalar-and-flux-history" / "abc_beta_alpha.png"
    save(fig, path)
    products.append((path, tuple("ABC"), ()))
    return products


def profile_rows_at(case: CaseData, tick: int) -> list[dict[str, str]]:
    frame = case.field_frames[tick]
    rows = [row for row in case.profile_rows
            if (row.get("plane_label") == "geometric_nozzle_exit" or
                math.isclose(finite(row.get("plane_x_Dh"), "profile plane_x_Dh"), 15.0, abs_tol=1e-10))
            and exact_int(row.get("field_frame_index"), "profile field index") ==
            exact_int(frame.manifest_row.get("field_frame_index"), "manifest field index")]
    if not rows:
        raise ValueError(f"Case {case.role}: no exit profile at tick {tick}")
    return rows


def render_exit_profiles(cases: dict[str, CaseData], ticks: Sequence[int], output: Path,
                         dh: float) -> tuple[Path, tuple[str, ...], tuple[int, ...]]:
    all_rows = [row for role in "ABC" for tick in ticks for row in profile_rows_at(cases[role], tick)]
    u_values = [finite(row["ux"], "profile ux") for row in all_rows]
    u_limits = [min(u_values), max(u_values)]
    if u_limits[0] == u_limits[1]:
        u_limits[1] += 1e-12
    fig, axes = plt.subplots(len(ticks), 3, figsize=(12, 3.7 * len(ticks)), constrained_layout=True)
    last = None
    for row_index, tick in enumerate(ticks):
        for column, role in enumerate("ABC"):
            rows = profile_rows_at(cases[role], tick)
            y = np.asarray([finite(row["y"], "profile y") / dh for row in rows])
            z = np.asarray([finite(row["z"], "profile z") / dh for row in rows])
            u = np.asarray([finite(row["ux"], "profile ux") for row in rows])
            f = np.asarray([finite(row["f"], "profile f") for row in rows])
            last = axes[row_index, column].scatter(
                y, z, c=u, cmap="magma", vmin=u_limits[0], vmax=u_limits[1],
                s=np.maximum(6.0, 1200.0 * np.asarray([finite(row["intersection_area"], "area") for row in rows])),
                marker="s", linewidths=np.where(f < .5, .5, 0),
                edgecolors=np.where(f < .5, "cyan", "none"), rasterized=True,
            )
            axes[row_index, column].set(
                xlabel=r"$y/D_h$", ylabel=r"$z/D_h$", xlim=(-.8, .8), ylim=(-.4, .4),
                title=f"{CASE_LABELS[role]} | t*={cases[role].field_frames[tick].t_star:.3f}",
            )
            axes[row_index, column].set_aspect("equal")
    fig.colorbar(last, ax=axes.ravel().tolist(), label="exit axial velocity; shared scale")
    target = output / "exit-profiles" / "abc_exit_profiles_tstar_0_2_4.png"
    save(fig, target)
    return target, tuple("ABC"), tuple(ticks)


def render_precursor_convergence(precursor_root: Path, output: Path) -> tuple[Path, tuple[str, ...], tuple[int, ...]]:
    rows = csv_rows(precursor_root / "precursor_history.csv", "precursor history")
    fields = (("Q_l", r"$Q_l$"), ("J_k", r"$J_k$"),
              ("pressure_drop", "pressure drop"), ("profile_l2_change", "profile L2 change"))
    times = [finite(row["t_star"], "precursor t_star") for row in rows]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for axis, (field, label) in zip(axes.ravel(), fields):
        values = [finite(row[field], field) for row in rows]
        if field == "profile_l2_change":
            values = [np.nan if value < 0 else value for value in values]
            axis.axhline(.005, linestyle="--", color="red", label="0.5% criterion")
        axis.plot(times, values, linewidth=1)
        axis.set(xlabel=r"$t^*$", ylabel=label)
        axis.grid(alpha=.25)
        if field == "profile_l2_change":
            axis.legend(fontsize=8)
    fig.suptitle("Pressure-driven internal precursor convergence history")
    target = output / "precursor-convergence" / "precursor_convergence.png"
    save(fig, target)
    return target, (), ()


def import_reference(path: Path):
    spec = importlib.util.spec_from_file_location("steady_r2_poiseuille_reference", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load Poiseuille reference module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_reference(reference_dir: Path, profile_dir: Path, reference_module: Path,
                     output: Path) -> list[tuple[Path, tuple[str, ...], tuple[int, ...]]]:
    reference_path = regular_file(reference_dir / "reference.json", "reference JSON")
    reference = load_json(reference_path, "reference JSON")
    if reference.get("schema") != REFERENCE_SCHEMA:
        raise ValueError("wrong Poiseuille reference schema")
    metrics = reference.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("reference metrics missing")
    bulk = finite(metrics.get("bulk_velocity"), "reference bulk velocity")
    module = import_reference(regular_file(reference_module, "reference module"))
    y = np.linspace(-1.0, 1.0, 161)
    z = np.linspace(-.5, .5, 81)
    yy, zz = np.meshgrid(y, z, indexing="xy")
    exact = module.velocity(yy, zz, modes=256) / bulk
    long_rows = csv_rows(reference_dir / "long_axis_cut.csv", "long-axis cut")
    short_rows = csv_rows(reference_dir / "short_axis_cut.csv", "short-axis cut")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    image = axes[0].contourf(yy, zz, exact, levels=30, vmin=0, vmax=float(np.max(exact)), cmap="magma")
    axes[0].set(xlabel="long-axis coordinate", ylabel="short-axis coordinate", title="Exact 2:1 profile, u/Ub")
    axes[0].set_aspect("equal")
    fig.colorbar(image, ax=axes[0])
    axes[1].plot([finite(row["y"], "y") for row in long_rows],
                 [finite(row["velocity"], "velocity") / bulk for row in long_rows])
    axes[1].set(xlabel="long-axis coordinate", ylabel="u/Ub", title="Long-axis cut")
    axes[2].plot([finite(row["z"], "z") for row in short_rows],
                 [finite(row["velocity"], "velocity") / bulk for row in short_rows])
    axes[2].set(xlabel="short-axis coordinate", ylabel="u/Ub", title="Short-axis cut")
    for axis in axes[1:]:
        axis.grid(alpha=.25)
    target1 = output / "poiseuille-reference" / "exact_profile_and_axis_cuts.png"
    save(fig, target1)

    comparison = load_json(profile_dir / "precursor-poiseuille-profile-comparison.json", "profile comparison")
    if comparison.get("schema") != PROFILE_SCHEMA:
        raise ValueError("wrong precursor-profile comparison schema")
    samples = csv_rows(profile_dir / "precursor-poiseuille-profile-samples.csv", "profile samples")
    near = [row for row in samples if row.get("plane_label") == "near_exit"]
    if not near:
        raise ValueError("no near-exit precursor profile samples")
    patches = [Rectangle(
        (finite(row["y_lower"], "y lower"), finite(row["z_lower"], "z lower")),
        finite(row["y_upper"], "y upper") - finite(row["y_lower"], "y lower"),
        finite(row["z_upper"], "z upper") - finite(row["z_lower"], "z lower"),
    ) for row in near]
    numerical = np.asarray([finite(row["numerical_u_over_bulk"], "numerical normalized u") for row in near])
    expected = np.asarray([finite(row["reference_normalized"], "reference normalized u") for row in near])
    difference = numerical - expected
    common = [float(min(np.min(numerical), np.min(expected))), float(max(np.max(numerical), np.max(expected)))]
    diff_limit = max(float(np.max(np.abs(difference))), 1e-15)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for axis, values, title, limits, cmap in (
        (axes[0], numerical, "Numerical precursor", common, "magma"),
        (axes[1], expected, "Exact cell-average reference", common, "magma"),
        (axes[2], difference, "Numerical - exact", [-diff_limit, diff_limit], "coolwarm"),
    ):
        collection = PatchCollection(patches, cmap=cmap, edgecolor="none")
        collection.set_array(values)
        collection.set_clim(*limits)
        axis.add_collection(collection)
        axis.autoscale_view()
        axis.set_aspect("equal")
        axis.set(xlabel="y", ylabel="z", title=title)
        fig.colorbar(collection, ax=axis)
    fig.suptitle("Near-exit precursor profile versus exact 2:1 Poiseuille reference")
    target2 = output / "poiseuille-reference" / "precursor_vs_exact_profiles.png"
    save(fig, target2)
    return [(target1, (), ()), (target2, (), ())]


def render_transfer(cases: dict[str, CaseData], output: Path) -> tuple[Path, tuple[str, ...], tuple[int, ...]]:
    metric_names = (
        "divergence_l2", "divergence_max", "velocity_impulse_l2",
        "cell_pressure_change_l2", "projection_pressure_adjustment_l2",
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for axis, role in zip(axes, "BC"):
        path = safe_under(cases[role].root, "precursor_transfer_projection.csv", f"Case {role} projection")
        rows = csv_rows(path, f"Case {role} projection")
        phases = [row["phase"] for row in rows]
        for name in metric_names:
            axis.plot(range(len(rows)), [max(abs(finite(row[name], name)), 1e-18) for row in rows], marker="o", label=name)
        axis.set_yscale("log")
        axis.set_xticks(range(len(phases)), phases, rotation=25, ha="right", fontsize=7)
        axis.set_title(CASE_LABELS[role])
        axis.grid(axis="y", alpha=.25)
        axis.legend(fontsize=6)
    target = output / "precursor-transfer" / "transfer_projection_diagnostics.png"
    save(fig, target)
    return target, ("B", "C"), (0,)


def input_records(
    reference_dir: Path, precursor_root: Path, profile_dir: Path,
    reference_module: Path, comparison: Path, cases: dict[str, CaseData],
) -> list[dict[str, object]]:
    paths = [
        reference_dir / "reference.json", reference_dir / "long_axis_cut.csv",
        reference_dir / "short_axis_cut.csv", reference_module,
        precursor_root / "precursor_history.csv",
        precursor_root / "precursor-transfer-cells.csv",
        precursor_root / "precursor-transfer-unsealed.json",
        precursor_root / "precursor-convergence.json",
        profile_dir / "precursor-poiseuille-profile-comparison.json",
        profile_dir / "precursor-poiseuille-profile-samples.csv", comparison,
    ]
    for role in "ABC":
        case = cases[role]
        paths.extend((
            case.package_path, case.metrics_path, case.profiles_path, case.health_path,
            case.root / "field_frame_manifest.csv",
            *[case.field_frames[tick].path for tick in sorted(case.field_frames)],
        ))
        if role in "BC":
            paths.extend((case.root / "precursor_transfer_projection.csv",
                          case.root / "precursor_transfer_projection_acceptance.json"))
        if role == "C":
            paths.extend((case.root / "poiseuille_profile_validation.csv",
                          case.root / "poiseuille_profile_acceptance.json"))
    unique = sorted({regular_file(path, "visual source input") for path in paths}, key=str)
    return [file_record(path) for path in unique]


def write_readme(root: Path, ticks: Sequence[int]) -> Path:
    path = root / "README_VISUAL_REVIEW.txt"
    path.write_text(
        "STEADY PRECURSOR PHYSICAL-REGIME AUDIT — HUMAN VISUAL REVIEW\n\n"
        "Suggested review order:\n- " + "\n- ".join(REVIEW_FIRST) + "\n\n"
        "Cases: A is pressure-driven/rest-start; B is pressure-driven/steady-precursor-start; "
        "C is an explicitly flow-controlled Poiseuille diagnostic, not the primary physical baseline.\n\n"
        f"The matched field sequence contains only observed master ticks {','.join(map(str, ticks))} "
        "(t*=0,2,4). No temporal interpolation or invented frames were used. Pressure and axial-velocity "
        "limits are shared across all displayed A/B/C states; liquid fraction uses [0,1].\n\n"
        "Inspect hydraulic histories and profiles quantitatively before interpreting morphology. Visuals "
        "do not establish stationarity, turbulence, physical Reynolds similarity, convergence, atomization, "
        "physical-model validation, experimental validation, or production readiness.\n",
        encoding="utf-8",
    )
    return path


def write_checksums(root: Path, paths: Iterable[Path]) -> Path:
    target = root / "SHA256SUMS"
    lines = [f"{sha256_file(path)}  {path.relative_to(root)}" for path in sorted(set(paths))]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def validate_manifest(root_arg: Path, manifest_arg: Path) -> dict[str, object]:
    root = root_arg.resolve(strict=True)
    manifest_path = regular_file(manifest_arg, "visual manifest")
    if manifest_path.parent != root:
        raise ValueError("visual manifest must be directly under output root")
    payload = load_json(manifest_path, "visual manifest")
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unsupported visual manifest schema")
    scales = payload.get("global_scales")
    if not isinstance(scales, dict) or scales.get("shared_across_cases") is not True:
        raise ValueError("manifest does not prove shared matched-case scales")
    members = payload.get("members")
    if not isinstance(members, list) or payload.get("member_count") != len(members) or not members:
        raise ValueError("visual manifest member count mismatch")
    member_paths: set[str] = set()
    for number, record in enumerate(members):
        if not isinstance(record, dict):
            raise ValueError(f"manifest member {number} is not an object")
        relative = record.get("path")
        if not isinstance(relative, str) or relative in member_paths:
            raise ValueError("duplicate or malformed manifest member path")
        member_paths.add(relative)
        path = safe_under(root, relative, f"manifest member {relative}")
        if record.get("size_bytes") != path.stat().st_size or record.get("sha256") != sha256_file(path):
            raise ValueError(f"manifest identity mismatch: {relative}")
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.format != "PNG" or [image.width, image.height] != [record.get("width"), record.get("height")]:
                raise ValueError(f"manifest image metadata mismatch: {relative}")
            if image.width < 480 or image.height < 300:
                raise ValueError(f"implausible image dimensions: {relative}")
    first = payload.get("review_first")
    if not isinstance(first, list) or not 2 <= len(first) <= 5 or any(item not in member_paths for item in first):
        raise ValueError("REVIEW_FIRST is not a 2-5 item subset of validated members")
    for key in ("readme", "checksums"):
        record = payload.get(key)
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError(f"missing {key} record")
        path = safe_under(root, record["path"], key)
        if record.get("size_bytes") != path.stat().st_size or record.get("sha256") != sha256_file(path):
            raise ValueError(f"{key} identity mismatch")
    inputs = payload.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("input provenance records missing")
    for record in inputs:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError("malformed input record")
        path = regular_file(Path(record["path"]), "manifest input")
        if record.get("size_bytes") != path.stat().st_size or record.get("sha256") != sha256_file(path):
            raise ValueError(f"visual source input changed: {path}")
    return payload


def render(args: argparse.Namespace) -> Path:
    output = args.output_root
    if output.exists() or output.is_symlink():
        raise ValueError("output root already exists; refusing stale/mixed visual package")
    staging = output.with_name(output.name + ".building")
    if staging.exists() or staging.is_symlink():
        raise ValueError("staging output already exists")
    case_scientific_commit = git_commit(
        args.expected_case_scientific_commit,
        "expected matched-case scientific commit",
    )
    precursor_scientific_commit = git_commit(
        args.expected_precursor_scientific_commit,
        "expected precursor scientific commit",
    )
    ticks = tuple(args.master_ticks)
    if ticks != tuple(sorted(set(ticks))) or ticks != (0, 20, 40):
        raise ValueError("Task 09 requires exactly master ticks 0,20,40")
    if args.dh <= 0 or args.exit_x <= 0 or not math.isclose(args.exit_x / args.dh, 15.0, abs_tol=1e-10):
        raise ValueError("invalid Dh/nozzle-exit geometry")

    cases = {
        role: load_case(
            role, getattr(args, f"case_{role.lower()}_root"),
            getattr(args, f"case_{role.lower()}_package"), ticks, args.dh,
            case_scientific_commit,
        ) for role in "ABC"
    }
    compatibility = {(cases[role].package["source_sha256"], cases[role].package["schedule_sha256"])
                     for role in "ABC"}
    if len(compatibility) != 1:
        raise ValueError("A/B/C source or schedule identity differs")

    comparison = load_json(args.comparison, "matched comparison")
    if comparison.get("schema") != "steady_precursor_matched_comparison_v2":
        raise ValueError("wrong matched comparison schema")
    common = comparison.get("common_horizon")
    if not isinstance(common, dict) or exact_int(common.get("master_tick"), "common horizon tick") < 40:
        raise ValueError("matched comparison does not cover t*=4")
    precursor_root = args.precursor_run_root.resolve(strict=True)
    precursor_meta = load_json(precursor_root / "precursor-transfer-unsealed.json", "precursor metadata")
    convergence = load_json(precursor_root / "precursor-convergence.json", "precursor convergence")
    if (precursor_meta.get("schema") != PRECURSOR_SCHEMA or
            precursor_meta.get("source_commit") != precursor_scientific_commit):
        raise ValueError("precursor metadata identity mismatch")
    if convergence.get("schema") != CONVERGENCE_SCHEMA or convergence.get("pass") is not True:
        raise ValueError("visual package requires a converged precursor")
    profile_dir = args.precursor_profile_dir.resolve(strict=True)
    profile_comparison = load_json(
        profile_dir / "precursor-poiseuille-profile-comparison.json",
        "precursor profile comparison",
    )
    if (profile_comparison.get("schema") != PROFILE_SCHEMA or
            profile_comparison.get("source_commit") != precursor_scientific_commit):
        raise ValueError("precursor profile-comparison identity mismatch")
    reference_dir = args.reference_dir.resolve(strict=True)
    reference_module = regular_file(args.reference_module, "Poiseuille reference module")

    staging.mkdir(parents=True)
    products: list[tuple[Path, tuple[str, ...], tuple[int, ...]]] = []
    scales = shared_limits(cases, ticks, args.exit_x)
    products.extend(render_field_products(cases, ticks, staging, args.dh, args.exit_x, scales))
    products.extend(render_histories(cases, staging, args.dh))
    products.append(render_exit_profiles(cases, ticks, staging, args.dh))
    products.append(render_precursor_convergence(precursor_root, staging))
    products.extend(render_reference(reference_dir, profile_dir, reference_module, staging))
    products.append(render_transfer(cases, staging))

    readme = write_readme(staging, ticks)
    checksum = write_checksums(staging, [item[0] for item in products] + [readme])
    members = [image_record(path, staging, roles=roles, ticks=member_ticks)
               for path, roles, member_ticks in products]
    sources = input_records(
        reference_dir, precursor_root, profile_dir, reference_module,
        args.comparison, cases,
    )
    sources.append(file_record(Path(__file__)))
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "matched_case_scientific_commit": case_scientific_commit,
        "precursor_scientific_commit": precursor_scientific_commit,
        "selected_master_ticks": list(ticks),
        "selected_t_star": [cases["A"].field_frames[tick].t_star for tick in ticks],
        "time_selection": "exact_observed_master_ticks_no_interpolation",
        "global_scales": scales,
        "inputs": sources,
        "member_count": len(members),
        "members": sorted(members, key=lambda item: str(item["path"])),
        "readme": file_record(readme, base=staging),
        "checksums": file_record(checksum, base=staging),
        "review_first": list(REVIEW_FIRST),
        "videos": {
            "status": "not_generated",
            "reason": (
                "only_three_observed_full-field_states_at_t_star_0_2_4; "
                "a_discrete_labeled_frame_sequence_avoids_implied_smooth_evolution"
            ),
        },
        "claim_boundary": (
            "informational deterministic rendering only; no stationarity, turbulence, "
            "dynamic similarity, convergence, atomization, or physical validation claim"
        ),
    }
    manifest_path = staging / "visual-package-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_manifest(staging, manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, output)
    return output / manifest_path.name


def parse_ticks(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(item) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("master ticks must be comma-separated integers") from error


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--reference-dir", type=Path)
    parser.add_argument("--reference-module", type=Path)
    parser.add_argument("--precursor-run-root", type=Path)
    parser.add_argument("--precursor-profile-dir", type=Path)
    for role in "abc":
        parser.add_argument(f"--case-{role}-root", type=Path)
        parser.add_argument(f"--case-{role}-package", type=Path)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--master-ticks", type=parse_ticks, default=(0, 20, 40))
    parser.add_argument("--dh", type=float)
    parser.add_argument("--exit-x", type=float)
    parser.add_argument("--expected-case-scientific-commit")
    parser.add_argument("--expected-precursor-scientific-commit")
    args = parser.parse_args(argv)
    if args.validate_only:
        if args.manifest is None:
            parser.error("--validate-only requires --manifest")
        return args
    required = (
        "reference_dir", "reference_module", "precursor_run_root",
        "precursor_profile_dir", "case_a_root", "case_a_package", "case_b_root",
        "case_b_package", "case_c_root", "case_c_package", "comparison", "dh",
        "exit_x", "expected_case_scientific_commit",
        "expected_precursor_scientific_commit",
    )
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("render mode missing: " + ", ".join("--" + name.replace("_", "-") for name in missing))
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.validate_only:
        payload = validate_manifest(args.output_root, args.manifest)
        print(json.dumps({"status": "pass", "members": payload["member_count"],
                          "manifest": str(args.manifest)}, sort_keys=True))
        return 0
    manifest = render(args)
    print(json.dumps({"status": "pass", "manifest": str(manifest)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
