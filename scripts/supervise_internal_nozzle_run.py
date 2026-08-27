#!/usr/bin/env python3
"""Run one bounded internal-nozzle command with durable lifecycle evidence."""

from __future__ import annotations

import argparse
import json
import os
import resource
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, record: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--heartbeat-seconds", type=float, default=5.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command after -- is required")
    if args.timeout_seconds <= 0 or args.heartbeat_seconds <= 0:
        parser.error("timeouts and heartbeat intervals must be positive")

    evidence = args.evidence_dir.resolve()
    cwd = args.cwd.resolve()
    if not cwd.is_dir():
        parser.error("cwd is not a directory")
    if evidence.exists():
        if not evidence.is_dir() or any(evidence.iterdir()):
            parser.error("evidence directory must be a new empty directory")
    else:
        evidence.mkdir(parents=True)
    stdout_path = evidence / "stdout.log"
    stderr_path = evidence / "stderr.log"
    launch_path = evidence / "launch.json"
    heartbeat_path = evidence / "heartbeat.json"
    terminal_path = evidence / "terminal.json"
    started_monotonic = time.monotonic()
    received_signal: int | None = None

    def request_shutdown(signum: int, _frame: object) -> None:
        """Defer parent-signal handling until child terminal evidence is durable."""
        nonlocal received_signal
        received_signal = signum

    previous_sigterm = signal.signal(signal.SIGTERM, request_shutdown)
    previous_sighup = signal.signal(signal.SIGHUP, request_shutdown)
    previous_sigint = signal.signal(signal.SIGINT, request_shutdown)

    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            child = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            pid = child.pid
            pgid = os.getpgid(pid)
            launch = {
                "schema": "internal_nozzle_supervision_v1",
                "started_at_utc": utc_now(),
                "cwd": str(cwd),
                "argv": command,
                "pid": pid,
                "process_group": pgid,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "timeout_seconds": args.timeout_seconds,
                "heartbeat_seconds": args.heartbeat_seconds,
                "lifecycle_owner": os.getpid(),
            }
            atomic_json(launch_path, launch)
            timed_out = False
            sent_term = False
            last_heartbeat = 0.0
            while child.poll() is None:
                elapsed = time.monotonic() - started_monotonic
                if elapsed - last_heartbeat >= args.heartbeat_seconds:
                    atomic_json(heartbeat_path, {
                        "observed_at_utc": utc_now(), "pid": pid, "process_group": pgid,
                        "elapsed_seconds": elapsed, "child_exists": process_exists(pid),
                    })
                    last_heartbeat = elapsed
                if elapsed >= args.timeout_seconds or received_signal is not None:
                    timed_out = elapsed >= args.timeout_seconds
                    os.killpg(pgid, signal.SIGTERM)
                    sent_term = True
                    break
                time.sleep(min(0.5, args.heartbeat_seconds))
            if sent_term:
                try:
                    child.wait(timeout=15.0)
                except subprocess.TimeoutExpired:
                    os.killpg(pgid, signal.SIGKILL)
            returncode = child.wait()

        elapsed = time.monotonic() - started_monotonic
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        terminal = {
            "schema": "internal_nozzle_supervision_v1",
            "started_at_utc": launch["started_at_utc"],
            "ended_at_utc": utc_now(),
            "pid": pid,
            "process_group": pgid,
            "elapsed_seconds": elapsed,
            "returncode": returncode,
            "exit_code": returncode if returncode >= 0 else None,
            "terminating_signal": -returncode if returncode < 0 else None,
            "timed_out": timed_out,
            "supervisor_signal": received_signal,
            "peak_rss_kib": usage.ru_maxrss,
            "stdout_size_bytes": stdout_path.stat().st_size,
            "stderr_size_bytes": stderr_path.stat().st_size,
            "child_exists_after_wait": process_exists(pid),
        }
        atomic_json(terminal_path, terminal)
        if received_signal is not None:
            return 128 + received_signal
        return returncode if returncode >= 0 else 128 + (-returncode)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGHUP, previous_sighup)
        signal.signal(signal.SIGINT, previous_sigint)


if __name__ == "__main__":
    raise SystemExit(main())
