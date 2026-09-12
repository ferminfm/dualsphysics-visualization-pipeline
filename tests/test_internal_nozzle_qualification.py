"""Inert children only. All synthetic claims stay in an isolated test root."""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import internal_nozzle_qualification as gate


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, sort_keys=True) + "\n")
    return p


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def fixture(tmp_path, monkeypatch, production=False):
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    s = tmp_path / "SYNTHETIC-gate-only"; s.mkdir()
    root = s / "source"; root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic Test")
    git(root, "config", "user.email", "synthetic@example.invalid")
    for rel in gate.GATE_FILES:
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SCRIPTS / p.name, p)
    source = root / "material.c"; source.write_text("/* SYNTHETIC inert source; no CFD */\n")
    git(root, "add", "scripts", "material.c"); git(root, "commit", "-qm", "SYNTHETIC fixture only")
    commit = git(root, "rev-parse", "HEAD")
    batch = s / gate.BATCH; batch.mkdir()
    run = batch / "case-b"; run.mkdir()
    solver = s / "inert-child.py"
    solver.write_text("#!" + sys.executable + "\nfrom pathlib import Path\nPath('SPAWN_MARKER').write_text('one inert child')\n")
    solver.chmod(0o700)
    tool = s / "toolchain.txt"; tool.write_text("SYNTHETIC no compiler")
    prepared = s / "prepared.txt"; prepared.write_text("SYNTHETIC no CFD header")
    bundle = write(s / "bundle.json", {"scientific_commit": commit,
        "tracked_behavior_files": [{"path": "material.c", "sha256": gate.digest(source)}],
        "basilisk": {"qcc_path": str(tool), "qcc_sha256": gate.digest(tool)},
        "prepared_centered": {"path": str(prepared), "sha256": gate.digest(prepared)}})
    checkpoint = s / "checkpoint.txt"; checkpoint.write_text("SYNTHETIC checkpoint")
    config = write(s / "config.json", {"SYNTHETIC": True, "criteria": gate.CRITERIA})
    input_paths = [solver, bundle, tool, prepared, checkpoint, config]
    contract = {"schema": "internal_nozzle_bound_launch_v3", "batch_identity": {"batch_id": gate.BATCH, "batch_root": str(batch)},
        "case_role": "B", "segment_id": "synthetic-one", "scientific_source_commit": commit,
        "source_bundle_manifest": {"path": str(bundle), "sha256": gate.digest(bundle)},
        "cwd": str(run), "solver": {"path": str(solver), "sha256": gate.digest(solver)},
        "solver_argv": [str(solver), "--domain", "full", "--case-role", "B", "--output-dir", str(run),
            "--end-time", str(2.1 * gate.DH), "--case-mode", "0", "--pressure", "351.48", "--external-dh", "21",
            "--refine-external-dh", "6", "--baselevel", "4", "--maxlevel", "8"],
        "supervisor_argv": [sys.executable, str(SCRIPTS / "supervise_internal_nozzle_run.py"), "--timeout-seconds", "5"],
        "verified_inputs": [{"label": p.name, "path": str(p), "sha256": gate.digest(p)} for p in input_paths]}
    material = [gate.file_record(p) for p in sorted(input_paths + [source] + [root / r for r in gate.GATE_FILES])]
    out = s / "stdout.log"; out.write_text("SYNTHETIC fixture result; no scientific observation\n")
    err = s / "stderr.log"; err.write_text("")
    terminal = write(s / "terminal.json", {"run_id": "SYNTHETIC", "argv": ["synthetic-inert-only"], "cwd": str(s),
        "returncode": 0, "terminal_state": "exited", "stdout": gate.file_record(out), "stderr": gate.file_record(err)})
    checks = {}
    for name in (gate.CHECKS if production else {"launch_gate_regression"}):
        rows = [{"metric": m, "left": 0.0, "right": 0.0, "scale_floor": 0 if k == "cumulative_rtol" else 1,
                 "tolerance": gate.CRITERIA[k], "criterion": k} for m, k in gate.OBLIGATIONS[name].items()]
        p = write(s / (name + ".json"), {"schema": "internal_nozzle_measured_qualification_v1", "name": name,
            "material_sha256": gate.fingerprint(material), "criteria": gate.CRITERIA, "inputs": [gate.file_record(config)],
            "terminals": [gate.file_record(terminal)], "comparisons": rows, "failures": []})
        checks[name] = gate.file_record(p)
    authority = {"schema": gate.SCHEMA, "mode": "production" if production else "diagnostic",
        "purpose": "matched_ab_confirmation" if production else "restart_tstar_2", "binding": gate.binding(contract),
        "material_sha256": gate.fingerprint(material), "material_files": material, "source_root": str(root), "source_commit": commit,
        "expires_utc": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat(),
        "maximum_starts": 1, "maximum_t_star": 2.2, "maximum_wall_seconds": 5, "plan_end_time": 2.1 * gate.DH,
        "plan_t_star": 2.1, "checks": checks, "synthetic_root": str(s)}
    a = write(s / "authority.json", authority)
    return {"s": s, "root": root, "batch": batch, "run": run, "contract": contract, "a": a, "authority": authority,
            "checkpoint": checkpoint, "solver": solver, "source": source, "terminal": terminal}


