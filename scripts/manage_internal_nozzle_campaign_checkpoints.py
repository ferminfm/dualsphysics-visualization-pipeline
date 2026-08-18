#!/usr/bin/env python3
"""Promote and select two rolling native internal-nozzle checkpoint generations.

The native Basilisk dump and its existing metadata remain the only mesh/field
checkpoint representation.  This utility only copies completed generations,
records their external integrity metadata, and selects the newest valid member
without ever parsing a dump or prediction-closure payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


MEMBER_SUFFIXES = ("", ".meta", ".prediction-closure-v4")
STATE_NAME = "campaign-state.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_member(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
        raise ValueError(f"checkpoint member is not a nonempty regular file: {path}")
    return {"name": path.name, "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def validate_generation(root: Path, generation: dict[str, object]) -> bool:
    directory = root / str(generation["directory"])
    try:
        members = generation["members"]
        if not isinstance(members, list) or len(members) != len(MEMBER_SUFFIXES):
            return False
        for member in members:
            if not isinstance(member, dict):
                return False
            path = directory / str(member["name"])
            if describe_member(path) != member:
                return False
    except (KeyError, OSError, ValueError):
        return False
    return True


def load_state(root: Path) -> dict[str, object]:
    path = root / STATE_NAME
    if not path.is_file():
        return {"schema": "internal_nozzle_campaign_state_v1", "generations": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != "internal_nozzle_campaign_state_v1":
        raise ValueError("unknown campaign state schema")
    if not isinstance(state.get("generations"), list):
        raise ValueError("campaign state generations must be a list")
    return state


def write_state(root: Path, state: dict[str, object]) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix="campaign-state-", suffix=".tmp", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / STATE_NAME)
    finally:
        if temporary.exists():
            temporary.unlink()


def select(root: Path, state: dict[str, object]) -> dict[str, object]:
    candidates = list(reversed(state["generations"]))
    for generation in candidates:
        if validate_generation(root, generation):
            return generation
    raise ValueError("no validated checkpoint generation is available")


def reconcile_state(root: Path, state: dict[str, object]) -> dict[str, object]:
    """Drop invalid inactive generations and persist the selected LKG lineage."""
    valid = [item for item in state["generations"] if validate_generation(root, item)]
    if not valid:
        raise ValueError("no validated checkpoint generation is available")
    reconciled = {
        "schema": "internal_nozzle_campaign_state_v1",
        "updated_at_utc": now(),
        "newest_generation": valid[-1]["generation"],
        "previous_generation": valid[-2]["generation"] if len(valid) > 1 else None,
        "generations": valid[-2:],
        "next_generation": max(int(item["generation"]) for item in valid) + 1,
    }
    if reconciled != state:
        write_state(root, reconciled)
    return reconciled


def promote(args: argparse.Namespace) -> int:
    root = args.campaign_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = args.checkpoint.resolve()
    sources = [Path(str(checkpoint) + suffix) for suffix in MEMBER_SUFFIXES]
    source_members = [describe_member(path) for path in sources]
    state = load_state(root)
    previous = select(root, state) if state["generations"] else None
    number = int(state.get("next_generation", 1))
    directory_name = f"generation-{number:04d}"
    destination = root / directory_name
    if destination.exists():
        raise ValueError(f"generation destination already exists: {destination}")
    staging = Path(tempfile.mkdtemp(prefix=f".{directory_name}-", dir=root))
    try:
        for source in sources:
            shutil.copy2(source, staging / source.name)
        generation = {
            "generation": number,
            "directory": directory_name,
            "checkpoint_basename": checkpoint.name,
            "promoted_at_utc": now(),
            "members": [describe_member(staging / source.name) for source in sources],
        }
        if generation["members"] != source_members or not validate_generation(root, {**generation, "directory": staging.name}):
            raise ValueError("staged checkpoint generation did not validate")
        os.replace(staging, destination)
        generations = [item for item in state["generations"] if validate_generation(root, item)]
        generations.append(generation)
        generations = generations[-2:]
        next_state = {
            "schema": "internal_nozzle_campaign_state_v1",
            "updated_at_utc": now(),
            "newest_generation": generation["generation"],
            "previous_generation": previous["generation"] if previous else None,
            "generations": generations,
            "next_generation": number + 1,
        }
        write_state(root, next_state)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    print(json.dumps({"status": "promoted", "generation": number}, sort_keys=True))
    return 0


def choose(args: argparse.Namespace) -> int:
    root = args.campaign_root.resolve()
    state = reconcile_state(root, load_state(root))
    selected = select(root, state)
    print(json.dumps({"status": "selected", "generation": selected["generation"],
                      "checkpoint": str(root / selected["directory"] / selected["checkpoint_basename"])}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("promote", "select"):
        sub = commands.add_parser(command)
        sub.add_argument("--campaign-root", required=True, type=Path)
        if command == "promote":
            sub.add_argument("--checkpoint", required=True, type=Path)
    args = parser.parse_args()
    return promote(args) if args.command == "promote" else choose(args)


if __name__ == "__main__":
    raise SystemExit(main())
