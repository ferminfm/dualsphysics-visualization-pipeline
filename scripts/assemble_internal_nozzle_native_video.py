#!/usr/bin/env python3
"""Assemble native Basilisk VOF frame sequences with missing-frame checks."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def frame_index(path: Path) -> int:
    digits = "".join(ch for ch in path.stem if ch.isdigit())
    return int(digits[-4:]) if digits else -1


def check_sequence(frames: list[Path]) -> dict[str, object]:
    indices = [frame_index(path) for path in frames]
    expected = list(range(indices[0], indices[-1] + 1)) if indices else []
    missing = sorted(set(expected) - set(indices))
    return {
        "frame_count": len(frames),
        "first_index": indices[0] if indices else None,
        "last_index": indices[-1] if indices else None,
        "monotone_unique": indices == sorted(set(indices)),
        "missing_indices": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--pattern", default="native_vof_*.ppm")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument("--min-input-frames", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    frames = sorted(args.frames_dir.glob(args.pattern), key=frame_index)
    sequence = check_sequence(frames)
    ffmpeg = shutil.which("ffmpeg")
    result: dict[str, object] = {
        "frames_dir": str(args.frames_dir),
        "pattern": args.pattern,
        "output": str(args.output),
        "fps": args.fps,
        "ffmpeg": ffmpeg or "",
        "dry_run": args.dry_run,
        **sequence,
    }
    ok = (
        len(frames) >= args.min_input_frames
        and bool(sequence["monotone_unique"])
        and not sequence["missing_indices"]
        and bool(ffmpeg)
    )
    if ok and not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg,
            "-y",
            "-framerate",
            str(args.fps),
            "-i",
            str(args.frames_dir / "native_vof_%04d.ppm"),
            "-pix_fmt",
            "yuv420p",
            str(args.output),
        ]
        proc = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result["ffmpeg_command"] = command
        result["ffmpeg_returncode"] = proc.returncode
        result["ffmpeg_stderr_tail"] = proc.stderr[-4000:]
        ok = proc.returncode == 0 and args.output.exists() and args.output.stat().st_size > 0
    result["video_assembly_ready"] = ok

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"NATIVE_VIDEO_MANIFEST={args.manifest}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
