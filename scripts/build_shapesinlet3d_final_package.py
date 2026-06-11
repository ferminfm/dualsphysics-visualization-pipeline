#!/usr/bin/env python3
"""Compose the final 05_ShapesInlet3D scientific-demonstration package.

The script is intentionally post-production only: it consumes already-rendered
PNG frames from previous particle, surface, and analysis passes, then writes
cards, MP4s, a contact sheet, and handoff metadata outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEFAULT_V2_ROOT = Path(
    "/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-showcase-v2"
)
DEFAULT_SURFACE_ROOT = Path(
    "/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-surface-render"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-final-package"
)

WIDTH = 1280
HEIGHT = 720
FPS = 12
BACKGROUND = (6, 11, 15)
FOREGROUND = (238, 246, 250)
MUTED = (190, 210, 220)
ACCENT = (55, 180, 225)
WARNING = (245, 205, 90)


@dataclass(frozen=True)
class SegmentSpec:
    name: str
    source: str
    frames: list[Path]
    repeat: int
    overlay_title: str
    overlay_lines: tuple[str, ...]
    legend: bool = False


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _natural_key(path: Path) -> tuple[object, ...]:
    import re

    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path.name))


def _clean_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for stale in path.glob("*"):
        if stale.is_file() or stale.is_symlink():
            stale.unlink()
        elif stale.is_dir():
            shutil.rmtree(stale)


def _fit_frame(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    scale = max(WIDTH / image.width, HEIGHT / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - WIDTH) // 2)
    top = max(0, (resized.height - HEIGHT) // 2)
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))


def _save_repeated(image: Image.Image, frames_dir: Path, start: int, count: int) -> int:
    index = start
    for _ in range(count):
        image.save(frames_dir / f"frame_{index:05d}.png")
        index += 1
    return index


def _draw_card(title: str, lines: list[str], *, caution: str | None = None) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    x = 86
    y = 92
    draw.rectangle((x, y, x + 9, HEIGHT - 92), fill=ACCENT)
    draw.text((x + 34, y - 4), title, font=_font(42, bold=True), fill=FOREGROUND)
    cursor = y + 78
    for line in lines:
        color = FOREGROUND if line.startswith("Ferm") else MUTED
        draw.text((x + 38, cursor), line, font=_font(24), fill=color)
        cursor += 38
    if caution:
        box_y = HEIGHT - 118
        draw.rounded_rectangle(
            (x + 34, box_y, WIDTH - x, box_y + 50),
            radius=8,
            fill=(15, 22, 28),
            outline=(80, 130, 155),
            width=1,
        )
        draw.text((x + 54, box_y + 13), caution, font=_font(20), fill=WARNING)
    return image


def _section_card(title: str, subtitle: str) -> Image.Image:
    return _draw_card(title, [subtitle], caution=None)


def _draw_overlay(
    image: Image.Image,
    title: str,
    lines: tuple[str, ...],
    *,
    legend: bool = False,
) -> Image.Image:
    image = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    pad = 16
    line_font = _font(17)
    title_font = _font(19, bold=True)
    widths = [draw.textbbox((0, 0), title, font=title_font)[2]]
    widths.extend(draw.textbbox((0, 0), line, font=line_font)[2] for line in lines)
    box_w = min(WIDTH - 60, max(widths) + pad * 2)
    box_h = 36 + len(lines) * 27 + pad
    x = 28
    y = 26
    draw.rounded_rectangle(
        (x, y, x + box_w, y + box_h),
        radius=9,
        fill=(3, 8, 12, 178),
        outline=(80, 150, 185, 135),
        width=1,
    )
    draw.text((x + pad, y + 12), title, font=title_font, fill=FOREGROUND)
    cursor = y + 42
    for line in lines:
        draw.text((x + pad, cursor), line, font=line_font, fill=MUTED)
        cursor += 27

    if legend:
        lx = WIDTH - 356
        ly = 30
        lw = 320
        lh = 72
        draw.rounded_rectangle(
            (lx, ly, lx + lw, ly + lh),
            radius=9,
            fill=(3, 8, 12, 178),
            outline=(80, 150, 185, 135),
            width=1,
        )
        draw.text((lx + 14, ly + 10), "Velocity magnitude view", font=_font(17, bold=True), fill=FOREGROUND)
        gx = lx + 18
        gy = ly + 42
        colors = [(25, 82, 180), (0, 170, 230), (130, 225, 120), (255, 200, 45), (230, 50, 35)]
        steps = 120
        for i in range(steps):
            t = i / max(1, steps - 1)
            scaled = t * (len(colors) - 1)
            low = min(len(colors) - 2, int(scaled))
            frac = scaled - low
            color = tuple(
                round(colors[low][channel] * (1.0 - frac) + colors[low + 1][channel] * frac)
                for channel in range(3)
            )
            draw.line((gx + i * 2, gy, gx + i * 2, gy + 12), fill=color, width=2)
        draw.text((gx, gy + 18), "low", font=_font(13), fill=MUTED)
        draw.text((gx + 206, gy + 18), "high", font=_font(13), fill=MUTED)
    return Image.alpha_composite(image, overlay).convert("RGB")


def _write_video(frames_dir: Path, output: Path, fps: int) -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ERROR: ffmpeg not found")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%05d.png"),
        "-vf",
        "format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "19",
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True)


def _select_range(directory: Path, pattern: str, start: int, stop: int) -> list[Path]:
    files = sorted(directory.glob(pattern), key=_natural_key)
    selected = []
    for path in files:
        import re

        match = re.search(r"(\d{4})(?=\.png$)", path.name)
        if not match:
            continue
        frame = int(match.group(1))
        if start <= frame <= stop:
            selected.append(path)
    if not selected:
        raise SystemExit(f"ERROR: no frames selected from {directory}/{pattern}")
    return selected


def _build_specs(v2_root: Path, surface_root: Path) -> list[SegmentSpec]:
    return [
        SegmentSpec(
            name="raw_particle_provenance",
            source="v2 view_a_frames",
            frames=_select_range(v2_root / "view_a_frames", "view_a_*.png", 20, 91),
            repeat=1,
            overlay_title="SPH particle provenance",
            overlay_lines=(
                "Example: 05_ShapesInlet3D",
                "Representation: PartVTK fluid particles",
                "Final particle count: ~135,627",
            ),
        ),
        SegmentSpec(
            name="reconstructed_surface",
            source="surface_frames",
            frames=sorted((surface_root / "surface_frames").glob("surface_*.png"), key=_natural_key),
            repeat=6,
            overlay_title="Reconstructed free surface",
            overlay_lines=(
                "Post-processing: IsoSurface",
                "Representation: VTK polygon surface",
                "Particle markers hidden",
            ),
        ),
        SegmentSpec(
            name="velocity_magnitude_analysis",
            source="v2 analysis_frames",
            frames=sorted((v2_root / "analysis_frames").glob("analysis_velocity_*.png"), key=_natural_key),
            repeat=3,
            overlay_title="Velocity magnitude view",
            overlay_lines=(
                "Post-analysis: VTK Vel FIELD",
                "Color map: speed magnitude",
                "Interpret as visualization cue, not validation",
            ),
            legend=True,
        ),
    ]


def _render_main_frames(output_root: Path, specs: list[SegmentSpec]) -> int:
    frames_dir = output_root / "final_frames"
    _clean_dir(frames_dir)
    index = 0
    intro = _draw_card(
        "3D Inlet-Flow Scientific Demonstration",
        [
            "Official DualSPHysics example with post-processing and surface reconstruction",
            "Fermín Franco-Medrano, Ph.D.",
            "UABC Ensenada Campus · IMI, Kyushu University",
            "Software: DualSPHysics v5.4 · Blender 4.5.10 LTS · ffmpeg",
            "Hardware: Ubuntu workstation · NVIDIA GeForce RTX 5070 Laptop GPU",
            "Pipeline: GPU SPH simulation → VTK / IsoSurface → headless Blender → ffmpeg",
        ],
        caution="Scientific demonstration — visualization and analysis workflow, not validation",
    )
    index = _save_repeated(intro, frames_dir, index, 6 * FPS)
    for segment in specs:
        if segment.name != "raw_particle_provenance":
            card_title = {
                "reconstructed_surface": "Segment B — reconstructed surface",
                "velocity_magnitude_analysis": "Segment C — analysis view",
            }.get(segment.name, segment.name)
            card_subtitle = {
                "reconstructed_surface": "IsoSurface mesh render from existing DualSPHysics BI4 output",
                "velocity_magnitude_analysis": "Velocity magnitude coloring from existing VTK field data",
            }.get(segment.name, segment.source)
            index = _save_repeated(_section_card(card_title, card_subtitle), frames_dir, index, FPS)
        for frame_path in segment.frames:
            frame = _fit_frame(frame_path)
            frame = _draw_overlay(
                frame,
                segment.overlay_title,
                segment.overlay_lines,
                legend=segment.legend,
            )
            index = _save_repeated(frame, frames_dir, index, segment.repeat)
    outro = _draw_card(
        "Scientific demonstration summary",
        [
            "Example: 05_ShapesInlet3D",
            "Simulation tool: DualSPHysics v5.4 GPU",
            "Post-processing: PartVTK + IsoSurface",
            "Rendering: Blender 4.5.10 LTS",
            "Output class: scientific demonstration",
            "Key elements: particle provenance · surface reconstruction · velocity-field post-analysis",
        ],
        caution="Visualization and workflow demonstration — not validation",
    )
    index = _save_repeated(outro, frames_dir, index, 5 * FPS)
    return index


def _render_clean_frames(output_root: Path, specs: list[SegmentSpec]) -> int:
    frames_dir = output_root / "clean_frames"
    _clean_dir(frames_dir)
    index = 0
    for segment in specs:
        for frame_path in segment.frames:
            frame = _fit_frame(frame_path)
            index = _save_repeated(frame, frames_dir, index, segment.repeat)
    return index


def _make_contact_sheet(output_root: Path) -> Path:
    frames_dir = output_root / "final_frames"
    candidates = [
        (frames_dir / "frame_00000.png", "intro"),
        (frames_dir / "frame_00095.png", "particles"),
        (frames_dir / "frame_00178.png", "surface"),
        (frames_dir / "frame_00260.png", "surface late"),
        (frames_dir / "frame_00315.png", "velocity"),
        (frames_dir / "frame_00410.png", "outro"),
    ]
    existing = [(path, label) for path, label in candidates if path.exists()]
    if len(existing) < 6:
        all_frames = sorted(frames_dir.glob("frame_*.png"), key=_natural_key)
        indexes = [0, len(all_frames) // 5, 2 * len(all_frames) // 5, 3 * len(all_frames) // 5, 4 * len(all_frames) // 5, len(all_frames) - 1]
        existing = [(all_frames[index], f"frame {index}") for index in indexes]

    tile_w, tile_h = 426, 240
    sheet = Image.new("RGB", (tile_w * 3, tile_h * 2), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for i, (path, label) in enumerate(existing[:6]):
        img = Image.open(path).convert("RGB").resize((tile_w, tile_h), Image.Resampling.LANCZOS)
        x = (i % 3) * tile_w
        y = (i // 3) * tile_h
        sheet.paste(img, (x, y))
        draw.rounded_rectangle((x + 10, y + 10, x + 178, y + 43), radius=5, fill=(3, 8, 12))
        draw.text((x + 20, y + 17), label, font=_font(16), fill=FOREGROUND)
    output = output_root / "dualsphysics_shapesinlet3d_final_contact_sheet.png"
    sheet.save(output)
    return output


def _hash_frames(frames_dir: Path) -> dict[str, object]:
    frames = sorted(frames_dir.glob("frame_*.png"), key=_natural_key)
    hashes = []
    for path in frames:
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    return {"count": len(frames), "unique_hashes": len(set(hashes))}


def _write_manifest(
    output_root: Path,
    specs: list[SegmentSpec],
    final_mp4: Path,
    clean_mp4: Path,
    contact_sheet: Path,
    final_frame_count: int,
    clean_frame_count: int,
) -> None:
    manifest = output_root / "artifact_manifest.txt"
    lines = [
        "DualSPHysics 05_ShapesInlet3D final scientific-demonstration package",
        "",
        f"Output root: {output_root}",
        "Source segments:",
    ]
    for spec in specs:
        lines.append(f"- {spec.name}: {spec.source}, {len(spec.frames)} frames, repeat {spec.repeat}")
    lines.extend(
        [
            "",
            "Generated artifacts:",
            f"- {final_mp4} ({final_mp4.stat().st_size} bytes)",
            f"- {clean_mp4} ({clean_mp4.stat().st_size} bytes)",
            f"- {contact_sheet} ({contact_sheet.stat().st_size} bytes)",
            f"- final_frames: {final_frame_count} PNG frames",
            f"- clean_frames: {clean_frame_count} PNG frames",
            "",
            "Caveat: scientific demonstration and visualization workflow, not validation.",
        ]
    )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_handoff(
    output_root: Path,
    specs: list[SegmentSpec],
    final_mp4: Path,
    clean_mp4: Path,
    contact_sheet: Path,
    final_frame_count: int,
    clean_frame_count: int,
) -> None:
    segments = [
        {
            "name": spec.name,
            "source": spec.source,
            "source_frame_count": len(spec.frames),
            "repeat": spec.repeat,
        }
        for spec in specs
    ]
    summary = {
        "status": "success",
        "final_mp4_path": str(final_mp4),
        "clean_mp4_path": str(clean_mp4),
        "contact_sheet_path": str(contact_sheet),
        "segments_used": segments,
        "surface_segment_included": True,
        "particle_segment_included": True,
        "analysis_segment_included": True,
        "visual_quality": "public_showcase_candidate",
        "repo_changed": False,
        "commit_hash": "",
        "exact_blocker": "",
        "next_step": "Manual review of final MP4; if accepted, use this as the primary public scientific-demonstration artifact.",
        "no_push_confirmed": True,
    }
    (output_root / "CODEX_FINAL_PACKAGE_SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    report = f"""# Final DualSPHysics 05_ShapesInlet3D Scientific Demonstration Package

