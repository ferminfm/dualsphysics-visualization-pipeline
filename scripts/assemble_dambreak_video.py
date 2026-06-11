"""Assemble a small dam-break portfolio MP4 from rendered PNG frames.

This script intentionally works from already-rendered PNGs. It adds simple
title/closing cards and a compact technical HUD without requiring Blender,
VisualSPHysics, VTK Python modules, or GUI access.
"""

from __future__ import annotations

import argparse
import glob
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEFAULT_TITLE = "DualSPHysics Dam-Break Visualization Pipeline"
DEFAULT_SUBTITLE = "Headless Blender render from prepared legacy VTK frames"
DEFAULT_CLOSING = "Reproducible local GPU SPH-to-Blender visualization pipeline"
DEFAULT_TITLE_DURATION = 6.0
DEFAULT_CLOSING_DURATION = 5.0
DEFAULT_FPS = 2
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_PARTICLE_TEXT = "Particles: ~20,000 fluid particles"
DEFAULT_PLATFORM_TEXT = "DualSPHysics CUDA 12.8 | RTX 5070 Laptop GPU"
DEFAULT_RENDER_TEXT = "Headless Blender VTK render"


@dataclass(frozen=True)
class SourceFrame:
    path: Path
    label: str


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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


def _parse_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("colors must be #RRGGBB")
    try:
        return tuple(int(value[i : i + 2], 16) for i in range(0, 6, 2))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("colors must be #RRGGBB") from exc


def _frame_label(path: Path) -> str:
    match = re.search(r"(\d{4})(?=\.[^.]+$)", path.name)
    return match.group(1) if match else path.stem


def _natural_key(path: Path) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", path.name)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _resolve_inputs(args: argparse.Namespace) -> list[Path]:
    inputs: list[Path] = []
    if args.input:
        inputs.extend(args.input)
    if args.input_glob:
        for pattern in args.input_glob:
            matches = [Path(match) for match in glob.glob(pattern)]
            if not matches:
                raise SystemExit(f"ERROR: --input-glob matched no frames: {pattern}")
            inputs.extend(matches)
    if args.input_dir:
        matches = sorted(args.input_dir.glob(args.input_pattern), key=_natural_key)
        if not matches:
            raise SystemExit(
                f"ERROR: --input-dir/--input-pattern matched no frames: "
                f"{args.input_dir}/{args.input_pattern}"
            )
        inputs.extend(matches)

    if not inputs:
        raise SystemExit("ERROR: provide --input, --input-glob, or --input-dir")

    resolved = sorted({path.resolve() for path in inputs}, key=_natural_key)
    for path in resolved:
        if not path.exists():
            raise SystemExit(f"ERROR: missing input frame: {path}")
        if path.name.startswith("frame_") and path.parent == args.frames_dir.resolve():
            raise SystemExit(
                "ERROR: refusing to read frame_*.png from --frames-dir; "
                "use a separate source sequence such as inlet3d_*.png"
            )
    if args.min_input_frames and len(resolved) < args.min_input_frames:
        raise SystemExit(
            f"ERROR: resolved only {len(resolved)} input frame(s); "
            f"expected at least {args.min_input_frames}"
        )
    return resolved


