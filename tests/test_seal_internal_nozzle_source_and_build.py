from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seal_internal_nozzle_source_and_build.py"
SPEC = importlib.util.spec_from_file_location("seal_source_build", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    (repo / "src.c").write_text("int main(void){return 0;}\n", encoding="utf-8")
    git(repo, "add", "src.c")
    git(repo, "commit", "-qm", "fixture")
    commit = git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(MODULE, "SOURCE_PATHS", ("src.c",))
    monkeypatch.setattr(MODULE, "BUILD_ROLES", {
        "pressure_driven": {
            "entry_source": "src.c",
            "required_defines": ("INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1",),
            "forbidden_defines": ("INTERNAL_NOZZLE_PROFILE_CONTROLLED",),
        },
    })
    basilisk = tmp_path / "basilisk"
    (basilisk / "navier-stokes").mkdir(parents=True)
    timestep = basilisk / "timestep.h"
    timestep.write_text("timestep\n", encoding="utf-8")
    monkeypatch.setattr(MODULE, "EXPECTED_TIMESTEP_SHA256", sha(timestep))
    centered = basilisk / "navier-stokes" / "centered.h"
    centered.write_text(
        f"{MODULE.ORIGINAL_INCLUDE}\n{MODULE.ORIGINAL_EMBED}\n"
        f"{MODULE.ORIGINAL_PREDICTION}  }}\n", encoding="utf-8"
    )
    expected, _ = MODULE.prepared_centered_bytes(basilisk)
    prepared = tmp_path / "internal_nozzle_centered.h"
    prepared.write_bytes(expected)
    qcc = tmp_path / "qcc"
    qcc.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    qcc.chmod(0o700)
    return repo, commit, basilisk, qcc, prepared


def test_source_bundle_requires_clean_exact_committed_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, commit, basilisk, qcc, prepared = fixture(tmp_path, monkeypatch)
    result = MODULE.seal_source(repo, commit, basilisk, qcc, prepared)
    assert result["scientific_commit"] == commit
    assert result["tracked_behavior_file_count"] == 1
    assert result["prepared_centered"]["sha256"] == sha(prepared)
    (repo / "untracked").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="worktree must be clean"):
        MODULE.seal_source(repo, commit, basilisk, qcc, prepared)


def test_wrong_commit_and_prepared_header_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, commit, basilisk, qcc, prepared = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="expected commit"):
        MODULE.seal_source(repo, "0" * 40, basilisk, qcc, prepared)
    prepared.write_text("wrong\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact authorized transform"):
        MODULE.seal_source(repo, commit, basilisk, qcc, prepared)


def test_build_seal_requires_complete_immutable_compile_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, commit, basilisk, qcc, prepared = fixture(tmp_path, monkeypatch)
    bundle = tmp_path / "source-bundle.json"
    bundle.write_text(json.dumps(
        MODULE.seal_source(repo, commit, basilisk, qcc, prepared)
    ), encoding="utf-8")
    bundle_sha = sha(bundle)
    binary = tmp_path / "solver"
    binary.write_bytes(b"binary")
    binary.chmod(0o700)
    evidence = tmp_path / "compile"
    evidence.mkdir()
    argv = [
        str(qcc.resolve()), "-DINTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1",
        str((repo / "src.c").resolve()), "-o", str(binary.resolve()),
    ]
    expected = {
        str(bundle.resolve()): bundle_sha,
        str(qcc.resolve()): sha(qcc),
        str(prepared.resolve()): sha(prepared),
        str((repo / "src.c").resolve()): sha(repo / "src.c"),
    }
    verified = [{
        "resolved_path": path, "expected_sha256": digest,
        "observed_sha256": digest, "observed_sha256_after": digest,
        "verified": True, "unchanged_during_run": True,
    } for path, digest in expected.items()]
    common = {
        "run_id": "qcc-001", "cwd": str(repo.resolve()), "argv": argv,
        "child_pid": 123, "source_commit": commit, "source_sha256": bundle_sha,
        "verified_inputs": verified,
    }
    (evidence / "launch.json").write_text(json.dumps(common), encoding="utf-8")
    (evidence / "terminal.json").write_text(json.dumps({
        **common, "exit_code": 0, "terminal_state": "normal_exit",
        "input_identity_changed": False, "child_exists_after_wait": False,
    }), encoding="utf-8")
    result = MODULE.seal_build(
        bundle, bundle_sha, evidence, binary, "pressure_driven",
    )
    assert result["binary"]["sha256"] == sha(binary)
    assert result["build_role"] == "pressure_driven"
    terminal = json.loads((evidence / "terminal.json").read_text(encoding="utf-8"))
    terminal["verified_inputs"] = terminal["verified_inputs"][:-1]
    (evidence / "terminal.json").write_text(json.dumps(terminal), encoding="utf-8")
    with pytest.raises(ValueError, match="complete source-input set"):
        MODULE.seal_build(bundle, bundle_sha, evidence, binary, "pressure_driven")


def test_build_seal_rejects_wrong_binary_and_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, commit, basilisk, qcc, prepared = fixture(tmp_path, monkeypatch)
    bundle = tmp_path / "source-bundle.json"
    bundle.write_text(json.dumps(
        MODULE.seal_source(repo, commit, basilisk, qcc, prepared)
    ), encoding="utf-8")
    binary = tmp_path / "solver"
    binary.write_bytes(b"binary")
    binary.chmod(0o700)
    evidence = tmp_path / "compile"
    evidence.mkdir()
    common = {
        "run_id": "qcc-001", "cwd": str(repo.resolve()),
        "argv": [str(qcc.resolve()), "-o", str(binary.resolve())],
        "child_pid": 123, "source_commit": commit, "source_sha256": sha(bundle),
        "verified_inputs": [],
    }
    (evidence / "launch.json").write_text(json.dumps(common), encoding="utf-8")
    (evidence / "terminal.json").write_text(json.dumps({
        **common, "exit_code": 1, "terminal_state": "normal_exit",
        "input_identity_changed": False, "child_exists_after_wait": False,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="successful compile"):
        MODULE.seal_build(bundle, sha(bundle), evidence, binary, "pressure_driven")
