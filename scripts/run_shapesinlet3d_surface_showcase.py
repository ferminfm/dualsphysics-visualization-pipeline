#!/usr/bin/env python3
"""Build a surface-render showcase from an existing ShapesInlet3D run.

This script does not run DualSPHysics. It postprocesses existing BI4 files with
the official IsoSurface tool, renders the generated legacy VTK surface meshes
with Blender, and assembles small MP4/contact-sheet artifacts outside Git.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CASE_DIR = Path(
    "/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official/"
    "DualSPHysics_v5.4/examples/inletoutlet/05_ShapesInlet3D"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-surface-render"
)
DEFAULT_ISOSURFACE = Path(
    "/home/franco/opt/dualsphysics-full-package-20260611/"
    "DualSPHysics_v5.4/bin/linux/IsoSurface_linux64"
)
DEFAULT_BLENDER = Path("/home/franco/bin/blender-portable")


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    case_dir: Path
    output_root: Path
    isosurface: Path
    blender: Path

    @property
    def data_dir(self) -> Path:
        return self.case_dir / "CaseShapesInlet3D_out/data"

    @property
    def particles_dir(self) -> Path:
        return self.case_dir / "CaseShapesInlet3D_out/particles"

    @property
    def case_xml(self) -> Path:
        return self.case_dir / "CaseShapesInlet3D_out/CaseShapesInlet3D.xml"

    @property
    def iso_dir(self) -> Path:
        return self.output_root / "surface_vtk"

    @property
    def frames_dir(self) -> Path:
        return self.output_root / "surface_frames"

    @property
    def logs_dir(self) -> Path:
        return self.output_root / "logs"


def _frame_numbers(spec: str) -> list[int]:
    if ":" in spec:
        parts = [int(part) for part in spec.split(":")]
        if len(parts) != 3:
            raise argparse.ArgumentTypeError("frame range must be start:stop:step")
        start, stop, step = parts
        if step <= 0:
            raise argparse.ArgumentTypeError("frame step must be positive")
        return list(range(start, stop + 1, step))
    return [int(part) for part in spec.split(",") if part.strip()]


def _run(command: list[str], log_path: Path, timeout_seconds: int) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write("$ " + " ".join(command) + "\n\n")
        log_file.flush()
        completed = subprocess.run(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = time.monotonic() - started
        log_file.write(f"\nEXIT_CODE={completed.returncode}\n")
        log_file.write(f"ELAPSED_SECONDS={elapsed:.3f}\n")
    if completed.returncode != 0:
        raise RuntimeError(f"command failed, see {log_path}")


def _require(path: Path, description: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: missing {description}: {path}")


def _surface_vtk(paths: Paths, frame: int) -> Path:
    return paths.iso_dir / f"Surface_{frame:04d}.vtk"


def _fluid_vtk(paths: Paths, frame: int) -> Path:
    return paths.particles_dir / f"PartFluid_{frame:04d}.vtk"


def _render_png(paths: Paths, frame: int) -> Path:
    return paths.frames_dir / f"surface_{frame:04d}.png"


def _prepare(paths: Paths, frames: list[int]) -> None:
    _require(paths.isosurface, "IsoSurface executable")
    _require(paths.blender, "Blender executable")
    _require(paths.data_dir, "existing BI4 data directory")
    _require(paths.particles_dir, "existing PartVTK particle directory")
    _require(paths.case_xml, "case XML")
    for frame in frames:
        _require(paths.data_dir / f"Part_{frame:04d}.bi4", f"BI4 frame {frame:04d}")
        _require(_fluid_vtk(paths, frame), f"fluid VTK frame {frame:04d}")
    paths.output_root.mkdir(parents=True, exist_ok=True)
    paths.iso_dir.mkdir(parents=True, exist_ok=True)
    paths.frames_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)


def _reconstruct_surfaces(paths: Paths, frames: list[int], timeout_seconds: int) -> None:
    for frame in frames:
        surface = _surface_vtk(paths, frame)
        if surface.exists() and surface.stat().st_size > 0:
            continue
        command = [
            str(paths.isosurface),
            "-dirdata",
            str(paths.data_dir),
            "-filexml",
            str(paths.case_xml),
            f"-first:{frame}",
            f"-last:{frame}",
            "-saveiso",
            str(paths.iso_dir / "Surface"),
            "-vars:-all,+vel,+rhop,+press,+type",
        ]
        _run(command, paths.logs_dir / f"isosurface_{frame:04d}.log", timeout_seconds)
        if not surface.exists() or surface.stat().st_size == 0:
            raise RuntimeError(f"IsoSurface did not create a usable surface: {surface}")


def _render_surfaces(
    paths: Paths,
    frames: list[int],
    timeout_seconds: int,
    resolution: int,
    samples: int,
    camera_preset: str,
) -> None:
    reference = _fluid_vtk(paths, max(frames))
    for frame in frames:
        output = _render_png(paths, frame)
        if output.exists() and output.stat().st_size > 0:
            continue
        command = [
            str(paths.blender),
            "--background",
            "--python",
            str(paths.repo_root / "scripts/blender_import_legacy_vtk.py"),
            "--",
            "--fluid",
            str(_fluid_vtk(paths, frame)),
            "--camera-reference",
            str(reference),
            "--iso",
            str(_surface_vtk(paths, frame)),
            "--hide-fluid",
            "--output",
            str(output),
            "--resolution",
            str(resolution),
            "--camera-preset",
            camera_preset,
            "--camera-lens",
            "70",
            "--style-preset",
            "polished",
            "--samples",
            str(samples),
            "--iso-color",
            "#5DD9FFFF",
            "--background-color",
            "#071018FF",
            "--light-energy",
            "1200",
            "--light-size",
            "2.0",
            "--no-caption",
        ]
        _run(command, paths.logs_dir / f"blender_surface_{frame:04d}.log", timeout_seconds)


def _assemble_clean(paths: Paths, fps: int, frames: list[int]) -> Path:
    output = paths.output_root / "dualsphysics_shapesinlet3d_surface_clean.mp4"
    sequence_dir = paths.output_root / "surface_frames_clean_sequence"
    sequence_dir.mkdir(parents=True, exist_ok=True)
    for stale in sequence_dir.glob("frame_*.png"):
        stale.unlink()
    for index, frame in enumerate(frames):
        shutil.copy2(_render_png(paths, frame), sequence_dir / f"frame_{index:04d}.png")
    command = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(sequence_dir / "frame_%04d.png"),
        "-vf",
        "format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "20",
        "-movflags",
        "+faststart",
        str(output),
    ]
    _run(command, paths.logs_dir / "ffmpeg_surface_clean.log", 300)
    return output


def _assemble_branded(paths: Paths, fps: int, min_frames: int) -> Path:
    output = paths.output_root / "dualsphysics_shapesinlet3d_surface_showcase.mp4"
    command = [
        "python3",
        str(paths.repo_root / "scripts/assemble_dambreak_video.py"),
        "--input-dir",
        str(paths.frames_dir),
        "--input-pattern",
        "surface_*.png",
        "--min-input-frames",
        str(min_frames),
        "--frames-dir",
        str(paths.output_root / "surface_frames_titled"),
        "--output",
        str(output),
        "--fps",
        str(fps),
        "--width",
        "1280",
        "--height",
        "720",
        "--title",
        "DualSPHysics 05_ShapesInlet3D Surface Render",
        "--subtitle",
        "Official inlet example | IsoSurface -> headless Blender -> ffmpeg | visualization demo, not validation",
        "--closing-title",
        "Surface reconstruction preview",
        "--closing-subtitle",
        "Particle markers hidden; smoother interface from existing BI4 outputs. Not atomization validation.",
        "--particle-text",
        "Official 05_ShapesInlet3D inlet/open-boundary example",
        "--platform-text",
        "DualSPHysics v5.4 | Blender 4.5.10 LTS | RTX 5070 Laptop GPU",
        "--render-text",
        "IsoSurface mesh render | no solver rerun",
        "--sim-frame-duration",
        str(1.0 / fps),
        "--title-duration",
        "5",
        "--closing-duration",
        "4",
        "--no-hud",
    ]
    _run(command, paths.logs_dir / "assemble_surface_showcase.log", 300)
    return output


def _make_contact_sheet(paths: Paths, frames: list[int]) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for contact sheet generation") from exc

    selected = [frames[0], frames[len(frames) // 4], frames[len(frames) // 2], frames[-1]]
    images = [Image.open(_render_png(paths, frame)).convert("RGB") for frame in selected]
    tile_w, tile_h = 640, 360
    sheet = Image.new("RGB", (tile_w * 2, tile_h * 2), (6, 11, 15))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for index, (frame, image) in enumerate(zip(selected, images, strict=True)):
        tile = image.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
        x = (index % 2) * tile_w
        y = (index // 2) * tile_h
        sheet.paste(tile, (x, y))
        draw.rectangle((x + 12, y + 12, x + 160, y + 48), fill=(5, 10, 14))
        draw.text((x + 22, y + 20), f"frame {frame:04d}", font=font, fill=(235, 245, 250))
    output = paths.output_root / "dualsphysics_shapesinlet3d_surface_contact_sheet.png"
    sheet.save(output)
    return output


def _write_manifest(
    paths: Paths,
    frames: list[int],
    clean_mp4: Path,
    branded_mp4: Path,
    contact_sheet: Path,
    started: float,
) -> dict[str, object]:
    surface_files = [_surface_vtk(paths, frame) for frame in frames]
    render_files = [_render_png(paths, frame) for frame in frames]
    manifest = paths.output_root / "artifact_manifest.txt"
    lines = [
        "DualSPHysics 05_ShapesInlet3D surface render artifacts",
        "",
        f"Output root: {paths.output_root}",
        f"Frames: {frames[0]:04d}..{frames[-1]:04d} ({len(frames)} frames)",
        f"Source data: {paths.data_dir}",
        f"Source XML: {paths.case_xml}",
        f"IsoSurface: {paths.isosurface}",
        f"Blender: {paths.blender}",
        "",
        "Generated files:",
    ]
    for path in [*surface_files, *render_files, clean_mp4, branded_mp4, contact_sheet]:
        lines.append(f"- {path} ({path.stat().st_size} bytes)")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    duration = time.monotonic() - started
    summary = {
        "status": "success",
        "reconstruction_path": "DualSPHysics IsoSurface_linux64",
        "output_root": str(paths.output_root),
        "frames": frames,
        "surface_vtk_count": len(surface_files),
        "render_png_count": len(render_files),
        "main_surface_mp4": str(clean_mp4),
        "branded_surface_mp4": str(branded_mp4),
        "contact_sheet": str(contact_sheet),
        "manifest": str(manifest),
        "elapsed_seconds": round(duration, 3),
        "visual_quality": "public_preview_candidate",
        "caveat": "official 3D inlet visualization demo only; not atomization validation",
        "no_solver_rerun": True,
    }
    (paths.output_root / "CODEX_SURFACE_RENDER_SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _write_report(paths: Paths, summary: dict[str, object]) -> None:
    report = f"""# DualSPHysics 05_ShapesInlet3D Surface Render Report

