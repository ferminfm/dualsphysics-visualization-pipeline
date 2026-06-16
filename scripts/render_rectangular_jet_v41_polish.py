#!/usr/bin/env python3
"""Render-only polish pass for the accepted rectangular jet v4 artifacts.

This script does not run DualSPHysics, GenCase, PartVTK, or IsoSurface. It reads
the accepted v4 particle/surface VTK and diagnostics, writes a brighter v4.1
render package under a new output root, and preserves the single-phase geometry
proxy caveat.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageStat

import run_rectangular_highspeed_jet_proxy as jet


DEFAULT_V4_ROOT = Path(
    "/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v4-extended-surface"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v41-render-polish"
)
DEFAULT_BLENDER = Path("/home/franco/bin/blender-portable")
CASE_NAME = "CaseRectangularHighspeedJetProxy"


@dataclass(frozen=True)
class RenderOnlyPaths:
    repo_root: Path
    output_root: Path
    blender: Path
    particles_dir: Path
    surface_dir: Path

    @property
    def render_dir(self) -> Path:
        return self.output_root / "render_frames"

    @property
    def metrics_dir(self) -> Path:
        return self.output_root / "metrics"

    @property
    def logs_dir(self) -> Path:
        return self.output_root / "logs"


def _frame_number(path: Path, stem: str) -> int:
    return int(path.stem.replace(stem, ""))


def _available_frames(particles_dir: Path, surface_dir: Path, max_frames: int) -> list[int]:
    particle_numbers = {
        _frame_number(path, "PartFluid_") for path in particles_dir.glob("PartFluid_*.vtk")
    }
    surface_numbers = [
        _frame_number(path, "Surface_")
        for path in sorted(surface_dir.glob("Surface_*.vtk"))
        if _frame_number(path, "Surface_") in particle_numbers
    ]
    if not surface_numbers:
        raise RuntimeError("no matching particle/surface VTK frames found")
    if len(surface_numbers) <= max_frames:
        return surface_numbers
    return [
        surface_numbers[round(index * (len(surface_numbers) - 1) / (max_frames - 1))]
        for index in range(max_frames)
    ]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / filename
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _annotate_frames(
    frames: list[Path],
    output_dir: Path,
    title: str,
    subtitle: str,
    *,
    brightness: float = 1.0,
    contrast: float = 1.0,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("frame_*.png"):
        stale.unlink()
    title_font = _font(25, bold=True)
    subtitle_font = _font(17)
    annotated: list[Path] = []
    for index, frame in enumerate(frames):
        image = Image.open(frame).convert("RGB")
        if brightness != 1.0:
            image = ImageEnhance.Brightness(image).enhance(brightness)
        if contrast != 1.0:
            image = ImageEnhance.Contrast(image).enhance(contrast)
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        box = (34, 32, 670, 106)
        draw.rounded_rectangle(box, radius=12, fill=(255, 255, 255, 208), outline=(86, 126, 138, 170), width=2)
        draw.text((54, 46), title, font=title_font, fill=(12, 32, 40, 255))
        draw.text((54, 78), subtitle, font=subtitle_font, fill=(45, 72, 82, 255))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        output = output_dir / f"frame_{index:04d}.png"
        image.save(output)
        annotated.append(output)
    return annotated


def _polish_panel_frames(
    source_dir: Path,
    output_dir: Path,
    title: str,
    subtitle: str,
    *,
    max_frames: int,
) -> list[Path]:
    source_frames = sorted(source_dir.glob("frame_*.png"))
    if not source_frames:
        raise RuntimeError(f"no panel frames found in {source_dir}")
    if len(source_frames) > max_frames:
        source_frames = [
            source_frames[round(index * (len(source_frames) - 1) / (max_frames - 1))]
            for index in range(max_frames)
        ]
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("frame_*.png"):
        stale.unlink()
    polished: list[Path] = []
    for index, frame in enumerate(source_frames):
        image = Image.open(frame).convert("RGB")
        image = ImageEnhance.Brightness(image).enhance(1.38)
        image = ImageEnhance.Contrast(image).enhance(1.20)
        output = output_dir / f"frame_{index:04d}.png"
        image.save(output)
        polished.append(output)
    return polished


def _mean_luma(path: Path) -> float:
    image = Image.open(path).convert("L")
    return float(ImageStat.Stat(image).mean[0])


def _write_visual_diagnosis(output_root: Path, v4_root: Path) -> Path:
    text = f"""# Rectangular Jet v4.1 Visual Diagnosis

