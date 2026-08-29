#!/usr/bin/env python3
"""Render a fixed-scale transient-mechanism human-review package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


TSTAR_FACTOR = 7.180961047245843


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows(paths: list[Path]) -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as stream:
            collected.extend(csv.DictReader(stream))
    return collected


def find_files(run_dirs: list[Path], name: str) -> list[Path]:
    return [path for run in run_dirs for path in (run / name,) if path.is_file()]


def dedupe(rows_in: list[dict[str, str]], keys: tuple[str, ...]) -> list[dict[str, str]]:
    selected: dict[tuple[object, ...], dict[str, str]] = {}
    for row in rows_in:
        key = tuple(round(float(row[name]), 12) if name in {"t", "plane_x_Dh"} else row[name]
                    for name in keys)
        selected[key] = row
    return [selected[key] for key in sorted(selected)]


def save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_histories(metric_paths: list[Path], health_paths: list[Path], output: Path) -> list[Path]:
    metric_rows = dedupe(rows(metric_paths), ("t", "plane_x_Dh"))
    exit_rows = [row for row in metric_rows if abs(float(row["plane_x_Dh"]) - 15.) < 1e-9]
    if not exit_rows:
        raise ValueError("no geometric-exit hydraulic rows")
    tstar = np.array([float(row["t"]) * TSTAR_FACTOR for row in exit_rows])
    products: list[Path] = []

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(tstar, [float(row["Q_l"]) for row in exit_rows], label=r"$Q_l$")
    axes[0].plot(tstar, [float(row["mdot_l"]) for row in exit_rows], "--", label=r"$\dot m_l$")
    axes[0].set_ylabel("flow / mass flow")
    axes[0].legend()
    for name, label in (("J_k_mixture", r"$J_k$"), ("J_p", r"$J_p$"),
                        ("J_total", r"$J_{total}$")):
        axes[1].plot(tstar, [float(row[name]) for row in exit_rows], label=label)
    axes[1].set(xlabel=r"$t^*=tU_{ref}/D_h$", ylabel="axial flux")
    axes[1].legend()
    for axis in axes:
        axis.grid(alpha=.25)
    fig.suptitle("Corrected full-domain L7-equivalent exit hydraulics")
    path = output / "scalar-and-flux-history" / "true_exit_flow_and_momentum.png"
    save(fig, path)
    products.append(path)

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    axes[0].plot(tstar, [float(row["area_weighted_liquid_velocity"]) for row in exit_rows], label="area weighted")
    axes[0].plot(tstar, [float(row["flux_weighted_liquid_velocity"]) for row in exit_rows], label="flux weighted")
    axes[0].set_ylabel("exit velocity")
    axes[0].legend()
    axes[1].plot(tstar, [float(row["forcing_to_plane_pressure_drop"]) for row in exit_rows])
    axes[1].set_ylabel("forcing-to-exit pressure drop")
    axes[2].plot(tstar, [float(row["liquid_area"]) for row in exit_rows])
    axes[2].set(xlabel=r"$t^*$", ylabel="exit liquid area")
    for axis in axes:
        axis.grid(alpha=.25)
    path = output / "scalar-and-flux-history" / "velocity_pressure_area_history.png"
    save(fig, path)
    products.append(path)

    health_rows = dedupe(rows(health_paths), ("t",)) if health_paths else []
    if health_rows:
        th = np.array([float(row["t"]) * TSTAR_FACTOR for row in health_rows])
        fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
        axes[0].plot(th, [float(row["total_grid_cells"]) for row in health_rows])
        axes[0].set_ylabel("adaptive cells")
        axes[1].plot(th, [float(row["dt"]) for row in health_rows], label="dt")
        axes[1].plot(th, [float(row["DT"]) for row in health_rows], label="DT")
        axes[1].set_ylabel("time step")
        axes[1].legend()
        for name in ("mgp_i", "mgpf_i", "mgu_i"):
            axes[2].plot(th, [float(row[name]) for row in health_rows], label=name)
        axes[2].set(xlabel=r"$t^*$", ylabel="solver iterations")
        axes[2].legend()
        for axis in axes:
            axis.grid(alpha=.25)
        path = output / "amr-and-solver" / "amr_timestep_solver_history.png"
        save(fig, path)
        products.append(path)
    return products


def field_frames(run_dirs: list[Path]) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for run in run_dirs:
        manifest = run / "field_frame_manifest.csv"
        if not manifest.is_file():
            continue
        for row in rows([manifest]):
            field = run / row["filename"]
            if field.is_file() and field.stat().st_size > 0:
                frames.append({"t": float(row["t"]), "tstar": float(row["t"]) * TSTAR_FACTOR,
                               "path": field, "source_sha256": row["source_sha256"]})
    selected: dict[float, dict[str, object]] = {round(float(frame["t"]), 12): frame for frame in frames}
    return [selected[key] for key in sorted(selected)]


def read_midplane(path: Path) -> dict[str, np.ndarray]:
    columns: dict[str, list[float]] = {name: [] for name in ("x", "y", "z", "f", "ux", "p", "Delta", "cs")}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            z, delta = float(row["z"]), float(row["Delta"])
            if abs(z) <= .51 * delta:
                for name in columns:
                    columns[name].append(float(row[name]))
    if not columns["x"]:
        raise ValueError(f"no midplane samples in {path}")
    return {name: np.asarray(values) for name, values in columns.items()}


def render_fields(frames: list[dict[str, object]], output: Path, dh: float,
                  exit_x: float) -> list[Path]:
    if not frames:
        return []
    loaded = [(frame, read_midplane(Path(frame["path"]))) for frame in frames]
    pressure_values = np.concatenate([data["p"][data["cs"] > 1e-8] for _, data in loaded])
    velocity_values = np.concatenate([data["ux"][data["cs"] > 1e-8] for _, data in loaded])
    p_limits = (float(np.nanpercentile(pressure_values, 1)), float(np.nanpercentile(pressure_values, 99)))
    u_limits = (float(np.nanpercentile(velocity_values, 1)), float(np.nanpercentile(velocity_values, 99)))
    products: list[Path] = []
    liquid_paths: list[Path] = []
    for frame, data in loaded:
        tstar = float(frame["tstar"])
        xdh, ydh = data["x"] / dh, data["y"] / dh
        for subdir, stem, values, limits, cmap, label in (
            ("continuation-liquid-views", "liquid", data["f"], (0., 1.), "Blues", "liquid volume fraction"),
            ("internal-pressure", "pressure", data["p"], p_limits, "viridis", "gauge pressure"),
            ("internal-velocity", "axial_velocity", data["ux"], u_limits, "magma", "axial velocity"),
        ):
            fig, axis = plt.subplots(figsize=(12, 4))
            image = axis.scatter(xdh, ydh, c=values, s=2, marker="s", linewidths=0,
                                 cmap=cmap, vmin=limits[0], vmax=limits[1], rasterized=True)
            axis.axvline(exit_x / dh, color="black", linestyle="--", linewidth=1, label="nozzle exit")
            axis.set(xlabel=r"$x/D_h$", ylabel=r"$y/D_h$", xlim=(0., max(xdh)),
                     ylim=(-4., 4.), title=f"full-domain L7-equivalent, t*={tstar:.3f}")
            axis.set_aspect("auto")
            axis.legend(loc="upper right")
            fig.colorbar(image, ax=axis, label=label)
            target = output / subdir / f"{stem}_tstar_{tstar:06.3f}.png"
            save(fig, target)
            products.append(target)
            if subdir == "continuation-liquid-views":
                liquid_paths.append(target)
    if liquid_paths:
        images = [Image.open(path).convert("RGB") for path in liquid_paths]
        width = max(image.width for image in images)
        height = sum(image.height for image in images)
        sheet = Image.new("RGB", (width, height), "white")
        y = 0
        for image in images:
            sheet.paste(image, (0, y))
            y += image.height
        target = output / "contact-sheets" / "corrected_baseline_liquid_timeline.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target)
        for image in images:
            image.close()
        products.append(target)
    return products


def plot_control(control_path: Path | None, output: Path) -> list[Path]:
    if control_path is None:
        return []
    payload = json.loads(control_path.read_text(encoding="utf-8"))
    fields = payload["fields"]["per_field"]
    names = list(fields)
    values = [max(float(fields[name]["relative_l2"]), 1e-18) for name in names]
    fig, axis = plt.subplots(figsize=(9, 5))
    axis.bar(names, values)
    axis.axhline(1e-7, color="red", linestyle="--", label=r"accepted $10^{-7}$ limit")
    axis.set_yscale("log")
    axis.set(ylabel="relative L2", title="Post-repair uninterrupted vs segmented restart control")
    axis.legend()
    axis.grid(axis="y", alpha=.25)
    target = output / "diagnostic-controls" / "restart_equivalence_relative_l2.png"
    save(fig, target)
    return [target]


def validate(products: list[Path], root: Path) -> dict[str, object]:
    members: list[dict[str, object]] = []
    for path in sorted(set(products)):
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"missing or empty visual product: {path}")
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
        if width < 200 or height < 150:
            raise ValueError(f"implausible visual dimensions: {path} {width}x{height}")
        members.append({"path": str(path.relative_to(root)), "size_bytes": path.stat().st_size,
                        "sha256": sha256(path), "width": width, "height": height})
    return {"schema": "internal_nozzle_human_visual_review_manifest_v1",
            "member_count": len(members), "members": members}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", action="append", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--dh", required=True, type=float)
    parser.add_argument("--exit-x", required=True, type=float)
    parser.add_argument("--control-comparison", type=Path)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    metrics = find_files(args.run_dir, "hydraulic_plane_metrics.csv")
    health = find_files(args.run_dir, "solver_health_metrics.csv")
    products = plot_histories(metrics, health, args.output_root)
    products.extend(render_fields(field_frames(args.run_dir), args.output_root, args.dh, args.exit_x))
    products.extend(plot_control(args.control_comparison, args.output_root))
    manifest = validate(products, args.output_root)
    manifest_path = args.output_root / "visual-package-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readme = args.output_root / "README_VISUAL_REVIEW.txt"
    first = [member["path"] for member in manifest["members"][:5]]
    readme.write_text(
        "INTERNAL NOZZLE TRANSIENT-MECHANISM VISUAL REVIEW\n\n"
        "All images are deterministic postprocessing of the corrected full-domain L7-equivalent trajectory.\n"
        "Inspect first:\n- " + "\n- ".join(first) + "\n\n"
        "Look for hydraulic trend, exit-profile evolution, pressure/velocity redistribution, AMR stability, "
        "and agreement of the restart control. Fixed scales are shared across temporal field views.\n\n"
        "Do not infer grid convergence, physical validation, atomization, production readiness, or mathematical "
        "stationarity from these images. Quantitative acceptance is defined only by committed numerical reports.\n",
        encoding="utf-8",
    )
    manifest["readme"] = {"path": readme.name, "size_bytes": readme.stat().st_size,
                          "sha256": sha256(readme)}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "products": len(products),
                      "manifest": str(manifest_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
