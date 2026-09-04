#!/usr/bin/env python3
"""Run one bounded internal-nozzle command with durable lifecycle evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import resource
import signal
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, record: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def signal_process_group(pgid: int, signum: int) -> bool:
    """Signal only the child-owned process group; absence is already terminal."""
    try:
        os.killpg(pgid, signum)
    except ProcessLookupError:
        return False
    return True


def terminate_and_reap(
    child: subprocess.Popen[bytes], pgid: int, grace_seconds: float = 15.0
) -> int:
    """Terminate an observed child group and always reap the direct child."""
    if child.poll() is None:
        signal_process_group(pgid, signal.SIGTERM)
    try:
        return child.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if child.poll() is None:
            signal_process_group(pgid, signal.SIGKILL)
        return child.wait()


def validate_inputs(
    specifications: list[list[str]], cwd: Path
) -> list[dict[str, object]]:
    """Verify declared immutable inputs before the supervised process starts."""
    verified: list[dict[str, object]] = []
    seen: set[Path] = set()
    for requested_text, expected_text in specifications:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_text):
            raise ValueError(
                f"invalid SHA-256 for input {requested_text!r}: expected 64 hex digits"
            )
        requested = Path(requested_text)
        candidate = requested if requested.is_absolute() else cwd / requested
        if candidate.is_symlink():
            raise ValueError(f"input file must not be a symlink: {requested_text}")
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(f"input file does not exist: {requested_text}") from exc
        mode = resolved.stat().st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"input file is not a regular file: {requested_text}")
        if resolved in seen:
            raise ValueError(f"input file declared more than once: {requested_text}")
        seen.add(resolved)
        expected = expected_text.lower()
        observed = sha256_file(resolved)
        if observed != expected:
            raise ValueError(
                f"input SHA-256 mismatch for {requested_text}: "
                f"expected {expected}, observed {observed}"
            )
        verified.append({
            "requested_path": requested_text,
            "resolved_path": str(resolved),
            "size_bytes": resolved.stat().st_size,
            "expected_sha256": expected,
            "observed_sha256": observed,
            "verified": True,
        })
    return verified


def acquire_lock(path: Path, record: dict[str, object]) -> None:
    """Atomically acquire a JSON lock without replacing an existing owner."""
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    fsync_directory(path.parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument(
        "--lock-root",
        type=Path,
        help=(
            "shared lock directory for cross-run duplicate prevention "
            "(default: a sibling of the evidence directory)"
        ),
    )
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--heartbeat-seconds", type=float, default=5.0)
    parser.add_argument("--run-id")
    parser.add_argument("--execution-id")
    parser.add_argument("--segment-id")
    parser.add_argument("--source-commit", default="not_applicable")
    parser.add_argument("--source-sha256", default="not_applicable")
    parser.add_argument(
        "--input-file-sha256",
        nargs=2,
        action="append",
        default=[],
        metavar=("PATH", "SHA256"),
        help="repeatable input path and required SHA-256 identity",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command after -- is required")
    if args.timeout_seconds <= 0 or args.heartbeat_seconds <= 0:
        parser.error("timeouts and heartbeat intervals must be positive")

    evidence = args.evidence_dir.resolve()
    cwd = args.cwd.resolve()
    if not cwd.is_dir():
        parser.error("cwd is not a directory")
    try:
        verified_inputs = validate_inputs(args.input_file_sha256, cwd)
    except ValueError as exc:
        parser.error(str(exc))
    strict_identity = args.execution_id is not None or args.segment_id is not None
    if strict_identity and (args.execution_id is None or args.segment_id is None):
        parser.error("execution-id and segment-id must be provided together")
    identifier_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    if strict_identity:
        if identifier_pattern.fullmatch(args.execution_id) is None:
            parser.error("invalid execution-id")
        if identifier_pattern.fullmatch(args.segment_id) is None:
            parser.error("invalid segment-id")
        if args.run_id is not None and args.run_id != args.segment_id:
            parser.error("run-id must equal segment-id when strict identity is used")
        execution_id = args.execution_id
        segment_id = args.segment_id
        run_id = segment_id
    else:
        run_id = args.run_id or f"run-{uuid.uuid4()}"
        if identifier_pattern.fullmatch(run_id) is None:
            parser.error("invalid run-id")
        execution_id = "not_applicable"
        segment_id = run_id
    if evidence.exists():
        if not evidence.is_dir() or any(evidence.iterdir()):
            parser.error("evidence directory must be a new empty directory")
    else:
        evidence.mkdir(parents=True)
        fsync_directory(evidence.parent)
    requested_lock_root = args.lock_root or evidence.parent / ".internal-nozzle-supervisor-locks"
    if requested_lock_root.exists() and requested_lock_root.is_symlink():
        parser.error("lock root must not be a symlink")
    lock_root = requested_lock_root.resolve()
    lock_root.mkdir(parents=True, exist_ok=True)
    if lock_root.is_symlink() or not lock_root.is_dir():
        parser.error("lock root must be a real directory")
    stdout_path = evidence / "stdout.log"
    stderr_path = evidence / "stderr.log"
    launch_path = evidence / "launch.json"
    heartbeat_path = evidence / "heartbeat.json"
    terminal_path = evidence / "terminal.json"
    lock_path = evidence / "active.lock"
    identity_payload = json.dumps(
        {"argv": command, "cwd": str(cwd)}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    command_identity = hashlib.sha256(identity_payload).hexdigest()
    duplicate_lock_path = lock_root / f"{command_identity}.lock"
    writer_lock_path = lock_root / "one-solver.lock"
    lock_record = {
        "schema": "internal_nozzle_supervisor_lock_v2",
        "execution_id": execution_id,
        "segment_id": segment_id,
        "run_id": run_id,
        "supervisor_pid": os.getpid(),
        "cwd": str(cwd),
        "argv": command,
        "command_cwd_sha256": command_identity,
    }
    local_lock_owned = False
    duplicate_lock_owned = False
    writer_lock_owned = False
    try:
        acquire_lock(lock_path, lock_record)
        local_lock_owned = True
        try:
            acquire_lock(duplicate_lock_path, lock_record)
            duplicate_lock_owned = True
        except FileExistsError:
            print(
                "ERROR: an identical command/cwd is already locked: "
                f"{duplicate_lock_path}",
                file=sys.stderr,
            )
            return 2
        try:
            acquire_lock(writer_lock_path, lock_record)
            writer_lock_owned = True
        except FileExistsError:
            print(
                "ERROR: another internal-nozzle solver already owns the writer lock: "
                f"{writer_lock_path}",
                file=sys.stderr,
            )
            return 2
    finally:
        if local_lock_owned and not writer_lock_owned:
            lock_path.unlink(missing_ok=True)
            fsync_directory(evidence)
        if duplicate_lock_owned and not writer_lock_owned:
            duplicate_lock_path.unlink(missing_ok=True)
            fsync_directory(lock_root)
    started_monotonic = time.monotonic()
    received_signal: int | None = None
    child: subprocess.Popen[bytes] | None = None
    launch: dict[str, object] | None = None
    returncode: int | None = None
    pid: int | None = None
    pgid: int | None = None
    timed_out = False
    supervisor_error: dict[str, str] | None = None

    def request_shutdown(signum: int, _frame: object) -> None:
        """Defer parent-signal handling until child terminal evidence is durable."""
        nonlocal received_signal
        received_signal = signum

    previous_sigterm = signal.signal(signal.SIGTERM, request_shutdown)
    previous_sighup = signal.signal(signal.SIGHUP, request_shutdown)
    previous_sigint = signal.signal(signal.SIGINT, request_shutdown)

    stdout = None
    stderr = None
    try:
        try:
            stdout = stdout_path.open("xb")
            stderr = stderr_path.open("xb")
            child = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            pid = child.pid
            # start_new_session=True makes the child the group leader.  Using the
            # known PID avoids an ESRCH race when a child exits immediately.
            pgid = pid
            launch = {
                "schema": "internal_nozzle_supervision_v2",
                "execution_id": execution_id,
                "segment_id": segment_id,
                "run_id": run_id,
                "started_at_utc": utc_now(),
                "cwd": str(cwd),
                "argv": command,
                "supervisor_pid": os.getpid(),
                "child_pid": pid,
                "process_group": pgid,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "timeout_seconds": args.timeout_seconds,
                "heartbeat_seconds": args.heartbeat_seconds,
                "source_commit": args.source_commit,
                "source_sha256": args.source_sha256,
                "active_lock": str(lock_path),
                "duplicate_lock": str(duplicate_lock_path),
                "writer_lock": str(writer_lock_path),
                "command_cwd_sha256": command_identity,
                "verified_inputs": verified_inputs,
            }
            atomic_json(launch_path, launch)
            last_heartbeat = 0.0
            while child.poll() is None:
                elapsed = time.monotonic() - started_monotonic
                if elapsed - last_heartbeat >= args.heartbeat_seconds:
                    atomic_json(heartbeat_path, {
                        "execution_id": execution_id, "segment_id": segment_id,
                        "run_id": run_id,
                        "observed_at_utc": utc_now(), "supervisor_pid": os.getpid(),
                        "child_pid": pid, "process_group": pgid,
                        "elapsed_seconds": elapsed, "child_exists": process_exists(pid),
                    })
                    last_heartbeat = elapsed
                if elapsed >= args.timeout_seconds or received_signal is not None:
                    timed_out = elapsed >= args.timeout_seconds
                    returncode = terminate_and_reap(child, pgid)
                    break
                time.sleep(min(0.5, args.heartbeat_seconds))
            if returncode is None:
                returncode = child.wait()
        except BaseException as exc:  # child ownership must survive metadata failures
            supervisor_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            if child is not None and pgid is not None:
                try:
                    returncode = terminate_and_reap(child, pgid)
                except BaseException as reap_exc:
                    supervisor_error["reap_error"] = (
                        f"{type(reap_exc).__name__}: {reap_exc}"
                    )
            print(
                f"ERROR: supervisor failure: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        finally:
            if child is not None and child.poll() is None and pgid is not None:
                returncode = terminate_and_reap(child, pgid)
            for stream_name, stream in (("stdout", stdout), ("stderr", stderr)):
                if stream is None:
                    continue
                try:
                    stream.flush()
                    os.fsync(stream.fileno())
                    stream.close()
                except BaseException as exc:
                    if supervisor_error is None:
                        supervisor_error = {
                            "type": type(exc).__name__,
                            "message": f"{stream_name} finalization failed: {exc}",
                        }
                    else:
                        supervisor_error[f"{stream_name}_finalization_error"] = (
                            f"{type(exc).__name__}: {exc}"
                        )

        if child is None or pid is None or pgid is None:
            return 125
        if returncode is None:
            returncode = child.wait()
        elapsed = time.monotonic() - started_monotonic
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        terminal_inputs: list[dict[str, object]] = []
        input_identity_changed = False
        for item in verified_inputs:
            updated = dict(item)
            input_path = Path(str(item["resolved_path"]))
            try:
                observed_after = sha256_file(input_path)
                updated["observed_sha256_after"] = observed_after
                updated["unchanged_during_run"] = observed_after == item["observed_sha256"]
            except (OSError, ValueError) as exc:
                updated["observed_sha256_after"] = None
                updated["unchanged_during_run"] = False
                updated["post_run_error"] = f"{type(exc).__name__}: {exc}"
            input_identity_changed |= not bool(updated["unchanged_during_run"])
            terminal_inputs.append(updated)
        if supervisor_error is not None:
            terminal_state = "supervisor_error"
        elif timed_out:
            terminal_state = "timeout"
        elif received_signal is not None:
            terminal_state = "supervisor_signal"
        elif input_identity_changed:
            terminal_state = "input_identity_changed"
        else:
            terminal_state = "normal_exit" if returncode >= 0 else "signal_exit"
        terminal = {
            "schema": "internal_nozzle_supervision_v2",
            "execution_id": execution_id,
            "segment_id": segment_id,
            "run_id": run_id,
            "started_at_utc": launch["started_at_utc"],
            "ended_at_utc": utc_now(),
            "cwd": str(cwd),
            "argv": command,
            "supervisor_pid": os.getpid(),
            "child_pid": pid,
            "process_group": pgid,
            "source_commit": args.source_commit,
            "source_sha256": args.source_sha256,
            "duplicate_lock": str(duplicate_lock_path),
            "writer_lock": str(writer_lock_path),
            "command_cwd_sha256": command_identity,
            "verified_inputs": terminal_inputs,
            "elapsed_seconds": elapsed,
            "returncode": returncode,
            "exit_code": returncode if returncode >= 0 else None,
            "terminating_signal": -returncode if returncode < 0 else None,
            "timed_out": timed_out,
            "supervisor_signal": received_signal,
            "peak_rss_kib": usage.ru_maxrss,
            "stdout_size_bytes": stdout_path.stat().st_size,
            "stderr_size_bytes": stderr_path.stat().st_size,
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_sha256": sha256_file(stderr_path),
            "child_exists_after_wait": process_exists(pid),
            "terminal_state": terminal_state,
            "supervisor_error": supervisor_error,
            "input_identity_changed": input_identity_changed,
        }
        atomic_json(terminal_path, terminal)
        lock_path.unlink()
        local_lock_owned = False
        duplicate_lock_path.unlink()
        duplicate_lock_owned = False
        writer_lock_path.unlink()
        writer_lock_owned = False
        fsync_directory(evidence)
        fsync_directory(lock_root)
        if supervisor_error is not None or input_identity_changed:
            return 125
        if timed_out:
            return 124
        if received_signal is not None:
            return 128 + received_signal
        return returncode if returncode >= 0 else 128 + (-returncode)
    finally:
        if child is not None and child.poll() is None and pgid is not None:
            terminate_and_reap(child, pgid)
        if local_lock_owned:
            lock_path.unlink(missing_ok=True)
            fsync_directory(evidence)
        if duplicate_lock_owned:
            duplicate_lock_path.unlink(missing_ok=True)
            fsync_directory(lock_root)
        if writer_lock_owned:
            writer_lock_path.unlink(missing_ok=True)
            fsync_directory(lock_root)
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGHUP, previous_sighup)
        signal.signal(signal.SIGINT, previous_sigint)


if __name__ == "__main__":
    raise SystemExit(main())