def launch(f, mutate_after_reservation=None):
    c = f["contract"]; ticket = f["run"] / ("qualification-ticket." + c["segment_id"] + ".json")
    with gate.reserve(f["a"], c, f["batch"] / "qualification-start-ledger.json", ticket):
        if mutate_after_reservation:
            mutate_after_reservation()
        command = [sys.executable, str(SCRIPTS / "supervise_internal_nozzle_run.py"),
            "--cwd", c["cwd"], "--evidence-dir", str(f["run"] / "evidence"),
            "--timeout-seconds", "5", "--heartbeat-seconds", ".01", "--qualification-ticket", str(ticket), "--", *c["solver_argv"]]
        return subprocess.run(command, capture_output=True, text=True)


@pytest.mark.parametrize("production", [False, True])
def test_exact_valid_fixture_launches_once(tmp_path, monkeypatch, production):
    f = fixture(tmp_path, monkeypatch, production)
    p = launch(f); assert p.returncode == 0, p.stderr
    assert (f["run"] / "SPAWN_MARKER").read_text() == "one inert child"
    with pytest.raises(ValueError, match="duplicate ticket"):
        launch(f)
    terminal = gate.load(f["run"] / "evidence/terminal.json")
    assert terminal["exit_code"] == 0 and terminal["child_exists_after_wait"] is False


@pytest.mark.parametrize("defect", ["missing", "failed", "stale", "wrong-case", "wrong-binary", "source", "checkpoint", "criteria",
    "over-horizon", "wrong-horizon-mapping", "boolean-counter", "zero-budget", "duplicate-key", "corrupt-record", "symlink",
    "traversal", "missing-closure", "wrong-source-commit", "untracked-source", "changed-toolchain", "missing-measurement",
    "failed-measurement", "failed-terminal", "corrupt-output", "unknown-purpose", "missing-gate-test", "wrong-omp"])
