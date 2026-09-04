import hashlib
import importlib.util
import json
import signal
import subprocess
import sys
import time
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "supervise_internal_nozzle_run.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def supervisor_command(
    tmp_path: Path,
    evidence: Path,
    child: list[str],
    *,
    run_id: str,
    timeout: str = "10",
    extra: list[str] | None = None,
) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--evidence-dir", str(evidence),
        "--cwd", str(tmp_path),
        "--lock-root", str(tmp_path / "shared-locks"),
        "--timeout-seconds", timeout,
        "--heartbeat-seconds", "0.02",
        "--run-id", run_id,
        *(extra or []),
        "--",
        *child,
    ]


def wait_for_file(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def test_supervisor_records_nonzero_terminal_result(tmp_path: Path):
    evidence = tmp_path / "run-001"
    child = (
        "import sys; "
        "print('known-stdout'); "
        "print('known-stderr', file=sys.stderr); "
        "raise SystemExit(7)"
    )
    command = supervisor_command(
        tmp_path,
        evidence,
        [sys.executable, "-c", child],
        run_id="smoke-001",
        extra=["--source-commit", "a" * 40, "--source-sha256", "b" * 64],
    )
    completed = subprocess.run(command, check=False)
    assert completed.returncode == 7
    launch = json.loads((evidence / "launch.json").read_text(encoding="utf-8"))
    terminal = json.loads((evidence / "terminal.json").read_text(encoding="utf-8"))
    assert launch["run_id"] == terminal["run_id"] == "smoke-001"
    assert launch["argv"] == terminal["argv"]
    assert launch["cwd"] == terminal["cwd"] == str(tmp_path.resolve())
    assert terminal["exit_code"] == 7
    assert terminal["terminating_signal"] is None
    assert terminal["terminal_state"] == "normal_exit"
    assert terminal["child_exists_after_wait"] is False
    assert terminal["stdout_sha256"] == digest(evidence / "stdout.log")
    assert terminal["stderr_sha256"] == digest(evidence / "stderr.log")
    assert terminal["stdout_size_bytes"] == (evidence / "stdout.log").stat().st_size
    assert terminal["stderr_size_bytes"] == (evidence / "stderr.log").stat().st_size
    assert (evidence / "stdout.log").read_text(encoding="utf-8") == "known-stdout\n"
    assert (evidence / "stderr.log").read_text(encoding="utf-8") == "known-stderr\n"
    assert not (evidence / "active.lock").exists()
    assert not Path(launch["duplicate_lock"]).exists()


def test_supervisor_observes_instant_exit_without_getpgid_race(tmp_path: Path):
    evidence = tmp_path / "instant"
    command = supervisor_command(
        tmp_path,
        evidence,
        [sys.executable, "-c", "raise SystemExit(0)"],
        run_id="instant-001",
    )
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    terminal = json.loads((evidence / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["terminal_state"] == "normal_exit"
    assert terminal["exit_code"] == 0
    assert terminal["child_exists_after_wait"] is False
    assert not (evidence / "active.lock").exists()
    assert not Path(terminal["duplicate_lock"]).exists()


def test_supervisor_timeout_is_terminal_and_reaped(tmp_path: Path):
    evidence = tmp_path / "timeout"
    command = supervisor_command(
        tmp_path,
        evidence,
        [sys.executable, "-c", "import time; time.sleep(10)"],
        run_id="timeout-001",
        timeout="0.08",
    )
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 124, completed.stderr
    terminal = json.loads((evidence / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["terminal_state"] == "timeout"
    assert terminal["timed_out"] is True
    assert terminal["terminating_signal"] in {signal.SIGTERM, signal.SIGKILL}
    assert terminal["child_exists_after_wait"] is False
    assert not (evidence / "active.lock").exists()
    assert not Path(terminal["duplicate_lock"]).exists()


def test_shared_lock_refuses_duplicate_command_and_cwd(tmp_path: Path):
    child = [sys.executable, "-c", "import time; time.sleep(0.5)"]
    first_evidence = tmp_path / "first"
    second_evidence = tmp_path / "second"
    first = subprocess.Popen(
        supervisor_command(
            tmp_path, first_evidence, child, run_id="duplicate-first", timeout="2"
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_file(first_evidence / "launch.json")
        second = subprocess.run(
            supervisor_command(
                tmp_path, second_evidence, child,
                run_id="duplicate-second", timeout="2",
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        assert second.returncode == 2
        assert "identical command/cwd is already locked" in second.stderr
        assert not (second_evidence / "launch.json").exists()
        assert not (second_evidence / "active.lock").exists()
    finally:
        first_stdout, first_stderr = first.communicate(timeout=5)
    assert first.returncode == 0, (first_stdout, first_stderr)
    first_terminal = json.loads(
        (first_evidence / "terminal.json").read_text(encoding="utf-8")
    )
    assert not Path(first_terminal["duplicate_lock"]).exists()


def test_input_sha_is_verified_before_and_after_run(tmp_path: Path):
    input_path = tmp_path / "transfer-state.bin"
    input_path.write_bytes(b"validated-transfer-state\n")
    expected = digest(input_path)
    evidence = tmp_path / "input-ok"
    command = supervisor_command(
        tmp_path,
        evidence,
        [sys.executable, "-c", "raise SystemExit(0)"],
        run_id="input-ok-001",
        extra=["--input-file-sha256", input_path.name, expected],
    )
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    launch = json.loads((evidence / "launch.json").read_text(encoding="utf-8"))
    terminal = json.loads((evidence / "terminal.json").read_text(encoding="utf-8"))
    assert launch["verified_inputs"] == [{
        "expected_sha256": expected,
        "observed_sha256": expected,
        "requested_path": input_path.name,
        "resolved_path": str(input_path.resolve()),
        "size_bytes": input_path.stat().st_size,
        "verified": True,
    }]
    assert terminal["verified_inputs"][0]["observed_sha256_after"] == expected
    assert terminal["verified_inputs"][0]["unchanged_during_run"] is True
    assert terminal["input_identity_changed"] is False


def test_input_sha_mismatch_fails_before_child_launch(tmp_path: Path):
    input_path = tmp_path / "transfer-state.bin"
    input_path.write_bytes(b"actual\n")
    marker = tmp_path / "child-ran"
    evidence = tmp_path / "input-bad"
    child = [
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
    ]
    command = supervisor_command(
        tmp_path,
        evidence,
        child,
        run_id="input-bad-001",
        extra=["--input-file-sha256", input_path.name, "0" * 64],
    )
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 2
    assert "input SHA-256 mismatch" in completed.stderr
    assert not marker.exists()
    assert not (evidence / "launch.json").exists()


def test_supervisor_error_after_launch_terminates_and_reaps_child(
    tmp_path: Path, monkeypatch
):
    spec = importlib.util.spec_from_file_location("supervisor_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    real_atomic_json = module.atomic_json

    def fail_launch_once(path, record):
        if path.name == "launch.json":
            raise OSError("injected launch-record failure")
        return real_atomic_json(path, record)

    monkeypatch.setattr(module, "atomic_json", fail_launch_once)
    evidence = tmp_path / "metadata-failure"
    args = supervisor_command(
        tmp_path,
        evidence,
        [sys.executable, "-c", "import time; time.sleep(10)"],
        run_id="metadata-failure-001",
    )[2:]
    result = module.main(args)
    assert result == 125
    terminal = json.loads((evidence / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["terminal_state"] == "supervisor_error"
    assert terminal["supervisor_error"]["type"] == "OSError"
    assert terminal["child_exists_after_wait"] is False
    assert not (evidence / "active.lock").exists()
    assert not Path(terminal["duplicate_lock"]).exists()


def test_supervisor_refuses_nonempty_evidence_directory(tmp_path: Path):
    evidence = tmp_path / "occupied"
    evidence.mkdir()
    (evidence / "foreign.txt").write_text("keep", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable, str(SCRIPT), "--evidence-dir", str(evidence),
            "--cwd", str(tmp_path), "--lock-root", str(tmp_path / "locks"),
            "--timeout-seconds", "1", "--",
            sys.executable, "-c", "raise SystemExit(0)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "evidence directory must be a new empty directory" in completed.stderr
    assert (evidence / "foreign.txt").read_text(encoding="utf-8") == "keep"