def _fit_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.convert("RGB")
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _font_that_fits(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    start_size: int,
    min_size: int,
    max_width: int,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = start_size
    while size > min_size:
        candidate = _font(size, bold=bold)
        width, _ = _text_size(draw, text, candidate)
        if width <= max_width:
            return candidate
        size -= 2
    return _font(min_size, bold=bold)


def _draw_card(
    title: str,
    subtitle: str,
    width: int,
    height: int,
    *,
    background: tuple[int, int, int],
    foreground: tuple[int, int, int],
    accent: tuple[int, int, int],
    qr_placeholder: bool,
) -> Image.Image:
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    x = width // 14
    max_text_width = width - x * 2 - 28
    title_font = _font_that_fits(
        draw,
        title,
        start_size=max(34, width // 24),
        min_size=max(24, width // 42),
        max_width=max_text_width,
        bold=True,
    )
    subtitle_font = _font_that_fits(
        draw,
        subtitle,
        start_size=max(18, width // 48),
        min_size=max(15, width // 70),
        max_width=max_text_width,
    )
    title_w, title_h = _text_size(draw, title, title_font)
    sub_w, sub_h = _text_size(draw, subtitle, subtitle_font)
    y = height // 2 - title_h - sub_h
    draw.rectangle((x, y - 26, x + 9, y + title_h + sub_h + 56), fill=accent)
    draw.text((x + 28, y), title, font=title_font, fill=foreground)
    draw.text((x + 30, y + title_h + 24), subtitle, font=subtitle_font, fill=(205, 215, 220))
    if qr_placeholder:
        box = min(width, height) // 7
        bx = width - box - width // 14
        by = height - box - height // 10
        draw.rectangle((bx, by, bx + box, by + box), outline=accent, width=3)
        draw.text((bx + 12, by + box // 2 - 10), "QR", font=subtitle_font, fill=accent)
    return image


def _hud_lines(frame: SourceFrame, args: argparse.Namespace) -> list[str]:
    frame_text = f"Frame {frame.label}"
    if args.seconds_per_frame_index is not None and frame.label.isdigit():
        time_value = int(frame.label) * args.seconds_per_frame_index
        frame_text = f"t={time_value:.4f} s | frame {frame.label}"
    return [
        frame_text,
        args.particle_text,
        args.platform_text,
        args.render_text,
    ]


def _draw_hud(image: Image.Image, frame: SourceFrame, args: argparse.Namespace) -> Image.Image:
    image = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(max(15, image.width // 76))
    lines = _hud_lines(frame, args)
    padding = max(10, image.width // 100)
    gap = max(4, image.height // 180)
    widths_heights = [_text_size(draw, line, font) for line in lines]
    box_w = max(w for w, _ in widths_heights) + padding * 2
    box_h = sum(h for _, h in widths_heights) + gap * (len(lines) - 1) + padding * 2
    x = padding
    y = padding
    draw.rounded_rectangle(
        (x, y, x + box_w, y + box_h),
        radius=8,
        fill=(5, 10, 14, args.hud_alpha),
        outline=(100, 170, 210, 135),
        width=1,
    )
    ty = y + padding
    for i, line in enumerate(lines):
        fill = (235, 245, 250, 255) if i == 0 else (200, 216, 224, 255)
        draw.text((x + padding, ty), line, font=font, fill=fill)
        ty += widths_heights[i][1] + gap
    if args.qr_placeholder:
        box = min(image.size) // 8
        bx = image.width - box - padding
        by = image.height - box - padding
        draw.rounded_rectangle(
            (bx, by, bx + box, by + box),
            radius=6,
            fill=(5, 10, 14, args.hud_alpha),
            outline=(100, 170, 210, 160),
            width=2,
        )
        qr_font = _font(max(13, box // 8), bold=True)
        draw.text((bx + 12, by + box // 2 - 10), args.qr_placeholder_text, font=qr_font, fill=(210, 230, 240, 255))
    return Image.alpha_composite(image, overlay).convert("RGB")


def _save_repeated(
    image: Image.Image,
    frames_dir: Path,
    start_index: int,
    count: int,
) -> int:
    index = start_index
    for _ in range(max(0, count)):
        image.save(frames_dir / f"frame_{index:04d}.png")
        index += 1
    return index


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
        str(frames_dir / "frame_%04d.png"),
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
    subprocess.run(command, check=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append")
    parser.add_argument(
        "--input-glob",
        action="append",
        help="Resolve one or more frame glob patterns inside Python, sorted naturally.",
    )
    parser.add_argument("--input-dir", type=Path, help="Directory containing source PNG frames.")
    parser.add_argument("--input-pattern", default="*.png", help="Pattern used with --input-dir.")
    parser.add_argument(
        "--min-input-frames",
        type=int,
        default=1,
        help="Fail if fewer source frames are resolved. Use >1 for animation assembly.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--subtitle", default=DEFAULT_SUBTITLE)
    parser.add_argument("--closing-title", default=DEFAULT_CLOSING)
    parser.add_argument("--closing-subtitle", default="Frames 0000-0150; frame 0200 excluded after QA")
    parser.add_argument("--title-duration", type=float, default=DEFAULT_TITLE_DURATION)
    parser.add_argument("--closing-duration", type=float, default=DEFAULT_CLOSING_DURATION)
    parser.add_argument("--sim-frame-duration", type=float, default=1.0)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--particle-text", default=DEFAULT_PARTICLE_TEXT)
    parser.add_argument("--platform-text", default=DEFAULT_PLATFORM_TEXT)
    parser.add_argument("--render-text", default=DEFAULT_RENDER_TEXT)
    parser.add_argument(
        "--no-hud",
        action="store_true",
        help="Do not draw the per-frame technical HUD on animation frames.",
    )
    parser.add_argument("--seconds-per-frame-index", type=float)
    parser.add_argument("--hud-alpha", type=int, default=176)
    parser.add_argument("--background", type=_parse_color, default=(6, 11, 15))
    parser.add_argument("--foreground", type=_parse_color, default=(238, 246, 250))
    parser.add_argument("--accent", type=_parse_color, default=(55, 170, 220))
    parser.add_argument("--qr-placeholder", action="store_true")
    parser.add_argument("--qr-placeholder-text", default="QR placeholder")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.fps <= 0:
        raise SystemExit("ERROR: --fps must be positive")

    source_frames = _resolve_inputs(args)

    args.frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in args.frames_dir.glob("frame_*.png"):
        stale.unlink()

    title_frames = round(args.title_duration * args.fps)
    closing_frames = round(args.closing_duration * args.fps)
    sim_frames_each = max(1, round(args.sim_frame_duration * args.fps))

    title = _draw_card(
        args.title,
        args.subtitle,
        args.width,
        args.height,
        background=args.background,
        foreground=args.foreground,
        accent=args.accent,
        qr_placeholder=args.qr_placeholder,
    )
    closing = _draw_card(
        args.closing_title,
        args.closing_subtitle,
        args.width,
        args.height,
        background=args.background,
        foreground=args.foreground,
        accent=args.accent,
        qr_placeholder=args.qr_placeholder,
    )

    index = _save_repeated(title, args.frames_dir, 0, title_frames)
    for input_path in source_frames:
        frame = SourceFrame(path=input_path, label=_frame_label(input_path))
        image = _fit_cover(Image.open(input_path), args.width, args.height)
        if not args.no_hud:
            image = _draw_hud(image, frame, args)
        index = _save_repeated(image, args.frames_dir, index, sim_frames_each)
    index = _save_repeated(closing, args.frames_dir, index, closing_frames)

    _write_video(args.frames_dir, args.output, args.fps)
    print(f"OUTPUT={args.output}")
    print(f"FRAMES_DIR={args.frames_dir}")
    print(f"VIDEO_FRAMES={index}")
    print(f"FPS={args.fps}")
    print(f"DURATION_SECONDS={index / args.fps:.3f}")
    print(f"TITLE_DURATION={args.title_duration}")
    print(f"CLOSING_DURATION={args.closing_duration}")
    print(f"QR_PLACEHOLDER={args.qr_placeholder}")


if __name__ == "__main__":
    main()