## Status
Success. The package combines already-generated particle, reconstructed-surface,
and velocity-colored analysis frames. DualSPHysics was not rerun.

## Outputs
- Main final video: `{final_mp4}`
- Clean companion video: `{clean_mp4}`
- Contact sheet: `{contact_sheet}`
- Artifact manifest: `{output_root / "artifact_manifest.txt"}`
- Summary JSON: `{output_root / "CODEX_FINAL_PACKAGE_SUMMARY.json"}`

## Segments
- Segment A: raw SPH particle provenance from fixed-camera View A.
- Segment B: reconstructed free-surface views from the IsoSurface render pass.
- Segment C: velocity magnitude analysis view from existing VTK `Vel` field data.

## Frame Summary
- Final video frames: {final_frame_count} at {FPS} fps.
- Clean video frames: {clean_frame_count} at {FPS} fps.
- Final frame hash sanity: {_hash_frames(output_root / "final_frames")}
- Clean frame hash sanity: {_hash_frames(output_root / "clean_frames")}

## Visual Quality Verdict
Public showcase candidate after manual review. The surface segment is the visual
centerpiece; the raw particle segment preserves solver provenance; and the
analysis segment shows a compact post-processing view.

## Caveat
This is an official DualSPHysics 3D inlet/open-boundary scientific
demonstration. It is not fully atomized spray validation, statistically
stationary spray validation, production CFD, or experimental agreement.
"""
    (output_root / "CODEX_FINAL_PACKAGE_REPORT.md").write_text(report, encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2-root", type=Path, default=DEFAULT_V2_ROOT)
    parser.add_argument("--surface-root", type=Path, default=DEFAULT_SURFACE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    specs = _build_specs(args.v2_root, args.surface_root)
    final_frame_count = _render_main_frames(args.output_root, specs)
    clean_frame_count = _render_clean_frames(args.output_root, specs)

    final_mp4 = args.output_root / "dualsphysics_shapesinlet3d_final_scientific_demo.mp4"
    clean_mp4 = args.output_root / "dualsphysics_shapesinlet3d_final_clean.mp4"
    _write_video(args.output_root / "final_frames", final_mp4, FPS)
    _write_video(args.output_root / "clean_frames", clean_mp4, FPS)
    contact_sheet = _make_contact_sheet(args.output_root)

    _write_manifest(
        args.output_root,
        specs,
        final_mp4,
        clean_mp4,
        contact_sheet,
        final_frame_count,
        clean_frame_count,
    )
    _write_handoff(
        args.output_root,
        specs,
        final_mp4,
        clean_mp4,
        contact_sheet,
        final_frame_count,
        clean_frame_count,
    )
    print(f"FINAL_MP4={final_mp4}")
    print(f"CLEAN_MP4={clean_mp4}")
    print(f"CONTACT_SHEET={contact_sheet}")
    print(f"FINAL_FRAMES={final_frame_count}")
    print(f"CLEAN_FRAMES={clean_frame_count}")


if __name__ == "__main__":
    main()
