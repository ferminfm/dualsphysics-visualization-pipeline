#!/usr/bin/env python3
"""Seal committed internal-nozzle source and one observable qcc build."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path


SOURCE_PATHS = (
    "cases/basilisk/rectangular_internal_nozzle_steady_precursor.c",
    "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c",
    "cases/basilisk/internal_nozzle_precursor_geometry.h",
    "cases/basilisk/internal_nozzle_precursor_start.h",
    "cases/basilisk/internal_nozzle_checkpoint_v4.h",
    "cases/basilisk/internal_nozzle_nonmutation_probe.h",
    "cases/basilisk/internal_nozzle_restartable_timestep.h",
    "cases/basilisk/internal_nozzle_projection_trace.h",
    "cases/basilisk/internal_nozzle_viscosity_embed_trace.h",
    "cases/basilisk/internal_nozzle_poisson_trace.h",
    "scripts/prepare_internal_nozzle_centered.py",
    "scripts/rectangular_poiseuille_reference.py",
    "scripts/evaluate_internal_nozzle_acceptance.py",
)
BUILD_ROLES = {
    "precursor": {
        "entry_source": "cases/basilisk/rectangular_internal_nozzle_steady_precursor.c",
        "required_defines": ("INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1",),
        "forbidden_defines": ("INTERNAL_NOZZLE_PROFILE_CONTROLLED",),
    },
    "pressure_driven": {
        "entry_source": "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c",
        "required_defines": ("INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1",),
        "forbidden_defines": ("INTERNAL_NOZZLE_PROFILE_CONTROLLED",),
    },
    "profile_controlled": {
        "entry_source": "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c",
        "required_defines": (
            "INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP=1",
            "INTERNAL_NOZZLE_PROFILE_CONTROLLED=1",
        ),
        "forbidden_defines": (),
    },
}
EXPECTED_TIMESTEP_SHA256 = "7a728bfe633cac8e6682fd8288ec6296a18d1486fb3c5b4b4019d227fb3947b4"
ORIGINAL_INCLUDE = '#include "timestep.h"'
REPLACEMENT_INCLUDE = '#include "internal_nozzle_restartable_timestep.h"'
ORIGINAL_EMBED = '# include "viscosity-embed.h"'
REPLACEMENT_EMBED = '# include "internal_nozzle_viscosity_embed_trace.h"'
ORIGINAL_PREDICTION = """  if (!stokes) {
    prediction();
"""
REPLACEMENT_PREDICTION = """  if (!stokes) {
#if INTERNAL_NOZZLE_PROJECTION_TRACE
    internal_nozzle_prediction_trace_stage
      ("before_prediction", uf, alpha);
#endif
    prediction();
#if INTERNAL_NOZZLE_PROJECTION_TRACE
    internal_nozzle_prediction_trace_stage
      ("after_prediction_pre_projection", uf, alpha);
#endif
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, context: str) -> dict[str, object]:
    def reject_nonfinite(value: str) -> object:
        raise ValueError(f"nonfinite JSON constant: {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
            parse_constant=reject_nonfinite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{context}: invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{context}: JSON root must be an object")
    return value


def exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{context}: key set mismatch")


def canonical_hash(value: object, length: int, context: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"{context}: expected {length} lowercase hex digits")
    return value


def validate_source_bundle(bundle: dict[str, object]) -> None:
    exact_keys(bundle, {
        "schema", "scientific_commit", "repository_root_name",
        "tracked_behavior_files", "tracked_behavior_file_count",
        "prepared_centered", "basilisk", "source_identity_semantics",
    }, "source bundle")
    if (bundle.get("schema") != "internal_nozzle_source_bundle_v1" or
            bundle.get("source_identity_semantics") !=
            "sha256_of_this_complete_manifest_file"):
        raise ValueError("unsupported source-bundle schema/semantics")
    canonical_hash(bundle.get("scientific_commit"), 40, "source bundle commit")
    if not isinstance(bundle.get("repository_root_name"), str) or not bundle["repository_root_name"]:
        raise ValueError("source bundle repository name is invalid")
    rows = bundle.get("tracked_behavior_files")
    if (not isinstance(rows, list) or not rows or
            bundle.get("tracked_behavior_file_count") != len(rows)):
        raise ValueError("source bundle tracked-file inventory is malformed")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("source bundle tracked-file record is malformed")
        exact_keys(row, {"path", "git_blob", "git_mode", "size_bytes", "sha256"},
                   "source bundle tracked file")
        path = row.get("path")
        if (not isinstance(path, str) or not path or Path(path).is_absolute() or
                Path(path).as_posix() != path or ".." in Path(path).parts or path in seen):
            raise ValueError("source bundle tracked path is invalid")
        seen.add(path)
        canonical_hash(row.get("git_blob"), 40, "source bundle Git blob")
        canonical_hash(row.get("sha256"), 64, "source bundle file SHA-256")
        if row.get("git_mode") not in {"100644", "100755"}:
            raise ValueError("source bundle tracked mode is invalid")
        if (isinstance(row.get("size_bytes"), bool) or
                not isinstance(row.get("size_bytes"), int) or row["size_bytes"] <= 0):
            raise ValueError("source bundle tracked size is invalid")
    if seen != set(SOURCE_PATHS):
        raise ValueError("source bundle does not contain the exact behavior-file set")
    prepared = bundle.get("prepared_centered")
    basilisk = bundle.get("basilisk")
    if not isinstance(prepared, dict) or not isinstance(basilisk, dict):
        raise ValueError("source bundle external-input records are malformed")
    exact_keys(prepared, {"path", "size_bytes", "sha256", "derivation"},
               "prepared centered")
    exact_keys(basilisk, {
        "basilisk_timestep_path", "basilisk_timestep_sha256",
        "basilisk_centered_path", "basilisk_centered_sha256",
        "qcc_path", "qcc_sha256",
    }, "Basilisk identity")
    if prepared.get("derivation") != "exact_hash_gated_transform":
        raise ValueError("prepared centered derivation is invalid")
    canonical_hash(prepared.get("sha256"), 64, "prepared centered SHA-256")
    if (isinstance(prepared.get("size_bytes"), bool) or
            not isinstance(prepared.get("size_bytes"), int) or prepared["size_bytes"] <= 0):
        raise ValueError("prepared centered size is invalid")
    for field in ("basilisk_timestep_sha256", "basilisk_centered_sha256", "qcc_sha256"):
        canonical_hash(basilisk.get(field), 64, f"Basilisk {field}")


def compiler_defines(argv: list[str]) -> list[str]:
    values: list[str] = []
    for token in argv:
        if token.startswith("-D") and len(token) > 2:
            values.append(token[2:])
    if len(values) != len(set(values)):
        raise ValueError("qcc argv repeats a preprocessor definition")
    return values


def regular(path: Path, context: str, *, executable: bool = False) -> Path:
    if path.is_symlink():
        raise ValueError(f"{context}: symlink forbidden")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{context}: missing path") from error
    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode) or resolved.stat().st_size <= 0:
        raise ValueError(f"{context}: nonempty regular file required")
    if executable and not os.access(resolved, os.X_OK):
        raise ValueError(f"{context}: executable file required")
    return resolved


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise ValueError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"temporary output already exists: {temporary}")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepared_centered_bytes(basilisk_src: Path) -> tuple[bytes, dict[str, object]]:
    timestep = regular(basilisk_src / "timestep.h", "Basilisk timestep.h")
    centered = regular(basilisk_src / "navier-stokes" / "centered.h", "Basilisk centered.h")
    timestep_sha = sha256_file(timestep)
    if timestep_sha != EXPECTED_TIMESTEP_SHA256:
        raise ValueError("Basilisk timestep.h identity is not the authorized restartable base")
    content = centered.read_text(encoding="utf-8")
    substitutions = (
        (ORIGINAL_INCLUDE, REPLACEMENT_INCLUDE, "timestep include"),
        (ORIGINAL_EMBED, REPLACEMENT_EMBED, "embedded-viscosity include"),
        (ORIGINAL_PREDICTION, REPLACEMENT_PREDICTION, "prediction trace"),
    )
    for old, new, label in substitutions:
        if content.count(old) != 1:
            raise ValueError(f"ambiguous Basilisk centered.h {label} substitution")
        content = content.replace(old, new, 1)
    return content.encode("utf-8"), {
        "basilisk_timestep_path": str(timestep),
        "basilisk_timestep_sha256": timestep_sha,
        "basilisk_centered_path": str(centered),
        "basilisk_centered_sha256": sha256_file(centered),
    }