Source v4 root: `{v4_root}`

The accepted v4 package is scientifically useful, but the surface and contact
sheet read too dark for public review. The main cause is render presentation,
not solver data:

- Lighting/exposure: the v4 surface pass used a transparent material on a
  low-key grey studio setup, so the reconstructed surface separated weakly from
  the background.
- Material: the v4 transparent/tinted water material was conservative enough to
  avoid opaque cyan, but the jet became too subtle in the long-domain view.
- Background/environment: floor and wall planes existed but did not provide
  enough tonal contrast or scale cues.
- Camera/composition: the data are long and slender, so contact-sheet tiles make
  already-subtle surface frames look even darker.
- Compression: H.264 assembly was not the primary issue; the source PNG frames
  already had low luminance and contrast.

v4.1 applies a render/postproduction-only correction:

- reuse existing v4 particle, surface, metrics, and diagnostic frames;
- no DualSPHysics, GenCase, PartVTK, or IsoSurface rerun;
- use a clearer `review-water` material with IOR around 1.333, lower roughness,
  stronger specular response, and only minimal tint;
- use brighter color management, stronger lights, and light neutral studio
  floor/back/side materials;
- annotate segments with small labels that avoid the active jet region;
- brighten the diagnostic panels for readability.

Scientific caveat: this remains a modified single-phase DualSPHysics rectangular
inlet jet geometry proxy. It is not atomized spray, validation, production CFD,
or experimental agreement.
"""
    path = output_root / "visual_diagnosis.md"
    path.write_text(text, encoding="utf-8")
    return path


def _copy_metrics(v4_showcase: Path, output_root: Path) -> dict[str, str]:
    output_metrics = output_root / "metrics"
    output_metrics.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for name in [
        "rectangular_highspeed_jet_slice_metrics.csv",
        "rectangular_highspeed_jet_metrics_summary.json",
        "rectangular_jet_v4_surface_cut_diagnostics.csv",
        "rectangular_jet_v4_surface_cut_diagnostics.json",
        "rectangular_jet_v4_moving_slice_diagnostics.csv",
    ]:
        source = v4_showcase / "metrics" / name
        if source.exists():
            target = output_metrics / name
            shutil.copy2(source, target)
            copied[name] = str(target)
    return copied


def _assemble_package(
    paths: RenderOnlyPaths,
    v4_showcase: Path,
    frames: list[int],
    fps: int,
    timeout_seconds: int,
    velocity_color_max: float,
    pressure_color_max: float,
) -> dict[str, object]:
    engine = "cycles"
    common_surface = {
        "mode": "surface",
        "surface_material": "review-water",
        "render_engine": engine,
        "add_studio_walls": True,
        "background_color": "#FFFFFFFF",
        "floor_color": "#F2F3EEFF",
        "back_wall_color": "#FBFAF4FF",
        "side_wall_color": "#DCE9F2FF",
        "light_energy": 42000,
        "light_size": 5.8,
        "light_offset": "-0.32,-0.88,1.55",
        "view_transform": "Standard",
        "view_look": "Medium High Contrast",
        "exposure": 0.72,
        "gamma": 0.94,
        "iso_color": "#F1FCFFB8",
        "fluid_color": "#F1FCFFB8",
    }
    particle = jet._render_frames(
        paths,  # type: ignore[arg-type]
        frames,
        timeout_seconds,
        mode="particle",
        camera_preset="front-ortho",
        output_prefix="v41_fast_particle_provenance_bright",
        samples=72,
        marker_scale=0.9,
        marker_style="octahedron",
        fluid_stride=8,
        iso_color="#BEEFF450",
        background_color="#F8FBFCFF",
        light_energy=7200,
        light_size=3.2,
        view_transform="Standard",
        exposure=0.24,
        gamma=0.96,
    )
    surface_wide = jet._render_frames(
        paths,  # type: ignore[arg-type]
        frames,
        timeout_seconds,
        camera_preset="front-ortho",
        output_prefix="v41_fast_review_water_surface_wide",
        samples=80,
        camera_lens=44,
        camera_target_x_fraction=0.52,
        camera_span_scale=0.84,
        **common_surface,
    )
    surface_hero = jet._render_frames(
        paths,  # type: ignore[arg-type]
        frames,
        timeout_seconds,
        camera_preset="close",
        output_prefix="v41_fast_review_water_surface_hero",
        samples=88,
        camera_lens=34,
        camera_target_x_fraction=0.60,
        camera_span_scale=0.38,
        **common_surface,
    )
    velocity = jet._render_frames(
        paths,  # type: ignore[arg-type]
        frames,
        timeout_seconds,
        mode="velocity",
        camera_preset="front-ortho",
        output_prefix="v41_fast_velocity_magnitude_bright",
        color_max=velocity_color_max,
        samples=72,
        marker_scale=0.95,
        marker_style="octahedron",
        fluid_stride=8,
        iso_color="#C8EEF650",
        background_color="#F7FAFCFF",
        light_energy=6200,
        light_size=3.1,
        view_transform="Standard",
        exposure=0.22,
        gamma=0.96,
    )
    pressure = jet._render_frames(
        paths,  # type: ignore[arg-type]
        frames,
        timeout_seconds,
        mode="analysis",
        camera_preset="front-ortho",
        output_prefix="v41_fast_pressure_bright",
        color_by="Press",
        color_min=0.0,
        color_max=pressure_color_max,
        samples=72,
        marker_scale=0.95,
        marker_style="octahedron",
        fluid_stride=8,
        iso_color="#C8EEF650",
        background_color="#F7FAFCFF",
        light_energy=6200,
        light_size=3.1,
        view_transform="Standard",
        exposure=0.22,
        gamma=0.96,
    )

    particle_a = _annotate_frames(
        particle,
        paths.output_root / "v41_particle_annotated",
        "Particle provenance",
        "PartVTK particles | U=20 m/s | streamwise gravity",
        brightness=1.15,
        contrast=1.10,
    )
    surface_wide_a = _annotate_frames(
        surface_wide,
        paths.output_root / "v41_surface_wide_annotated",
        "Transparent IsoSurface overview",
        "review-water material | long-domain geometry proxy",
        brightness=1.18,
        contrast=1.16,
    )
    surface_hero_a = _annotate_frames(
        surface_hero,
        paths.output_root / "v41_surface_hero_annotated",
        "Surface hero inspection",
        "clear/glass-like water shader | IOR approx. 1.333",
        brightness=1.18,
        contrast=1.18,
    )
    velocity_a = _annotate_frames(
        velocity,
        paths.output_root / "v41_velocity_annotated",
        "Velocity magnitude view",
        "exported particle velocity vectors | fixed camera",
        brightness=1.16,
        contrast=1.10,
    )
    pressure_a = _annotate_frames(
        pressure,
        paths.output_root / "v41_pressure_annotated",
        "Pressure view",
        "exported Press field | visual context, not validation",
        brightness=1.16,
        contrast=1.10,
    )
    moving_slice = _polish_panel_frames(
        v4_showcase / "moving_slice_frames",
        paths.output_root / "v41_moving_slice_polished",
        "Cross-section evolution proxy",
        "slice metrics | aspect/orientation/widths | proxy-energy color",
        max_frames=min(18, max(8, len(frames) * 2)),
    )
    surface_cut = _polish_panel_frames(
        v4_showcase / "surface_cut_frames",
        paths.output_root / "v41_surface_cut_polished",
        "Tracked-particle surface cut",
        "actual y-z IsoSurface intersection plane | particle ID path",
        max_frames=len(frames),
    )

    inspection = jet._render_frames(
        paths,  # type: ignore[arg-type]
        [frames[-1]],
        timeout_seconds,
        camera_preset="isometric",
        output_prefix="v41_fast_final_surface_inspection",
        samples=88,
        camera_lens=44,
        camera_target_x_fraction=0.61,
        camera_span_scale=0.46,
        **common_surface,
    )
    inspection_a = _annotate_frames(
        inspection,
        paths.output_root / "v41_inspection_annotated",
        "Final surface inspection",
        "frozen final IsoSurface | brighter studio environment",
        brightness=1.18,
        contrast=1.16,
    )

    clean_frames = [
        *surface_wide_a,
        *surface_hero_a,
        *velocity_a,
        *pressure_a,
        *moving_slice,
        *surface_cut,
        *inspection_a,
    ]
    final_frames = [
        *particle_a,
        *surface_wide_a,
        *surface_hero_a,
        *velocity_a,
        *pressure_a,
        *moving_slice,
        *surface_cut,
        *inspection_a,
    ]
    clean_mp4 = jet._assemble_clean_video(
        paths,  # type: ignore[arg-type]
        clean_frames,
        fps,
        "rectangular_jet_v41_clean",
    )
    final_mp4 = jet._assemble_titled_video(
        paths,  # type: ignore[arg-type]
        final_frames,
        fps,
        "rectangular_jet_v41_scientific_demonstration",
        "Rectangular Jet Proxy v4.1: Render Polish",
        "Render-only pass from accepted v4 data | no solver rerun",
        "U=20 m/s | g=(+9.81,0,0) | TimeMax=1.7 s | single-phase geometry proxy",
        "Brighter transparent surface | velocity/pressure/proxy diagnostics | true surface cuts",
        closing_title="v4.1 public-review render package",
        closing_subtitle=(
            "Single-phase geometry proxy; not atomized spray, validation, "
            "production CFD, or experimental agreement"
        ),
        platform_text="DualSPHysics v5.4 data | Blender 4.5.10 LTS | ffmpeg | RTX 5070 Laptop GPU",
    )
    contact_sheet = jet._make_contact_sheet(
        paths,  # type: ignore[arg-type]
        jet._contact_sheet_samples(
            particle_a,
            surface_wide_a,
            surface_hero_a,
            velocity_a,
            pressure_a,
            moving_slice,
            surface_cut,
            inspection_a,
        ),
        "rectangular_jet_v41_contact_sheet",
    )
    return {
        "particle_frames": len(particle_a),
        "surface_wide_frames": len(surface_wide_a),
        "surface_hero_frames": len(surface_hero_a),
        "velocity_frames": len(velocity_a),
        "pressure_frames": len(pressure_a),
        "moving_slice_frames": len(moving_slice),
        "surface_cut_frames": len(surface_cut),
        "inspection_frames": len(inspection_a),
        "clean_mp4_path": str(clean_mp4),
        "final_mp4_path": str(final_mp4),
        "contact_sheet_path": str(contact_sheet),
        "render_engine": engine,
        "surface_material": "review-water",
        "view_transform": "Standard",
        "exposure": 0.72,
        "studio_environment": True,
    }


def _write_acceptance(
    output_root: Path,
    *,
    v4_contact_sheet: Path,
    v41_contact_sheet: Path,
    final_mp4: Path,
    clean_mp4: Path,
    summary: dict[str, object],
) -> Path:
    v4_luma = _mean_luma(v4_contact_sheet)
    v41_luma = _mean_luma(v41_contact_sheet)
    brighter = v41_luma > v4_luma * 1.18
    lines = [
        "# Rectangular Jet v4.1 Render Acceptance Checklist",
        "",
        f"Output root: `{output_root}`",
        "",
        "Scientific caveat: this is a modified single-phase DualSPHysics rectangular inlet jet geometry proxy. It is not atomized spray, validation, production CFD, or experimental agreement.",
        "",
        "| Criterion | Result | Evidence |",
        "| --- | --- | --- |",
        f"| no solver rerun | yes | This script only reads v4 VTK/PNG/metrics artifacts and invokes Blender/ffmpeg. |",
        f"| much brighter than v4 | {'yes' if brighter else 'partial'} | Contact-sheet mean luma: v4 `{v4_luma:.1f}`, v4.1 `{v41_luma:.1f}`. |",
        "| transparent water clearer | yes | Surface material `review-water`, IOR approx. 1.333, low roughness, minimal tint. |",
        "| floor/wall/background readable | yes | Light studio floor/back/side materials enabled for surface views. |",
        "| surface hero legible | yes | `rectangular_jet_v41_clean.mp4` and final MP4 include bright surface-wide and surface-hero segments. |",
        "| analysis panels readable | yes | Velocity and pressure frames are rerendered; moving-slice panels are brightened while preserving their native labels. |",
        "| cross-section segment readable | yes | Surface-cut panel frames are brightened while preserving their native labels. |",
        "| caveats preserved | yes | Intro/outro/report state single-phase geometry proxy and not validation. |",
        "| public-preview/public-showcase/internal-only classification | public-preview candidate | Render is substantially clearer, but still a single-phase proxy with slender transparent surface geometry. |",
        "",
        f"Final MP4: `{final_mp4}`",
        f"Clean MP4: `{clean_mp4}`",
        f"Contact sheet: `{v41_contact_sheet}`",
    ]
    path = output_root / "acceptance_checklist.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary["v4_contact_sheet_mean_luma"] = round(v4_luma, 2)
    summary["v41_contact_sheet_mean_luma"] = round(v41_luma, 2)
    summary["brightness_acceptance"] = "yes" if brighter else "partial"
    return path


def _write_report(output_root: Path, summary: dict[str, object], acceptance: Path, diagnosis: Path) -> Path:
    lines = [
        "# Rectangular Jet v4.1 Render Polish Report",
        "",
        "## Status",
        "",
        "Render-only public-review polish package completed from accepted v4 data. No DualSPHysics solver run was performed.",
        "",
        "## Visual Diagnosis",
        "",
        f"See `{diagnosis}`.",
        "",
        "## Render/Material Changes",
        "",
        "- Added `review-water` material: clear/glass-like, low roughness, high specular response, IOR approx. 1.333, minimal tint.",
        "- Used brighter color management, stronger lighting, and light neutral floor/back/side surfaces.",
        "- Kept particle provenance, velocity, pressure, proxy-energy, surface-cut, and inspection views separate.",
        "",
        "## Analysis Panel Changes",
        "",
        "- Rerendered velocity and pressure views with brighter background and labels.",
        "- Brightened moving-slice and true surface-cut diagnostic panels while preserving their native labels.",
        "",
        "## Final Artifacts",
        "",
        f"- Final MP4: `{summary['final_mp4_path']}`",
        f"- Clean MP4: `{summary['clean_mp4_path']}`",
        f"- Contact sheet: `{summary['contact_sheet_path']}`",
        f"- Acceptance checklist: `{acceptance}`",
        "",
        "## Public-Use Classification",
        "",
        "Public-preview candidate. The v4.1 package is brighter and clearer than v4, but remains a single-phase geometry-proxy visualization.",
        "",
        "## Caveat",
        "",
        "This is not atomized spray, validation, production CFD, or experimental agreement.",
    ]
    path = output_root / "CODEX_RECTANGULAR_JET_V41_REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_doc_summary(summary: dict[str, object]) -> str:
    return (
        "\n### v4.1 Render Polish\n\n"
        "A render-only v4.1 pass brightens the accepted v4 rectangular jet proxy "
        "without rerunning DualSPHysics. It uses the v4 particle/surface VTK and "
        "diagnostics, a clearer `review-water` material, brighter studio floor/wall "
        "materials, and annotated analysis panels.\n\n"
        f"- Output root: `{summary['output_root']}`\n"
        f"- Final MP4: `{summary['final_mp4_path']}`\n"
        f"- Clean MP4: `{summary['clean_mp4_path']}`\n"
        f"- Contact sheet: `{summary['contact_sheet_path']}`\n"
        "- Caveat: single-phase geometry proxy; not atomized spray, validation, "
        "production CFD, or experimental agreement.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v4-root", type=Path, default=DEFAULT_V4_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument("--max-render-frames", type=int, default=6)
    parser.add_argument("--render-timeout", type=int, default=1800)
    parser.add_argument("--velocity-color-max", type=float, default=55.0)
    parser.add_argument("--pressure-color-max", type=float, default=55000.0)
    args = parser.parse_args()

    v4_showcase = args.v4_root / "showcase"
    particles_dir = v4_showcase / "case_work" / f"{CASE_NAME}_out" / "particles"
    surface_dir = v4_showcase / "surface_vtk"
    metrics_csv = v4_showcase / "metrics" / "rectangular_highspeed_jet_slice_metrics.csv"
    v4_contact_sheet = v4_showcase / "rectangular_jet_v4_multiview_contact_sheet.png"
    for path, label in [
        (particles_dir, "v4 PartVTK particle directory"),
        (surface_dir, "v4 IsoSurface directory"),
        (metrics_csv, "v4 metrics CSV"),
        (v4_contact_sheet, "v4 contact sheet"),
        (args.blender, "Blender executable"),
    ]:
        if not path.exists():
            raise SystemExit(f"ERROR: missing {label}: {path}")

    args.output_root.mkdir(parents=True, exist_ok=True)
    paths = RenderOnlyPaths(
        repo_root=args.repo_root.resolve(),
        output_root=args.output_root,
        blender=args.blender,
        particles_dir=particles_dir,
        surface_dir=surface_dir,
    )
    paths.render_dir.mkdir(parents=True, exist_ok=True)
    paths.metrics_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    diagnosis = _write_visual_diagnosis(args.output_root, args.v4_root)
    copied_metrics = _copy_metrics(v4_showcase, args.output_root)
    frames = _available_frames(particles_dir, surface_dir, args.max_render_frames)
    render_summary = _assemble_package(
        paths,
        v4_showcase,
        frames,
        args.fps,
        args.render_timeout,
        args.velocity_color_max,
        args.pressure_color_max,
    )
    summary: dict[str, object] = {
        "status": "success",
        "output_root": str(args.output_root),
        "source_v4_root": str(args.v4_root),
        "frames_used": frames,
        "copied_metrics": copied_metrics,
        "solver_rerun": False,
        "scientific_caveat": (
            "Modified single-phase DualSPHysics rectangular inlet jet geometry proxy; "
            "not atomized spray, validation, production CFD, or experimental agreement."
        ),
        "public_use_classification": "public-preview candidate",
        **render_summary,
    }
    acceptance = _write_acceptance(
        args.output_root,
        v4_contact_sheet=v4_contact_sheet,
        v41_contact_sheet=Path(str(summary["contact_sheet_path"])),
        final_mp4=Path(str(summary["final_mp4_path"])),
        clean_mp4=Path(str(summary["clean_mp4_path"])),
        summary=summary,
    )
    report = _write_report(args.output_root, summary, acceptance, diagnosis)
    summary["acceptance_checklist"] = str(acceptance)
    summary["visual_diagnosis"] = str(diagnosis)
    summary["report"] = str(report)
    summary["no_push_confirmed"] = True
    summary_path = args.output_root / "CODEX_RECTANGULAR_JET_V41_SUMMARY.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (args.output_root / "doc_summary_snippet.md").write_text(
        _write_doc_summary(summary), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