## Status
Success. Existing `Part_XXXX.bi4` files were postprocessed with the official
DualSPHysics `IsoSurface_linux64` tool, then rendered as VTK polygon surfaces in
headless Blender. DualSPHysics itself was not rerun.

## Reconstruction Path
- Tool: `{paths.isosurface}`
- Input BI4 data: `{paths.data_dir}`
- Case XML: `{paths.case_xml}`
- Output surface VTK directory: `{paths.iso_dir}`

## Render Outputs
- Clean surface animation: `{summary["main_surface_mp4"]}`
- Branded surface showcase: `{summary["branded_surface_mp4"]}`
- Contact sheet: `{summary["contact_sheet"]}`
- Artifact manifest: `{summary["manifest"]}`

## Visual Quality Verdict
Public preview candidate. The surface reconstruction removes the visible
particle-marker look from the inlet streams and produces a more fluid-like
interface. The result is smoother and closer to a water visualization than the
particle-cloud render, but it still shows interpolation texture and sparse-data
limitations.

## Comparison To Particle Render
- Particle render: better for showing raw SPH particles and solver provenance,
  but coarse/polygonal at close range.
- Surface render: better for public visual presentation because it hides marker
  faceting and creates continuous inlet columns and free-surface pooling.
- Remaining limitation: this is still the official single-phase/free-surface
  inlet example. It is not fully atomized spray validation, statistically
  stationary spray validation, production CFD, or experimental agreement.

