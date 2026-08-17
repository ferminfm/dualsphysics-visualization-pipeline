#!/usr/bin/env python3
"""Assemble scientific media from completed Basilisk physical frames."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-codex")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont


CANVAS = (1920, 1080)
FPS = 12


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def route_label(route_id: str) -> str:
    labels = {
        "official_round_control": "Official circular control",
        "rectangular_long_modified_benchmark": "2:1 rectangular imposed-inlet benchmark",
    }
    return labels.get(route_id, route_id.replace("_", " ").title())


def route_short(route_id: str) -> str:
    return "rectangular" if "rectangular" in route_id else "round"


def load_route_specs(media_route_manifest: Path) -> list[dict[str, Any]]:
    manifest = load_json(media_route_manifest)
    specs = []
    for route_id, route in (manifest.get("routes") or {}).items():
        root = Path(route["root"])
        visual_manifest = Path(route.get("frame_manifest", root / "visual_frame_manifest.json"))
        surface_manifest = Path(route.get("surface_manifest", root / "surface_manifest.json"))
        frame_csv = Path(route.get("frame_csv", root / "raw_frame_summary.csv"))
        component_csv = Path(route.get("component_csv", root / "raw_component_summary.csv"))
        frames = load_json(visual_manifest).get("frames", [])
        frame_rows = read_csv(frame_csv)
        frame_by_index = {as_int(row, "frame_index"): row for row in frame_rows}
        specs.append(
            {
                "route_id": route_id,
                "label": route_label(route_id),
                "role": route.get("role", ""),
                "root": root,
                "visual_manifest": visual_manifest,
                "surface_manifest": surface_manifest,
                "frame_csv": frame_csv,
                "component_csv": component_csv,
                "frames": frames,
                "frame_rows": frame_rows,
                "frame_by_index": frame_by_index,
                "components": read_csv(component_csv),
                "surface_manifest_data": load_json(surface_manifest),
                "imposed_inlet_boundary": bool(route.get("imposed_inlet_boundary")),
                "resolution_caveat": bool(route.get("resolution_caveat")),
            }
        )
    return specs


def source_frame_path(route: dict[str, Any], frame: dict[str, Any]) -> Path:
    path = Path(frame.get("filename", ""))
    return path if path.is_absolute() else route["root"] / path


def surface_path(route: dict[str, Any], record: dict[str, Any]) -> Path:
    filename = record.get("filename") or record.get("path") or ""
    path = Path(filename)
    if path.is_absolute():
        return path
    candidates = [route["root"] / path, route["root"] / "surfaces" / path.name]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def audit_route(route: dict[str, Any]) -> dict[str, Any]:
    frames = route["frames"]
    indices = [as_int(frame, "frame_index") for frame in frames]
    expected = list(range(min(indices), max(indices) + 1)) if indices else []
    source_paths = [source_frame_path(route, frame) for frame in frames]
    missing_frames = [str(path) for path in source_paths if not path.exists() or path.stat().st_size <= 0]
    surfaces = route["surface_manifest_data"].get("surfaces") or []
    surface_paths = [surface_path(route, record) for record in surfaces]
    missing_surfaces = [str(path) for path in surface_paths if not path.exists() or path.stat().st_size <= 0]
    times = [as_float(frame, "time") for frame in frames]
    return {
        "route_id": route["route_id"],
        "label": route["label"],
        "role": route["role"],
        "root": str(route["root"]),
        "frame_count": len(frames),
        "first_time": min(times) if times else None,
        "final_time": max(times) if times else None,
        "first_index": min(indices) if indices else None,
        "last_index": max(indices) if indices else None,
        "index_sequence_complete": indices == expected,
        "missing_indices": sorted(set(expected) - set(indices)),
        "missing_or_empty_native_frames": missing_frames,
        "surface_count": len(surfaces),
        "missing_or_empty_surfaces": missing_surfaces,
        "surface_sequence_ready": bool(surfaces) and not missing_surfaces,
        "visual_manifest_sha256": sha256(route["visual_manifest"]) if route["visual_manifest"].exists() else "",
        "surface_manifest_sha256": sha256(route["surface_manifest"]) if route["surface_manifest"].exists() else "",
    }


def draw_overlay(
    image: Image.Image,
    lines: list[str],
    anchor: tuple[int, int] = (24, 24),
    fill: tuple[int, int, int, int] = (0, 0, 0, 190),
) -> Image.Image:
    image = image.convert("RGBA")
    draw = ImageDraw.Draw(image)
    text_font = font(30)
    small_font = font(24)
    fonts = [text_font] + [small_font] * (len(lines) - 1)
    widths = []
    heights = []
    for text, text_font_i in zip(lines, fonts):
        box = draw.textbbox((0, 0), text, font=text_font_i)
        widths.append(box[2] - box[0])
        heights.append(box[3] - box[1])
    x, y = anchor
    pad = 14
    box_w = max(widths) + 2 * pad if widths else 0
    box_h = sum(heights) + 10 * (len(lines) - 1) + 2 * pad if heights else 0
    draw.rectangle((x, y, x + box_w, y + box_h), fill=fill)
    ty = y + pad
    for text, text_font_i, height in zip(lines, fonts, heights):
        draw.text((x + pad, ty), text, fill=(255, 255, 255, 255), font=text_font_i)
        ty += height + 10
    return image.convert("RGB")


def fit_canvas(source: Image.Image) -> Image.Image:
    source = source.convert("RGB")
    canvas = Image.new("RGB", CANVAS, (255, 255, 255))
    scale = min(CANVAS[0] / source.width, CANVAS[1] / source.height)
    resized = source.resize((int(source.width * scale), int(source.height * scale)), Image.Resampling.BICUBIC)
    x = (CANVAS[0] - resized.width) // 2
    y = (CANVAS[1] - resized.height) // 2
    canvas.paste(resized, (x, y))
    return canvas


def metrics_lines(route: dict[str, Any], frame: dict[str, Any]) -> list[str]:
    idx = as_int(frame, "frame_index")
    row = route["frame_by_index"].get(idx, {})
    t = as_float(frame, "time")
    lines = [
        f"{route['label']}",
        f"t={t:.2f}, frame={idx:04d}, maxlevel={frame.get('maxlevel', '')}",
        f"credible={as_int(row, 'credible_component_count')}, separated={as_int(row, 'detached_proxy_count')}, front={as_float(row, 'active_front_over_L0'):.3f}, interface growth={as_float(row, 'interface_growth'):.1f}",
        "au=0.05, T0=0.1; internal scientific media; public_ready=false",
    ]
    if route["imposed_inlet_boundary"]:
        lines.append("Rectangular route: imposed inlet profile, not internal-nozzle flow")
    if route["resolution_caveat"]:
        lines.append("Resolution-sensitive comparison route")
    return lines


def compact_metric_lines(route: dict[str, Any], frame: dict[str, Any]) -> list[str]:
    idx = as_int(frame, "frame_index")
    row = route["frame_by_index"].get(idx, {})
    lines = [
        f"cred={as_int(row, 'credible_component_count')}, sep={as_int(row, 'detached_proxy_count')}",
        f"front={as_float(row, 'active_front_over_L0'):.3f}, interface={as_float(row, 'interface_growth'):.1f}",
        "au=0.05, T0=0.1; public_ready=false",
    ]
    if route["imposed_inlet_boundary"]:
        lines.append("imposed inlet; not internal-nozzle flow")
    if route["resolution_caveat"]:
        lines.append("resolution-sensitive comparison")
    return lines


def native_overlay_lines(route: dict[str, Any], frame: dict[str, Any]) -> list[str]:
    t = as_float(frame, "time")
    return [
        route["label"],
        f"t={t:.2f}, frame={as_int(frame, 'frame_index'):04d}, maxlevel={frame.get('maxlevel', '')}",
        *compact_metric_lines(route, frame),
    ]


def run_ffmpeg(frame_dir: Path, output: Path, fps: int = FPS) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    result: dict[str, Any] = {"ffmpeg": ffmpeg or "", "output": str(output), "fps": fps}
    if not ffmpeg:
        result["returncode"] = 127
        return result
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frame_dir / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    proc = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result.update(
        {
            "command": command,
            "returncode": proc.returncode,
            "stderr_tail": proc.stderr[-4000:],
            "exists": output.exists(),
            "size_bytes": output.stat().st_size if output.exists() else 0,
        }
    )
    return result


def ffprobe(path: Path) -> dict[str, Any]:
    exe = shutil.which("ffprobe")
    if not exe or not path.exists():
        return {}
    command = [
        exe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,nb_read_frames,duration,pix_fmt",
        "-count_frames",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return {"returncode": proc.returncode, "stderr": proc.stderr[-1000:]}
    return json.loads(proc.stdout)


def assemble_route_video(route: dict[str, Any], media_dir: Path, work_dir: Path, mapping_rows: list[dict[str, Any]]) -> dict[str, Any]:
    name = "rectangular_profile" if "rectangular" in route["route_id"] else "official_round"
    frame_dir = work_dir / f"{name}_native"
    shutil.rmtree(frame_dir, ignore_errors=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    for output_index, frame in enumerate(route["frames"]):
        source = source_frame_path(route, frame)
        image = fit_canvas(Image.open(source))
        image = draw_overlay(image, native_overlay_lines(route, frame), (1020, 760))
        image.save(frame_dir / f"frame_{output_index:04d}.png")
        mapping_rows.append(
            {
                "video_id": f"{name}_full_length_native",
                "output_frame_index": output_index,
                "route": route["route_id"],
                "source_frame_index": frame.get("frame_index"),
                "source_time": frame.get("time"),
                "source_iteration": frame.get("iteration"),
                "source_frame_path": str(source),
                "maxlevel": frame.get("maxlevel"),
                "manifest_hash": sha256(route["visual_manifest"]),
                "hold_or_duplication": "none",
            }
        )
    video = media_dir / f"{name}_full_length_native.mp4"
    result = run_ffmpeg(frame_dir, video)
    result["ffprobe"] = ffprobe(video)
    result["frame_count"] = len(route["frames"])
    result["video_id"] = f"{name}_full_length_native"
    create_contact_sheet(route, media_dir / f"{name}_contact_sheet.png")
    return result


def create_contact_sheet(route: dict[str, Any], output: Path) -> None:
    frames = route["frames"]
    cols = 11
    rows = math.ceil(len(frames) / cols)
    tile = (320, 180)
    sheet = Image.new("RGB", (cols * tile[0], rows * tile[1]), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    text_font = font(16)
    for n, frame in enumerate(frames):
        image = Image.open(source_frame_path(route, frame)).convert("RGB")
        image.thumbnail((tile[0], tile[1]), Image.Resampling.BICUBIC)
        x = (n % cols) * tile[0]
        y = (n // cols) * tile[1]
        sheet.paste(image, (x + (tile[0] - image.width) // 2, y + (tile[1] - image.height) // 2))
        draw.rectangle((x, y, x + tile[0], y + 24), fill=(0, 0, 0))
        draw.text((x + 6, y + 4), f"{route_short(route['route_id'])} t={as_float(frame, 'time'):.2f}", fill=(255, 255, 255), font=text_font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def assemble_comparison(round_route: dict[str, Any], rect_route: dict[str, Any], media_dir: Path, work_dir: Path, mapping_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_time_round = {round(as_float(frame, "time"), 8): frame for frame in round_route["frames"]}
    by_time_rect = {round(as_float(frame, "time"), 8): frame for frame in rect_route["frames"]}
    exact_times = sorted(set(by_time_round) & set(by_time_rect))
    frame_dir = work_dir / "round_vs_rectangular"
    shutil.rmtree(frame_dir, ignore_errors=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    for output_index, t in enumerate(exact_times):
        rf = by_time_round[t]
        xf = by_time_rect[t]
        left = Image.open(source_frame_path(round_route, rf)).convert("RGB").resize((960, 540), Image.Resampling.BICUBIC)
        right = Image.open(source_frame_path(rect_route, xf)).convert("RGB").resize((960, 540), Image.Resampling.BICUBIC)
        canvas = Image.new("RGB", CANVAS, (255, 255, 255))
        canvas.paste(left, (0, 210))
        canvas.paste(right, (960, 210))
        lines = [
            "Round vs rectangular exact-time comparison",
            f"t={t:.2f}, maxlevel={rf.get('maxlevel', '')}; au=0.05, T0=0.1",
            "Left: official circular control. Right: 2:1 rectangular imposed inlet, resolution-sensitive comparison.",
        ]
        canvas = draw_overlay(canvas, lines, (24, 24))
        canvas = draw_overlay(canvas, compact_metric_lines(round_route, rf), (24, 780), (0, 0, 0, 180))
        canvas = draw_overlay(canvas, compact_metric_lines(rect_route, xf), (984, 780), (0, 0, 0, 180))
        canvas.save(frame_dir / f"frame_{output_index:04d}.png")
        for route, frame in ((round_route, rf), (rect_route, xf)):
            mapping_rows.append(
                {
                    "video_id": "round_vs_rectangular_time_aligned",
                    "output_frame_index": output_index,
                    "route": route["route_id"],
                    "source_frame_index": frame.get("frame_index"),
                    "source_time": frame.get("time"),
                    "source_iteration": frame.get("iteration"),
                    "source_frame_path": str(source_frame_path(route, frame)),
                    "maxlevel": frame.get("maxlevel"),
                    "manifest_hash": sha256(route["visual_manifest"]),
                    "hold_or_duplication": "none",
                }
            )
    video = media_dir / "round_vs_rectangular_time_aligned.mp4"
    result = run_ffmpeg(frame_dir, video)
    result["ffprobe"] = ffprobe(video)
    result["exact_time_pair_count"] = len(exact_times)
    result["video_id"] = "round_vs_rectangular_time_aligned"
    create_comparison_contact_sheet(round_route, rect_route, exact_times, media_dir / "round_vs_rectangular_contact_sheet.png")
    return result


def create_comparison_contact_sheet(round_route: dict[str, Any], rect_route: dict[str, Any], exact_times: list[float], output: Path) -> None:
    by_time_round = {round(as_float(frame, "time"), 8): frame for frame in round_route["frames"]}
    by_time_rect = {round(as_float(frame, "time"), 8): frame for frame in rect_route["frames"]}
    sample = exact_times[:: max(1, len(exact_times) // 20)]
    cols = 5
    tile = (384, 216)
    rows = math.ceil(len(sample) / cols)
    sheet = Image.new("RGB", (cols * tile[0], rows * tile[1]), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    text_font = font(15)
    for n, t in enumerate(sample):
        left = Image.open(source_frame_path(round_route, by_time_round[t])).convert("RGB").resize((tile[0] // 2, tile[1]), Image.Resampling.BICUBIC)
        right = Image.open(source_frame_path(rect_route, by_time_rect[t])).convert("RGB").resize((tile[0] // 2, tile[1]), Image.Resampling.BICUBIC)
        x = (n % cols) * tile[0]
        y = (n // cols) * tile[1]
        sheet.paste(left, (x, y))
        sheet.paste(right, (x + tile[0] // 2, y))
        draw.rectangle((x, y, x + tile[0], y + 24), fill=(0, 0, 0))
        draw.text((x + 6, y + 4), f"exact t={t:.2f}", fill=(255, 255, 255), font=text_font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def assemble_onset_video(route: dict[str, Any], media_dir: Path, work_dir: Path, onset: float, mapping_rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame_dir = work_dir / "topology_onset_detail"
    shutil.rmtree(frame_dir, ignore_errors=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames = [frame for frame in route["frames"] if onset - 0.12 <= as_float(frame, "time") <= onset + 0.20]
    for output_index, frame in enumerate(frames):
        image = fit_canvas(Image.open(source_frame_path(route, frame)))
        lines = native_overlay_lines(route, frame)
        lines.insert(1, f"onset detail; audit onset t={onset:.2f}")
        image = draw_overlay(image, lines, (1020, 760))
        image.save(frame_dir / f"frame_{output_index:04d}.png")
        mapping_rows.append(
            {
                "video_id": "topology_onset_detail",
                "output_frame_index": output_index,
                "route": route["route_id"],
                "source_frame_index": frame.get("frame_index"),
                "source_time": frame.get("time"),
                "source_iteration": frame.get("iteration"),
                "source_frame_path": str(source_frame_path(route, frame)),
                "maxlevel": frame.get("maxlevel"),
                "manifest_hash": sha256(route["visual_manifest"]),
                "hold_or_duplication": "none",
            }
        )
    video = media_dir / "topology_onset_detail.mp4"
    result = run_ffmpeg(frame_dir, video, fps=6)
    result["ffprobe"] = ffprobe(video)
    result["frame_count"] = len(frames)
    result["video_id"] = "topology_onset_detail"
    return result


def build_cross_section_proxy(route: dict[str, Any], output_csv: Path) -> list[dict[str, Any]]:
    rows = read_csv(route["root"] / "raw_interface_cells.csv")
    stations = [0.20, 0.40, 0.60]
    grouped: dict[tuple[int, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        x = as_float(row, "x")
        delta = as_float(row, "Delta", 0.0)
        for station in stations:
            if abs(x - station) <= max(2.0 * delta, 0.012):
                grouped[(as_int(row, "frame_index"), station)].append(row)
    out_rows = []
    for frame in route["frames"]:
        idx = as_int(frame, "frame_index")
        for station in stations:
            sample = grouped.get((idx, station), [])
            if not sample:
                out_rows.append({"frame_index": idx, "t": frame.get("time"), "station_x": station, "sample_count": 0})
                continue
            weights = [as_float(row, "f") * as_float(row, "Delta") ** 2 for row in sample]
            total = sum(weights)
            cy = sum(as_float(row, "y") * w for row, w in zip(sample, weights)) / total if total else 0.0
            cz = sum(as_float(row, "z") * w for row, w in zip(sample, weights)) / total if total else 0.0
            ys = [as_float(row, "y") for row in sample]
            zs = [as_float(row, "z") for row in sample]
            y_extent = max(ys) - min(ys) if ys else 0.0
            z_extent = max(zs) - min(zs) if zs else 0.0
            aspect = y_extent / z_extent if z_extent else 0.0
            out_rows.append(
                {
                    "frame_index": idx,
                    "t": frame.get("time"),
                    "station_x": station,
                    "sample_count": len(sample),
                    "area_proxy": total,
                    "centroid_y": cy,
                    "centroid_z": cz,
                    "aspect_y_over_z": aspect,
                }
            )
    write_csv(
        output_csv,
        out_rows,
        ["frame_index", "t", "station_x", "sample_count", "area_proxy", "centroid_y", "centroid_z", "aspect_y_over_z"],
    )
    return out_rows


def assemble_cross_section_video(route: dict[str, Any], media_dir: Path, work_dir: Path, data_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in data_rows:
        by_frame[as_int(row, "frame_index")].append(row)
    frame_dir = work_dir / "cross_section_evolution"
    shutil.rmtree(frame_dir, ignore_errors=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    for output_index, frame in enumerate(route["frames"]):
        idx = as_int(frame, "frame_index")
        history = [row for row in data_rows if as_int(row, "frame_index") <= idx and as_int(row, "sample_count") > 0]
        fig, axes = plt.subplots(1, 3, figsize=(12.8, 7.2))
        for ax, key, title in zip(axes, ["area_proxy", "centroid_y", "aspect_y_over_z"], ["area proxy", "centroid y", "aspect y/z"]):
            for station in [0.20, 0.40, 0.60]:
                subset = [row for row in history if abs(as_float(row, "station_x") - station) < 1.0e-9]
                ax.plot([as_float(row, "t") for row in subset], [as_float(row, key) for row in subset], label=f"x={station:.2f}")
            ax.set_title(title)
            ax.set_xlabel("time")
            ax.grid(True, alpha=0.3)
        axes[0].legend(fontsize=8)
        fig.suptitle(f"{route['label']} cross-section proxy from exported interface cells, t={as_float(frame, 'time'):.2f}")
        fig.tight_layout()
        fig.savefig(frame_dir / f"frame_{output_index:04d}.png", dpi=150)
        plt.close(fig)
    video = media_dir / "cross_section_evolution.mp4"
    result = run_ffmpeg(frame_dir, video, fps=12)
    result["ffprobe"] = ffprobe(video)
    result["frame_count"] = len(route["frames"])
    result["video_id"] = "cross_section_evolution"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-route-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--topology-onset-time", type=float, default=0.48)
    args = parser.parse_args()

    media_dir = args.output_root / "scientific_media"
    work_dir = args.output_root / "work_frames"
    media_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    routes = load_route_specs(args.media_route_manifest)
    audits = [audit_route(route) for route in routes]
    mapping_rows: list[dict[str, Any]] = []
    videos = []
    for route in routes:
        videos.append(assemble_route_video(route, media_dir, work_dir, mapping_rows))

    round_route = next((route for route in routes if route["route_id"] == "official_round_control"), None)
    rect_route = next((route for route in routes if "rectangular" in route["route_id"]), None)
    if round_route and rect_route:
        videos.append(assemble_comparison(round_route, rect_route, media_dir, work_dir, mapping_rows))
    if round_route:
        videos.append(assemble_onset_video(round_route, media_dir, work_dir, args.topology_onset_time, mapping_rows))
        cross_rows = build_cross_section_proxy(round_route, media_dir / "cross_section_proxy.csv")
        videos.append(assemble_cross_section_video(round_route, media_dir, work_dir, cross_rows))

    mapping_path = media_dir / "PHYSICAL_FRAME_MAPPING.csv"
    write_csv(
        mapping_path,
        mapping_rows,
        [
            "video_id",
            "output_frame_index",
            "route",
            "source_frame_index",
            "source_time",
            "source_iteration",
            "source_frame_path",
            "maxlevel",
            "manifest_hash",
            "hold_or_duplication",
        ],
    )
    manifest = {
        "generated_at_utc": utc_now(),
        "media_route_manifest": str(args.media_route_manifest),
        "output_root": str(args.output_root),
        "canvas": {"width": CANVAS[0], "height": CANVAS[1]},
        "fps": FPS,
        "route_audits": audits,
        "videos": videos,
        "contact_sheets": sorted(str(path) for path in media_dir.glob("*contact_sheet.png")),
        "physical_frame_mapping": str(mapping_path),
        "all_primary_physical_frames_included": any(
            audit["route_id"] == "official_round_control" and audit["frame_count"] == 101 and not audit["missing_or_empty_native_frames"]
            for audit in audits
        ),
        "true_surface_sequence_ready": any(
            audit["route_id"] == "official_round_control" and audit["surface_sequence_ready"] for audit in audits
        ),
    }
    write_json(media_dir / "SCIENTIFIC_MEDIA_MANIFEST.json", manifest)
    write_json(args.output_root / "FRAME_COMPLETENESS_AUDIT.json", {"generated_at_utc": utc_now(), "routes": audits})
    write_json(
        args.output_root / "MEDIA_INPUT_MANIFEST.json",
        {
            "generated_at_utc": utc_now(),
            "media_route_manifest": str(args.media_route_manifest),
            "routes": [
                {
                    "route_id": route["route_id"],
                    "root": str(route["root"]),
                    "visual_manifest": str(route["visual_manifest"]),
                    "surface_manifest": str(route["surface_manifest"]),
                    "frame_csv": str(route["frame_csv"]),
                    "component_csv": str(route["component_csv"]),
                }
                for route in routes
            ],
        },
    )
    print(f"SCIENTIFIC_MEDIA_MANIFEST={media_dir / 'SCIENTIFIC_MEDIA_MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
