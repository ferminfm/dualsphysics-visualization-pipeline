#!/usr/bin/env python3
"""Compile and run a bounded matched quarter/full Basilisk smoke pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_QCC = Path("/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc")
DEFAULT_SOURCE = Path("cases/basilisk/rectangular_internal_nozzle_convergence_visual.c")


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(
    command: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None
) -> dict[str, object]:
    started = timestamp()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "started_at": started,
            "finished_at": timestamp(),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "started_at": started,
            "finished_at": timestamp(),
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
        }


def write_log(path: Path, record: dict[str, object]) -> None:
    path.write_text(
        "COMMAND=" + " ".join(str(part) for part in record["command"]) + "\n"
        + "RETURN_CODE=" + str(record["returncode"]) + "\n"
        + "TIMED_OUT=" + str(record["timed_out"]).lower() + "\n"
        + "\nSTDOUT\n" + str(record["stdout"])
        + "\nSTDERR\n" + str(record["stderr"]),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--qcc", type=Path, default=DEFAULT_QCC)
    parser.add_argument("--maxlevel", type=int, default=5)
    parser.add_argument("--baselevel", type=int, default=4)
    parser.add_argument("--end-time", type=float, default=0.006)
    parser.add_argument("--sample-dt", type=float, default=0.003)
    parser.add_argument("--pressure", type=float, default=351.48)
    parser.add_argument("--external-dh", type=float, default=1.0)
    parser.add_argument("--omp-threads", type=int, default=4)
    parser.add_argument("--compile-timeout", type=int, default=180)
    parser.add_argument("--run-timeout", type=int, default=300)
    args = parser.parse_args()

    source = args.source.resolve()
    qcc = args.qcc.resolve()
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        parser.error(f"output root must be absent or empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        parser.error(f"source not found: {source}")
    if not qcc.is_file() or not os.access(qcc, os.X_OK):
        parser.error(f"qcc is not executable: {qcc}")

    manifest: dict[str, object] = {
        "classification": "bounded_quarter_full_symmetry_smoke",
        "started_at": timestamp(),
        "source": str(source),
        "source_sha256": sha256(source),
        "qcc": str(qcc),
        "omp_threads": args.omp_threads,
        "matched_parameters": {
            "maxlevel": args.maxlevel,
            "baselevel": args.baselevel,
            "pressure": args.pressure,
            "end_time": args.end_time,
            "external_dh": args.external_dh,
            "diagnostic_dt": args.sample_dt,
            "visual_dt": args.sample_dt,
            "checkpoint_dt": args.end_time + args.sample_dt,
            "raw_export": True,
            "facet_export": True,
            "native_frames": False,
            "perturbation_amplitude": 0.0,
        },
        "domain_only_difference": True,
        "transverse_periodic_boundaries": False,
        "commands": [],
        "status": "running",
    }

    with tempfile.TemporaryDirectory(prefix="task02-qcc-") as tmp_name:
        build_dir = Path(tmp_name)
        copied_source = build_dir / source.name
        shutil.copy2(source, copied_source)
        binary = build_dir / "quarter_domain_control"
        basilisk = qcc.parent
        compile_command = [
            str(qcc), "-O2", "-Wall", "-grid=octree", copied_source.name,
            "-o", str(binary), f"-L{basilisk / 'gl'}", "-lglutils", "-lfb_tiny", "-lm",
        ]
        compile_env = os.environ.copy()
        compile_env["BASILISK"] = str(basilisk)
        compile_record = run_command(
            compile_command, cwd=build_dir, timeout=args.compile_timeout, env=compile_env
        )
        write_log(output_root / "compile.log", compile_record)
        manifest["commands"].append({k: v for k, v in compile_record.items() if k not in {"stdout", "stderr"}})
        if compile_record["returncode"] != 0:
            manifest["status"] = "compile_failed"
            manifest["finished_at"] = timestamp()
            (output_root / "run_manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return 1

        run_env = os.environ.copy()
        run_env["OMP_NUM_THREADS"] = str(args.omp_threads)
        for domain in ("quarter", "full"):
            case_output = output_root / domain
            command = [
                str(binary),
                "--case-id", f"task02_smoke_{domain}",
                "--domain", domain,
                "--case-mode", "2",
                "--maxlevel", str(args.maxlevel),
                "--baselevel", str(args.baselevel),
                "--pressure", str(args.pressure),
                "--end-time", str(args.end_time),
                "--external-dh", str(args.external_dh),
                "--output-dir", str(case_output),
                "--diagnostic-dt", str(args.sample_dt),
                "--visual-dt", str(args.sample_dt),
                "--checkpoint-dt", str(args.end_time + args.sample_dt),
                "--raw-export", "1",
                "--native-frames", "0",
                "--facet-export", "1",
                "--max-steps", "3000",
                "--perturb-amp", "0",
            ]
            record = run_command(command, cwd=build_dir, timeout=args.run_timeout, env=run_env)
            write_log(output_root / f"run_{domain}.log", record)
            manifest["commands"].append({k: v for k, v in record.items() if k not in {"stdout", "stderr"}})
            if record["returncode"] != 0:
                manifest["status"] = f"{domain}_run_failed"
                manifest["finished_at"] = timestamp()
                (output_root / "run_manifest.json").write_text(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                return 1

    manifest["status"] = "success"
    manifest["finished_at"] = timestamp()
    (output_root / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"QUARTER_FULL_SMOKE={output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