def test_adversarial_no_spawn(tmp_path, monkeypatch, defect):
    f = fixture(tmp_path, monkeypatch, True); a = f["authority"]; c = f["contract"]
    if defect == "failed": a["checks"].pop("precursor")
    elif defect == "stale": a["expires_utc"] = "2000-01-01T00:00:00+00:00"
    elif defect == "wrong-case": c["case_role"] = "C"
    elif defect == "wrong-binary": f["solver"].write_text("changed")
    elif defect == "source": f["source"].write_text("changed")
    elif defect == "checkpoint": f["checkpoint"].write_text("changed")
    elif defect == "criteria": a["binding"]["criteria"]["restart_core"] = 1
    elif defect == "over-horizon": a["maximum_t_star"] = 1
    elif defect == "wrong-horizon-mapping": a["plan_t_star"] = 1
    elif defect == "boolean-counter": a["maximum_starts"] = True
    elif defect == "zero-budget": a["maximum_starts"] = 0
    elif defect == "corrupt-record": a["extra"] = "not allowed"
    elif defect == "missing-closure": a["material_files"] = a["material_files"][:1]; a["material_sha256"] = gate.fingerprint(a["material_files"])
    elif defect == "wrong-source-commit": a["source_commit"] = "b" * 40
    elif defect == "untracked-source": git(f["root"], "rm", "--cached", "material.c"); git(f["root"], "commit", "-qm", "untrack"); a["source_commit"] = git(f["root"], "rev-parse", "HEAD")
    elif defect == "changed-toolchain": (f["s"] / "toolchain.txt").write_text("changed")
    elif defect in {"missing-measurement", "failed-measurement"}:
        p = Path(a["checks"]["restart_tstar_2"]["path"]); obj = gate.load(p)
        if defect == "missing-measurement": obj["comparisons"].pop()
        else: obj["comparisons"][0]["left"] = 1
        write(p, obj); a["checks"]["restart_tstar_2"] = gate.file_record(p)
    elif defect == "failed-terminal": obj = gate.load(f["terminal"]); obj["returncode"] = 1; write(f["terminal"], obj)
    elif defect == "corrupt-output": (f["s"] / "stdout.log").write_text("changed")
    elif defect == "unknown-purpose": a["purpose"] = "unlimited"
    elif defect == "missing-gate-test": a["checks"].pop("launch_gate_regression")
    elif defect == "wrong-omp": monkeypatch.setenv("OMP_NUM_THREADS", "2")
    write(f["a"], a)
    if defect == "missing": f["a"] = f["s"] / "absent.json"
    elif defect == "symlink": p = f["s"] / "link.json"; p.symlink_to(f["a"]); f["a"] = p
    elif defect == "traversal": f["a"] = f["run"] / ".." / ".." / "authority.json"
    elif defect == "duplicate-key": f["a"].write_text('{"schema":"a","schema":"b"}')
    with pytest.raises((ValueError, KeyError, OSError, subprocess.CalledProcessError)):
        launch(f)
    assert not (f["run"] / "SPAWN_MARKER").exists()