## Next Step
For a final public showcase, compare the v2 multiview particle video against this
surface render and choose either the surface render alone or a two-segment video:
raw SPH particle view followed by reconstructed surface view.
"""
    (paths.output_root / "CODEX_SURFACE_RENDER_REPORT.md").write_text(
        report,
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--isosurface", type=Path, default=DEFAULT_ISOSURFACE)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument(
        "--frames",
        default="20:100:4",
        help="Frame list or inclusive start:stop:step. Default gives 21 frames.",
    )
    parser.add_argument("--fps", type=int, default=3)
    parser.add_argument("--resolution", type=int, default=1280)
    parser.add_argument("--samples", type=int, default=48)
    parser.add_argument("--camera-preset", default="isometric")
    parser.add_argument("--iso-timeout", type=int, default=180)
    parser.add_argument("--render-timeout", type=int, default=600)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    paths = Paths(
        repo_root=repo_root,
        case_dir=args.case_dir,
        output_root=args.output_root,
        isosurface=args.isosurface,
        blender=args.blender,
    )
    frames = _frame_numbers(args.frames)
    if not frames:
        raise SystemExit("ERROR: no frames selected")
    started = time.monotonic()
    _prepare(paths, frames)
    _reconstruct_surfaces(paths, frames, args.iso_timeout)
    _render_surfaces(
        paths,
        frames,
        args.render_timeout,
        args.resolution,
        args.samples,
        args.camera_preset,
    )
    clean_mp4 = _assemble_clean(paths, args.fps, frames)
    branded_mp4 = _assemble_branded(paths, args.fps, len(frames))
    contact_sheet = _make_contact_sheet(paths, frames)
    summary = _write_manifest(paths, frames, clean_mp4, branded_mp4, contact_sheet, started)
    _write_report(paths, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
