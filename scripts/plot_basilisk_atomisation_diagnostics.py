#!/usr/bin/env python3
"""Plot compact diagnostics for long Basilisk atomisation benchmark routes."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-codex")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(row: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default) or default))
    except (TypeError, ValueError):
        return default


def route_label(route_id: str) -> str:
    labels = {
        "official_round_control": "official round control",
        "rectangular_long_modified_benchmark": "rectangular imposed inlet",
    }
    return labels.get(route_id, route_id.replace("_", " "))


def load_routes(media_route_manifest: Path) -> list[dict[str, Any]]:
    manifest = load_json(media_route_manifest)
    routes = []
    for route_id, route in (manifest.get("routes") or {}).items():
        root = Path(route["root"])
        routes.append(
            {
                "route_id": route_id,
                "label": route_label(route_id),
                "role": route.get("role", ""),
                "root": root,
                "frames": read_csv(Path(route.get("frame_csv", root / "raw_frame_summary.csv"))),
                "components": read_csv(Path(route.get("component_csv", root / "raw_component_summary.csv"))),
            }
        )
    return routes


def route_series(route: dict[str, Any], key: str) -> tuple[list[float], list[float]]:
    frames = route["frames"]
    return [as_float(row, "t") for row in frames], [as_float(row, key) for row in frames]


def save_line_plot(path: Path, title: str, ylabel: str, routes: list[dict[str, Any]], keys: list[str]) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    styles = ["-", "--", "-.", ":"]
    for route in routes:
        for index, key in enumerate(keys):
            t, values = route_series(route, key)
            if not t:
                continue
            label = f"{route['label']} {key.replace('_', ' ')}" if len(keys) > 1 else route["label"]
            ax.plot(t, values, styles[index % len(styles)], linewidth=1.8, label=label)
    ax.set_title(title)
    ax.set_xlabel("simulation time")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_size_distribution(path: Path, routes: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for route in routes:
        rows = route["components"]
        if not rows:
            continue
        final_time = max(as_float(row, "t") for row in rows)
        final = [
            as_float(row, "equivalent_diameter")
            for row in rows
            if abs(as_float(row, "t") - final_time) < 1.0e-9 and as_int(row, "credible") > 0
        ]
        if final:
            ax.hist(final, bins=min(24, max(6, len(final) // 3)), alpha=0.55, label=route["label"])
    ax.set_title("Final-frame credible component size proxy")
    ax.set_xlabel("equivalent diameter proxy")
    ax.set_ylabel("component count")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-route-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    routes = load_routes(args.media_route_manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    save_line_plot(
        args.output_dir / "component_history.svg",
        "Credible and separated component history",
        "component count",
        routes,
        ["credible_component_count", "detached_proxy_count"],
    )
    save_line_plot(
        args.output_dir / "interface_growth.svg",
        "Interface proxy growth",
        "growth relative to initial frame",
        routes,
        ["interface_growth"],
    )
    save_line_plot(
        args.output_dir / "active_front.svg",
        "Active front history",
        "active-front x/L0",
        routes,
        ["active_front_over_L0"],
    )
    save_size_distribution(args.output_dir / "size_distribution_final.svg", routes)
    save_line_plot(
        args.output_dir / "conservation.svg",
        "Liquid-volume history",
        "liquid volume error",
        routes,
        ["liquid_volume_error"],
    )
    save_line_plot(
        args.output_dir / "route_cost_comparison.svg",
        "Cumulative computational cost",
        "wall time seconds",
        routes,
        ["wall_time_seconds"],
    )

    manifest = {
        "media_route_manifest": str(args.media_route_manifest),
        "route_count": len(routes),
        "plots": sorted(str(path) for path in args.output_dir.glob("*.svg")),
    }
    (args.output_dir / "diagnostic_plot_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"DIAGNOSTIC_PLOT_MANIFEST={args.output_dir / 'diagnostic_plot_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
