"""Fail-closed software launch gate for the restart-qualification successor.

Certificates bind checked evidence, not credentials. This module makes no
kernel-security claim. Synthetic fixtures are confined to an isolated root.
The sole parent must never execute a scientific binary around this interface.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
from verify_internal_nozzle_step_integral import checkpoint_state_from_fields

BATCH = "20260912-internal-nozzle-restart-state-closure-r1"
SCHEMA = "internal_nozzle_qualification_authority_v1"
CHECKS = {"precursor", "transfer_projection_impulse", "restart_tstar_1",
          "restart_tstar_2", "cumulative_same_step", "solver_health_identity",
          "launch_gate_regression"}
PURPOSES = {"initialization_projection", "restart_tstar_1", "restart_tstar_2",
            "same_step_cumulative", "instrumentation_equivalence"}
CRITERIA = {"restart_core": 1e-7, "restart_profile": 1e-8,
            "restart_raw": 1e-8, "cumulative_rtol": 5e-8,
            "cumulative_atol": 1e-12, "exact_count": 0.0,
            "precursor_Q_drift": .001, "precursor_J_drift": .002,
            "precursor_pressure_drift": .001, "precursor_profile_L2": .005,
            "precursor_mass_imbalance": .005,
            "transfer_divergence_L2": .001, "transfer_divergence_max": .05,
            "transfer_velocity_impulse": .02, "transfer_pressure_change": .01}
DH = (2.0 / 3.0) * math.sqrt(2.0 * math.pi / 144.0)
GATE_FILES = {"scripts/internal_nozzle_qualification.py",
              "scripts/verify_internal_nozzle_step_integral.py",
              "scripts/launch_internal_nozzle_qualified.py",
              "scripts/launch_internal_nozzle_precursor_case.py",
              "scripts/supervise_internal_nozzle_run.py"}
PLANES = ("geometric_nozzle_exit", "inlet_boundary_adjacent", "legacy_exit_inner",
          "mid_straight", "near_exit_projected_aperture", "post_contraction",
          "pre_contraction", "upstream_plenum")
CORE = "J_k_liquid J_k_mixture J_p J_total Q_l area_mean_pressure area_weighted_liquid_velocity fluid_area flux_weighted_liquid_velocity forcing_to_plane_pressure_drop liquid_area mdot_l mdot_mix".split()
PROFILE = "I2_liquid I3_liquid alpha beta cumulative_discharged_liquid_volume cumulative_liquid_inflow cumulative_liquid_outflow cumulative_nozzle_exit_discharge cumulative_nozzle_exit_net_volume momentum_equivalent_velocity".split()
RAW = "active_front active_front_Dh cumulative_liquid_inflow cumulative_liquid_outflow exit_flow exit_liquid_area interface_growth interface_proxy liquid_inventory_change_fraction liquid_mass_balance_relative_error liquid_mass_balance_residual liquid_volume mean_exit_velocity profile_sanity".split()
RESTART = {**{p + "/" + m: "restart_core" for p in PLANES for m in CORE},
           **{p + "/" + m: "restart_profile" for p in PLANES for m in PROFILE},
           **{"raw/" + m: "restart_raw" for m in RAW},
           **{"exact/" + m: "exact_count" for m in "grid_maxdepth i mgp_i mgpf_i mgu_i total_grid_cells detached_proxy_count one_cell_debris_count post_tag_count fallback_generation_errors duplicate_outputs checkpoint_identity_errors".split()}}
OBLIGATIONS = {
    "launch_gate_regression": {"failed_test_count": "exact_count"},
    "precursor": {"Q_relative_drift": "precursor_Q_drift", "J_k_relative_drift": "precursor_J_drift",
                  "pressure_drop_relative_drift": "precursor_pressure_drift", "profile_L2_change": "precursor_profile_L2",
                  "mass_flow_imbalance": "precursor_mass_imbalance", "unresolved_monotonic_trends": "exact_count",
                  "solver_health_violations": "exact_count"},
    "transfer_projection_impulse": {"divergence_l2_normalized": "transfer_divergence_L2",
        "divergence_max_normalized": "transfer_divergence_max", "velocity_impulse_l2_normalized": "transfer_velocity_impulse",
        "cell_pressure_change_l2_normalized": "transfer_pressure_change", "projection_pressure_adjustment_l2_normalized": "transfer_pressure_change",
        "mapping_identity_violations": "exact_count", "initialization_identity_violations": "exact_count"},
    "restart_tstar_1": RESTART, "restart_tstar_2": RESTART,
    "cumulative_same_step": {"signed_net": "cumulative_rtol", "positive_net": "cumulative_rtol",
        "omitted_or_duplicate_steps": "exact_count", "restart_accumulator_errors": "exact_count", "manufactured_test_failures": "exact_count"},
    "solver_health_identity": {"health_limit_violations": "exact_count", "material_identity_violations": "exact_count",
        "instrumentation_equivalence_failures": "exact_count", "unresolved_field_event_identity_errors": "exact_count"},
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def exact(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys),
            label + ": closed key set mismatch")


def integer(value, lo, hi, label):
    require(type(value) is int and lo <= value <= hi, label + ": invalid integer")
    return value


def number(value, lo, hi, label):
    require(type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi,
            label + ": invalid finite number")
    return value


def regular(path):
    p = Path(path)
    require(p.is_absolute() and ".." not in p.parts, "noncanonical/traversing path")
    require(all(not q.is_symlink() for q in (p, *p.parents)), "symlink path")
    require(p.is_file() and p.resolve(strict=True) == p, "missing/nonregular path")
    return p


def digest(path):
    h = hashlib.sha256()
    with regular(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(encode(value)).hexdigest()


def load(path):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "duplicate JSON key: " + key)
            out[key] = value
        return out
    value = json.loads(regular(path).read_text(), object_pairs_hook=pairs,
                       parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    require(isinstance(value, dict), "record must be an object")
    return value


def file_record(path):
    p = regular(path)
    return {"path": str(p), "size_bytes": p.stat().st_size, "sha256": digest(p)}


def verify_file(record):
    exact(record, {"path", "size_bytes", "sha256"}, "file record")
    integer(record["size_bytes"], 0, 2**50, "file size")
    require(isinstance(record["sha256"], str) and
            re.fullmatch("[0-9a-f]{64}", record["sha256"]), "malformed SHA-256")
    require(file_record(record["path"]) == record, "file identity changed: " + record["path"])
    return Path(record["path"])


def atomic(path, value):
    path = Path(path)
    require(not path.is_symlink() and ".." not in path.parts, "unsafe record destination")
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encode(value) + b"\n"); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def option(argv, key):
    indices = [i for i, x in enumerate(argv) if x == key]
    require(len(indices) == 1 and indices[0] + 1 < len(argv), "missing/duplicate option " + key)
    return argv[indices[0] + 1]


DIAGNOSTIC_IDENTITY_OPTIONS = {
    "--restore-source-sha": "source_sha256",
    "--diagnostic-restore-source-commit": "scientific_source_commit",
    "--diagnostic-restore-solver-sha256": "solver_sha256",
    "--diagnostic-restore-execution-id": "execution_id",
}


def historical_metadata(contract):
    require(contract["restore"]["kind"] == "checkpoint", "historical diagnostic requires exact checkpoint")
    r = contract["restore"]["metadata"]
    p = regular(r["path"])
    require(digest(p) == r["sha256"], "historical metadata changed")
    fields = {}
    for line in p.read_text().splitlines():
        require("=" in line, "malformed historical metadata")
        k, v = line.split("=", 1)
        require(k not in fields, "duplicate historical metadata key")
        fields[k] = v
    require(fields.get("schema") in {"internal_nozzle_checkpoint_metadata_v7", "internal_nozzle_checkpoint_metadata_v8"}, "unsupported historical checkpoint")
    if fields['schema']=='internal_nozzle_checkpoint_metadata_v8':
        checkpoint_state_from_fields(fields)
    for key in DIAGNOSTIC_IDENTITY_OPTIONS.values():
        require(key in fields, "missing historical identity " + key)
        if key != "execution_id":
            require(re.fullmatch("[0-9a-f]{%d}" % (40 if key == "scientific_source_commit" else 64), fields[key]), "bad historical identity")
    return fields


def bind_historical_diagnostic_restore(contract):
    fields = historical_metadata(contract)
    require(not any(x in contract["solver_argv"] for x in DIAGNOSTIC_IDENTITY_OPTIONS), "duplicate diagnostic identity")
    tail = []
    for option_name, field in DIAGNOSTIC_IDENTITY_OPTIONS.items():
        tail.extend([option_name, fields[field]])
    contract["solver_argv"].extend(tail)
    contract["supervisor_argv"].extend(tail)
    contract["diagnostic_restore"] = {
        "classification": "historical_checkpoint_new_diagnostic_binary_not_production_qualification",
        "metadata": file_record(contract["restore"]["metadata"]["path"]),
        "predecessor_identity": {key: fields[key] for key in DIAGNOSTIC_IDENTITY_OPTIONS.values()},
    }


def binding(contract):
    """Full argv covers BCs, phase/geometry/mesh, schedule, restore and horizon.

    Referenced source/build/schedule/transfer/closure bytes are rehashed. There
    is no packaging-descendant exception: reissue the exact binding if needed.
    """
    require(contract["schema"] == "internal_nozzle_bound_launch_v3", "wrong launch schema")
    require(contract["batch_identity"]["batch_id"] == BATCH, "wrong batch")
    require(contract["case_role"] in {"A", "B"}, "only A/B allowed")
    argv = contract["solver_argv"]
    require(isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv), "invalid argv")
    require(argv[0] == contract["solver"]["path"], "wrong executable")
    require(digest(argv[0]) == contract["solver"]["sha256"], "changed binary")
    require(option(argv, "--domain") == "full", "physical domain identity")
    require(option(argv, "--case-role") == contract["case_role"], "wrong case")
    require(option(argv, "--output-dir") == contract["cwd"], "wrong cwd")
    require(option(argv, "--case-mode") == "0" and
            float(option(argv, "--pressure")) == 351.48 and
            float(option(argv, "--external-dh")) == 21 and
            float(option(argv, "--refine-external-dh")) == 6 and
            option(argv, "--baselevel") == "4", "wrong physical configuration")
    require(option(argv, "--maxlevel") in {"4", "5", "6", "7", "8"}, "resolution outside diagnostic authority")
    require(os.environ.get("OMP_NUM_THREADS") == "1", "OMP_NUM_THREADS must be one")
    inputs = contract["verified_inputs"]
    require(isinstance(inputs, list) and inputs, "missing material inputs")
    paths = set()
    for row in inputs:
        exact(row, {"label", "path", "sha256"}, "bound input")
        require(row["path"] not in paths, "duplicate bound input")
        paths.add(row["path"])
        require(digest(row["path"]) == row["sha256"], "changed bound input")
    return {"contract_sha256": fingerprint(contract), "criteria": dict(CRITERIA),
            "gate_sha256": digest(Path(__file__).resolve()),
            "case_role": contract["case_role"], "batch_id": BATCH}


def verify_terminal(record):
    terminal = load(verify_file(record))
    rc = terminal.get("exit_code", terminal.get("returncode"))
    require(type(rc) is int and rc == 0, "qualification process did not PASS")
    require(terminal.get("terminal_state") in {"normal_exit", "exited"}, "unobserved terminal state")
    require(terminal.get("run_id") and terminal.get("argv") and terminal.get("cwd"), "incomplete terminal identity")
    for name in ("stdout", "stderr"):
        if isinstance(terminal.get(name), dict):
            r = terminal[name]
            verify_file({"path": r["path"], "size_bytes": r.get("size_bytes", r.get("size")), "sha256": r["sha256"]})
        else:
            p = Path(record["path"]).parent / (name + ".log")
            verify_file({"path": str(p), "size_bytes": terminal[name + "_size_bytes"],
                         "sha256": terminal[name + "_sha256"]})
    return terminal


def verify_check(record, name, material_id):
    check = load(verify_file(record))
    exact(check, {"schema", "name", "material_sha256", "criteria", "inputs", "terminals", "comparisons", "failures"}, "qualification check")
    require(check["schema"] == "internal_nozzle_measured_qualification_v1" and check["name"] == name, "wrong check identity")
    require(check["material_sha256"] == material_id and check["criteria"] == CRITERIA, "stale/wrong criteria or material")
    require(check["failures"] == [] and check["inputs"] and check["terminals"] and check["comparisons"], "failed/incomplete check")
    for row in check["inputs"]:
        verify_file(row)
    for row in check["terminals"]:
        verify_terminal(row)
    seen = set()
    for row in check["comparisons"]:
        exact(row, {"metric", "left", "right", "scale_floor", "tolerance", "criterion"}, "comparison")
        require(row["metric"] not in seen, "duplicate metric")
        seen.add(row["metric"])
        for key in ("left", "right"):
            number(row[key], -1e300, 1e300, key)
        number(row["scale_floor"], 0, 1, "normalization floor")
        require(row["metric"] in OBLIGATIONS[name] and row["criterion"] == OBLIGATIONS[name][row["metric"]]
                and row["tolerance"] == CRITERIA[row["criterion"]], "unregistered tolerance or metric")
        require(row["scale_floor"] == (0 if row["criterion"] == "cumulative_rtol" else 1), "wrong normalization floor")
        if name not in {"restart_tstar_1", "restart_tstar_2", "cumulative_same_step"}:
            require(row["right"] == 0 and row["left"] >= 0, "bound metric must be a nonnegative measured violation/drift")
        denominator = max(row["scale_floor"], abs(row["left"]), abs(row["right"]))
        error = abs(row["left"] - row["right"])
        passed = (math.isclose(row["left"], row["right"], rel_tol=5e-8, abs_tol=1e-12)
                  if row["criterion"] == "cumulative_rtol" else
                  (error == 0 if denominator == 0 else error / denominator <= row["tolerance"]))
        require(passed, "measured qualification FAIL: " + row["metric"])
    require(seen == set(OBLIGATIONS[name]), "missing required measured qualification metrics")
    if name == "launch_gate_regression":
        require(seen == {"failed_test_count"} and check["comparisons"][0]["left"] == 0
                and check["comparisons"][0]["criterion"] == "exact_count", "gate regression not passing")


def validate(record_path, contract, now=None):
    a = load(record_path)
    exact(a, {"schema", "mode", "purpose", "binding", "material_sha256", "material_files", "source_root", "source_commit",
              "expires_utc", "maximum_starts", "maximum_t_star", "maximum_wall_seconds", "plan_end_time", "plan_t_star",
              "checks", "synthetic_root"}, "qualification authority")
    require(a["schema"] == SCHEMA, "unsupported authority schema")
    require(a["binding"] == binding(contract), "stale/wrong launch binding")
    integer(a["maximum_starts"], 1, 48, "maximum starts")
    number(a["maximum_wall_seconds"], 0.001, 28800, "wall cap")
    number(a["plan_end_time"], 0, 1e3, "end time")
    number(a["plan_t_star"], 0, 4, "plan t_star")
    require(float(option(contract["solver_argv"], "--end-time")) == a["plan_end_time"], "wrong end time")
    require(abs(a["plan_end_time"] / DH - a["plan_t_star"]) <= 1e-12, "t_star does not match physical horizon")
    require(float(option(contract["supervisor_argv"], "--timeout-seconds")) <= a["maximum_wall_seconds"], "wall budget exceeded")
    expiry = dt.datetime.fromisoformat(a["expires_utc"])
    require(expiry.tzinfo is not None and (now or dt.datetime.now(dt.timezone.utc)) < expiry, "stale authority")
    require(a["material_files"] and fingerprint(a["material_files"]) == a["material_sha256"], "material manifest corrupted")
    for r in a["material_files"]:
        verify_file(r)
    root = Path(a["source_root"])
    require(root.is_dir() and not root.is_symlink(), "wrong source root")
    require(a["source_commit"] == contract["scientific_source_commit"], "wrong source commit")
    head = subprocess.check_output(["git", "--no-optional-locks", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(head == a["source_commit"], "source HEAD changed")
    bundle = load(contract["source_bundle_manifest"]["path"])
    require(bundle.get("scientific_commit") == head, "source bundle commit mismatch")
    required = {r["path"] for r in contract["verified_inputs"]}
    required.update(str(root / rel) for rel in GATE_FILES)
    for rel in GATE_FILES:
        require(digest(root / rel) == digest(Path(__file__).parent / Path(rel).name), "running gate/launcher dependency differs from certificate source")
    for r in bundle["tracked_behavior_files"]:
        rel = Path(r["path"])
        require(not rel.is_absolute() and ".." not in rel.parts, "invalid source-bundle path")
        p = root / rel
        require(digest(p) == r["sha256"], "source dependency changed")
        required.add(str(p))
    for key, value in bundle["basilisk"].items():
        if key.endswith("_path"):
            require(digest(value) == bundle["basilisk"][key[:-5] + "_sha256"], "toolchain changed")
            required.add(value)
    prepared = bundle["prepared_centered"]
    require(digest(prepared["path"]) == prepared["sha256"], "prepared solver dependency changed")
    required.add(prepared["path"])
    actual = [r["path"] for r in a["material_files"]]
    require(len(actual) == len(set(actual)) and required <= set(actual), "incomplete material dependency closure")
    for r in a["material_files"]:
        p = Path(r["path"])
        if p.is_relative_to(root):
            rel = p.relative_to(root).as_posix()
            entry = subprocess.check_output(["git", "ls-tree", "HEAD", "--", rel], cwd=root, text=True).split()
            require(len(entry) >= 4 and entry[0] in {"100644", "100755"} and entry[1] == "blob", "uncommitted/nonregular material")
            blob = subprocess.check_output(["git", "show", head + ":" + rel], cwd=root)
            require(hashlib.sha256(blob).hexdigest() == r["sha256"], "material worktree differs from commit")
    if a["synthetic_root"] is not None:
        s = Path(a["synthetic_root"])
        require(s.name.startswith("SYNTHETIC-") and root.is_relative_to(s) and Path(contract["cwd"]).is_relative_to(s), "synthetic context escaped")
        require(all(Path(r["path"]).is_relative_to(s) for r in a["material_files"]), "synthetic material escaped")
    if a["mode"] == "diagnostic":
        require(a["purpose"] in PURPOSES and set(a["checks"]) == {"launch_gate_regression"}, "invalid diagnostic purpose or missing gate tests")
        verify_check(a["checks"]["launch_gate_regression"], "launch_gate_regression", a["material_sha256"])
        number(a["maximum_t_star"], 0, 2.2, "diagnostic horizon")
    elif a["mode"] == "production":
        require(option(contract["solver_argv"], "--maxlevel") == "8", "production physical resolution mismatch")
        require(a["purpose"] == "matched_ab_confirmation" and set(a["checks"]) == CHECKS, "production missing qualification")
        number(a["maximum_t_star"], 0, 4, "production horizon")
        for name, r in a["checks"].items():
            verify_check(r, name, a["material_sha256"])
    else:
        raise ValueError("unsupported launch mode")
    present = [x for x in DIAGNOSTIC_IDENTITY_OPTIONS if x in contract["solver_argv"]]
    if a['mode']=='production' and not present and contract.get('restore',{}).get('kind')=='checkpoint':
        fields=historical_metadata(contract)
        state=checkpoint_state_from_fields(fields)
        require(state['source_commit']==contract['scientific_source_commit'] and
                state['solver_sha256']==contract['solver']['sha256'] and
                state['execution_id']==contract['execution_id'] and
                state['case_role']==contract['case_role'],
                'production accepted-step checkpoint identity mismatch')
    if present or "diagnostic_restore" in contract:
        require(a["mode"] == "diagnostic" and len(present) == len(DIAGNOSTIC_IDENTITY_OPTIONS), "historical restore forbidden for production or incomplete")
        fields = historical_metadata(contract)
        for flag, key in DIAGNOSTIC_IDENTITY_OPTIONS.items():
            require(option(contract["solver_argv"], flag) == fields[key], "diagnostic identity differs from pinned metadata")
        expected = {"classification": "historical_checkpoint_new_diagnostic_binary_not_production_qualification",
                    "metadata": file_record(contract["restore"]["metadata"]["path"]),
                    "predecessor_identity": {key: fields[key] for key in DIAGNOSTIC_IDENTITY_OPTIONS.values()}}
        require(contract.get("diagnostic_restore") == expected, "missing diagnostic provenance")
    require(a["plan_t_star"] <= a["maximum_t_star"], "over-horizon launch")
    return a


@contextlib.contextmanager
def reserve(record_path, contract, ledger_path, ticket_path):
    """Hold one writer lock through the actual supervised child lifetime.

    Starts are consumed before spawn, including failed/unobservable starts.
    A record may not be replayed by changing its ledger or ticket destination.
    """
    root = Path(contract["batch_identity"]["batch_root"])
    ledger_path, ticket_path = Path(ledger_path), Path(ticket_path)
    require(ledger_path == root / "qualification-start-ledger.json", "noncanonical start ledger")
    require(ticket_path == Path(contract["cwd"]) / ("qualification-ticket." + contract["segment_id"] + ".json"), "noncanonical ticket")
    require(not ticket_path.exists() and not ticket_path.is_symlink(), "duplicate ticket")
    require(not ledger_path.is_symlink(), "symlink ledger")
    lockpath = root / "qualification-gate.lock"
    require(not lockpath.is_symlink(), "symlink gate lock")
    with lockpath.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        a = validate(record_path, contract)
        key = digest(record_path)
        ledger = load(ledger_path) if ledger_path.exists() else {"schema": "nozzle_gate_start_ledger_v1", "starts": []}
        exact(ledger, {"schema", "starts"}, "start ledger")
        require(ledger["schema"] == "nozzle_gate_start_ledger_v1" and isinstance(ledger["starts"], list), "corrupt start ledger")
        require(len(ledger["starts"]) < 48, "global process-start budget exhausted")
        for row in ledger["starts"]:
            exact(row, {"record_sha256", "segment_id", "ticket_path", "full_target_resolution"}, "prior start")
            require(type(row["full_target_resolution"]) is bool, "corrupt resolution counter")
            require(isinstance(row["record_sha256"], str) and re.fullmatch("[0-9a-f]{64}", row["record_sha256"]), "corrupt record identity")
            require(isinstance(row["segment_id"], str) and re.fullmatch("[A-Za-z0-9][A-Za-z0-9._-]{0,127}", row["segment_id"]), "corrupt segment identity")
            prior_ticket = Path(row["ticket_path"])
            require(prior_ticket.is_relative_to(root) and ".." not in prior_ticket.parts, "corrupt prior ticket path")
            require(row["segment_id"] != contract["segment_id"], "segment already consumed")
        require(len({r["segment_id"] for r in ledger["starts"]}) == len(ledger["starts"]), "duplicate historical segments")
        full = option(contract["solver_argv"], "--maxlevel") == "8"
        require(not full or sum(r["full_target_resolution"] for r in ledger["starts"]) < 12, "full-resolution process budget exhausted")
        require(sum(row["record_sha256"] == key for row in ledger["starts"]) < a["maximum_starts"], "permit start budget exhausted")
        ticket = {"schema": "nozzle_gate_ticket_v1", "run_id": str(uuid.uuid4()), "parent_pid": os.getpid(),
                  "record": file_record(record_path), "contract": contract, "state": "reserved"}
        # Rehash immediately before writing the reservation; the supervisor
        # performs the same validation again immediately before Popen.
        require(validate(record_path, contract) == a, "identity changed before reservation")
        ledger["starts"].append({"record_sha256": key, "segment_id": contract["segment_id"], "ticket_path": str(ticket_path), "full_target_resolution": full})
        atomic(ledger_path, ledger); atomic(ticket_path, ticket)
        try:
            yield ticket_path
        finally:
            ticket["state"] = "consumed"; atomic(ticket_path, ticket)


def supervisor_gate(ticket_path, argv, cwd):
    require(ticket_path is not None, "direct successor supervisor entry forbidden without reserved qualification")
    t = load(ticket_path)
    exact(t, {"schema", "run_id", "parent_pid", "record", "contract", "state"}, "qualification ticket")
    require(t["schema"] == "nozzle_gate_ticket_v1" and t["state"] == "reserved" and
            type(t["parent_pid"]) is int and t["parent_pid"] == os.getppid(), "ticket parent/state mismatch")
    c = t["contract"]
    require(c["solver_argv"] == argv and c["cwd"] == str(cwd), "ticket command/cwd mismatch")
    record = verify_file(t["record"])
    validate(record, c)


def scoped(cwd):
    return BATCH in Path(cwd).parts