def test_invalidation_after_reservation_prevents_spawn(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    p = launch(f, lambda: f["checkpoint"].write_text("changed after parent validation"))
    assert p.returncode != 0 and "changed" in p.stderr
    assert not (f["run"] / "SPAWN_MARKER").exists()
    assert len(gate.load(f["batch"] / "qualification-start-ledger.json")["starts"]) == 1


def test_concurrent_reservation_is_rejected(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); c = f["contract"]
    with gate.reserve(f["a"], c, f["batch"] / "qualification-start-ledger.json", f["run"] / "qualification-ticket.synthetic-one.json"):
        other = copy.deepcopy(c); other["segment_id"] = "different"
        with pytest.raises(BlockingIOError):
            with gate.reserve(f["a"], other, f["batch"] / "qualification-start-ledger.json", f["run"] / "qualification-ticket.different.json"):
                pytest.fail("concurrent reservation")
    assert not (f["run"] / "SPAWN_MARKER").exists()


def test_direct_supervisor_and_historical_entry_rejected(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    p = subprocess.run([sys.executable, str(SCRIPTS / "supervise_internal_nozzle_run.py"), "--cwd", str(f["run"]),
        "--evidence-dir", str(f["run"] / "direct"), "--timeout-seconds", "5", "--", *f["contract"]["solver_argv"]], capture_output=True, text=True)
    assert p.returncode != 0 and "direct successor" in p.stderr
    import launch_internal_nozzle_precursor_case as old
    monkeypatch.setattr(old, "parse_args", lambda argv: type("Args", (), {"batch_id": gate.BATCH, "cwd": f["run"]})())
    with pytest.raises(ValueError, match="requires launch_internal_nozzle_qualified"):
        old.main([])
    assert not (f["run"] / "SPAWN_MARKER").exists()


def test_successor_identity_does_not_promote_predecessor_permit(tmp_path, monkeypatch):
    assert gate.BATCH == "20260912-internal-nozzle-restart-state-closure-r1"
    f = fixture(tmp_path, monkeypatch)
    assert gate.scoped(f["run"])
    wrong = copy.deepcopy(f["contract"])
    wrong["batch_identity"]["batch_id"] = "20260905-internal-nozzle-restart-diagnostic-qualification-r1"
    with pytest.raises(ValueError, match="wrong batch"):
        gate.binding(wrong)
    assert not (f["run"] / "SPAWN_MARKER").exists()


@pytest.mark.parametrize("defect", ["permit_exhausted", "full_budget", "boolean_resolution", "corrupt_hash", "duplicate_segment", "alternate_ledger"])
def test_start_ledger_fail_closed(tmp_path, monkeypatch, defect):
    f = fixture(tmp_path, monkeypatch)
    row = {"record_sha256": gate.digest(f["a"]), "segment_id": "past-one",
           "ticket_path": str(f["run"] / "old.json"), "full_target_resolution": True}
    rows = [row]
    if defect == "full_budget":
        rows = [{**row, "record_sha256": "a" * 64, "segment_id": "past-" + str(i)} for i in range(12)]
    elif defect == "boolean_resolution": row["full_target_resolution"] = 1
    elif defect == "corrupt_hash": row["record_sha256"] = True
    elif defect == "duplicate_segment": rows = [row, dict(row)]
    path = write(f["batch"] / "qualification-start-ledger.json", {"schema": "nozzle_gate_start_ledger_v1", "starts": rows})
    if defect == "alternate_ledger": path = f["batch"] / "alternate.json"
    with pytest.raises(ValueError):
        with gate.reserve(f["a"], f["contract"], path, f["run"] / "qualification-ticket.synthetic-one.json"):
            pytest.fail("invalid/exhausted ledger accepted")
    assert not (f["run"] / "SPAWN_MARKER").exists()


@pytest.mark.parametrize("mode", ["valid-diagnostic", "production", "wrong-identity", "duplicate-metadata"])
def test_historical_diagnostic_identity_never_qualifies_production(tmp_path, monkeypatch, mode):
    f = fixture(tmp_path, monkeypatch, mode == "production")
    metadata = f["s"] / "historical.meta"
    metadata.write_text("schema=internal_nozzle_checkpoint_metadata_v7\nsource_sha256=" + "a"*64 +
        "\nscientific_source_commit=" + "b"*40 + "\nsolver_sha256=" + "c"*64 + "\nexecution_id=historic-test\n")
    c=f["contract"]; a=f["authority"]
    c["restore"]={"kind":"checkpoint", "metadata":{"path":str(metadata),"sha256":gate.digest(metadata)}}
    if mode == "duplicate-metadata":
        with metadata.open("a") as fp: fp.write("execution_id=ambiguous\n")
        c["restore"]["metadata"]["sha256"]=gate.digest(metadata)
        with pytest.raises(ValueError, match="duplicate historical"):
            gate.bind_historical_diagnostic_restore(c)
        return
    gate.bind_historical_diagnostic_restore(c)
    if mode == "wrong-identity":
        i=c["solver_argv"].index("--diagnostic-restore-execution-id");c["solver_argv"][i+1]="forged"
    a["binding"]=gate.binding(c)
    a["material_files"].append(gate.file_record(metadata));a["material_sha256"]=gate.fingerprint(a["material_files"])
    for k, row in a["checks"].items():
        p=Path(row["path"]); check=gate.load(p);check["material_sha256"]=a["material_sha256"];write(p,check);a["checks"][k]=gate.file_record(p)
    write(f["a"],a)
    if mode == "valid-diagnostic": assert gate.validate(f["a"],c)["mode"] == "diagnostic"
    else:
        with pytest.raises(ValueError, match="historical restore forbidden|differs from pinned"):
            gate.validate(f["a"],c)
    assert not (f["run"] / "SPAWN_MARKER").exists()