def seal_source(
    repo_root: Path, expected_commit: str, basilisk_src: Path,
    qcc_path: Path, prepared_centered: Path,
) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("expected commit must be 40 lowercase hex digits")
    root = Path(git(repo_root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if root != repo_root.resolve(strict=True):
        raise ValueError("repo-root must be the exact Git worktree root")
    if git(root, "rev-parse", "HEAD") != expected_commit:
        raise ValueError("scientific HEAD does not match expected commit")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("scientific worktree must be clean before source sealing")
    records: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        candidate = root / relative
        resolved = regular(candidate, f"tracked source {relative}")
        listing = git(root, "ls-tree", expected_commit, "--", relative).split()
        if len(listing) != 4 or listing[1] != "blob" or listing[3] != relative:
            raise ValueError(f"tracked source is not one regular Git blob: {relative}")
        mode, _, blob, _ = listing
        if mode not in {"100644", "100755"}:
            raise ValueError(f"tracked source has inadmissible mode: {relative}")
        object_bytes = subprocess.run(
            ["git", "cat-file", "blob", blob], cwd=root, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        current_bytes = resolved.read_bytes()
        if object_bytes != current_bytes:
            raise ValueError(f"tracked source bytes differ from HEAD: {relative}")
        records.append({
            "path": relative, "git_blob": blob, "git_mode": mode,
            "size_bytes": len(current_bytes),
            "sha256": hashlib.sha256(current_bytes).hexdigest(),
        })
    expected_prepared, external = prepared_centered_bytes(basilisk_src.resolve(strict=True))
    prepared = regular(prepared_centered, "prepared centered header")
    if prepared.read_bytes() != expected_prepared:
        raise ValueError("prepared centered header is not the exact authorized transform")
    qcc = regular(qcc_path, "qcc", executable=True)
    return {
        "schema": "internal_nozzle_source_bundle_v1",
        "scientific_commit": expected_commit,
        "repository_root_name": root.name,
        "tracked_behavior_files": records,
        "tracked_behavior_file_count": len(records),
        "prepared_centered": {
            "path": str(prepared), "size_bytes": prepared.stat().st_size,
            "sha256": sha256_file(prepared), "derivation": "exact_hash_gated_transform",
        },
        "basilisk": {
            **external, "qcc_path": str(qcc), "qcc_sha256": sha256_file(qcc),
        },
        "source_identity_semantics": "sha256_of_this_complete_manifest_file",
    }


def verified_inputs(terminal: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = terminal.get("verified_inputs")
    if not isinstance(rows, list):
        raise ValueError("terminal verified_inputs must be a list")
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("resolved_path"), str):
            raise ValueError("malformed terminal input record")
        path = str(Path(str(row["resolved_path"])).resolve(strict=True))
        if path in result:
            raise ValueError("duplicate terminal input record")
        result[path] = row
    return result


def seal_build(
    source_bundle: Path, source_bundle_sha256: str, evidence_dir: Path,
    binary_path: Path, build_role: str,
) -> dict[str, object]:
    bundle_path = regular(source_bundle, "source bundle")
    if sha256_file(bundle_path) != source_bundle_sha256:
        raise ValueError("source-bundle SHA-256 mismatch")
    bundle = load_json(bundle_path, "source bundle")
    validate_source_bundle(bundle)
    if build_role not in BUILD_ROLES:
        raise ValueError("unsupported build role")
    evidence = evidence_dir.resolve(strict=True)
    launch_path = regular(evidence / "launch.json", "qcc launch record")
    terminal_path = regular(evidence / "terminal.json", "qcc terminal record")
    launch = load_json(launch_path, "qcc launch record")
    terminal = load_json(terminal_path, "qcc terminal record")
    for key in ("run_id", "cwd", "argv", "child_pid", "source_commit", "source_sha256"):
        if launch.get(key) != terminal.get(key):
            raise ValueError(f"qcc launch/terminal {key} mismatch")
    if (terminal.get("exit_code") != 0 or terminal.get("terminal_state") != "normal_exit" or
            terminal.get("input_identity_changed") is not False or
            terminal.get("child_exists_after_wait") is not False):
        raise ValueError("qcc terminal record is not an observable successful compile")
    if (terminal.get("source_commit") != bundle.get("scientific_commit") or
            terminal.get("source_sha256") != source_bundle_sha256):
        raise ValueError("qcc terminal source identity mismatch")
    binary = regular(binary_path, "compiled solver", executable=True)
    argv = terminal.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(value, str) for value in argv):
        raise ValueError("qcc argv is invalid")
    qcc_path = str(Path(str(bundle["basilisk"]["qcc_path"])).resolve(strict=True))
    if str(Path(argv[0]).resolve(strict=True)) != qcc_path:
        raise ValueError("qcc executable does not match source bundle")
    if "-o" not in argv or argv.index("-o") + 1 >= len(argv):
        raise ValueError("qcc argv has no output binding")
    if Path(argv[argv.index("-o") + 1]).resolve(strict=True) != binary:
        raise ValueError("compiled binary is not the qcc-declared output")
    role = BUILD_ROLES[build_role]
    cwd = Path(str(terminal.get("cwd"))).resolve(strict=True)
    entry = (cwd / str(role["entry_source"])).resolve(strict=True)
    source_tokens = [
        token for token in argv[1:]
        if not token.startswith("-") and Path(token).suffix == ".c"
    ]
    if (len(source_tokens) != 1 or
            (Path(source_tokens[0]) if Path(source_tokens[0]).is_absolute()
             else cwd / source_tokens[0]).resolve(strict=True) != entry):
        raise ValueError("qcc argv does not compile the exact build-role entry source")
    defines = compiler_defines(argv)
    for required in role["required_defines"]:
        if required not in defines:
            raise ValueError(f"qcc argv lacks required build-role define: {required}")
    for forbidden in role["forbidden_defines"]:
        if any(value == forbidden or value.startswith(forbidden + "=") for value in defines):
            raise ValueError(f"qcc argv contains forbidden build-role define: {forbidden}")
    expected: dict[str, str] = {
        str(bundle_path): source_bundle_sha256,
        qcc_path: str(bundle["basilisk"]["qcc_sha256"]),
        str(Path(str(bundle["prepared_centered"]["path"])).resolve(strict=True)):
            str(bundle["prepared_centered"]["sha256"]),
    }
    files = bundle.get("tracked_behavior_files")
    if not isinstance(files, list) or len(files) != bundle.get("tracked_behavior_file_count"):
        raise ValueError("source bundle tracked-file inventory is malformed")
    for record in files:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError("source bundle has malformed tracked-file record")
        expected[str((cwd / str(record["path"])).resolve(strict=True))] = str(record.get("sha256"))
    observed = verified_inputs(terminal)
    if set(observed) != set(expected):
        raise ValueError("qcc terminal did not verify the complete source-input set")
    for path, digest in expected.items():
        row = observed[path]
        if (row.get("expected_sha256") != digest or row.get("observed_sha256") != digest or
                row.get("observed_sha256_after") != digest or row.get("verified") is not True or
                row.get("unchanged_during_run") is not True):
            raise ValueError(f"qcc source input was not immutably verified: {path}")
    return {
        "schema": "internal_nozzle_observable_qcc_build_v1",
        "scientific_commit": bundle["scientific_commit"],
        "source_bundle_path": str(bundle_path),
        "source_bundle_sha256": source_bundle_sha256,
        "build_role": build_role,
        "entry_source": str(role["entry_source"]),
        "required_defines": list(role["required_defines"]),
        "compile_identity_semantics":
            "observable_qcc_exact_entry_source_role_defines_and_immutable_inputs",
        "compile_run_id": terminal["run_id"],
        "compile_argv": argv,
        "compile_terminal": {
            "path": str(terminal_path), "sha256": sha256_file(terminal_path),
            "exit_code": 0, "terminal_state": "normal_exit",
        },
        "binary": {
            "path": str(binary), "size_bytes": binary.stat().st_size,
            "sha256": sha256_file(binary),
        },
        "verified_input_count": len(expected),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    source = subparsers.add_parser("source")
    source.add_argument("--repo-root", type=Path, required=True)
    source.add_argument("--expected-commit", required=True)
    source.add_argument("--basilisk-src", type=Path, required=True)
    source.add_argument("--qcc", type=Path, required=True)
    source.add_argument("--prepared-centered", type=Path, required=True)
    source.add_argument("--output", type=Path, required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--source-bundle", type=Path, required=True)
    build.add_argument("--source-bundle-sha256", required=True)
    build.add_argument("--evidence-dir", type=Path, required=True)
    build.add_argument("--binary", type=Path, required=True)
    build.add_argument("--build-role", choices=tuple(BUILD_ROLES), required=True)
    build.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "source":
        payload = seal_source(
            args.repo_root, args.expected_commit, args.basilisk_src,
            args.qcc, args.prepared_centered,
        )
    else:
        if not re.fullmatch(r"[0-9a-f]{64}", args.source_bundle_sha256):
            parser.error("source-bundle-sha256 must be 64 lowercase hex digits")
        payload = seal_build(
            args.source_bundle, args.source_bundle_sha256, args.evidence_dir, args.binary,
            args.build_role,
        )
    atomic_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
