#!/usr/bin/env python3
"""Prepare a hash-gated centered solver header with restartable timestep state."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


EXPECTED_TIMESTEP_SHA256 = (
    "7a728bfe633cac8e6682fd8288ec6296a18d1486fb3c5b4b4019d227fb3947b4"
)
ORIGINAL_INCLUDE = '#include "timestep.h"'
REPLACEMENT_INCLUDE = '#include "internal_nozzle_restartable_timestep.h"'
ORIGINAL_EMBED_VISCOSITY_INCLUDE = '# include "viscosity-embed.h"'
TRACE_EMBED_VISCOSITY_INCLUDE = '# include "internal_nozzle_viscosity_embed_trace.h"'
ORIGINAL_PREDICTION_BLOCK = """  if (!stokes) {
    prediction();
"""
TRACE_PREDICTION_BLOCK = """  if (!stokes) {
#if INTERNAL_NOZZLE_PROJECTION_TRACE
    internal_nozzle_prediction_trace_stage
      (\"before_prediction\", uf, alpha);
#endif
    prediction();
#if INTERNAL_NOZZLE_PROJECTION_TRACE
    internal_nozzle_prediction_trace_stage
      (\"after_prediction_pre_projection\", uf, alpha);
#endif
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basilisk-src", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    timestep = args.basilisk_src / "timestep.h"
    centered = args.basilisk_src / "navier-stokes" / "centered.h"
    observed = sha256(timestep)
    if observed != EXPECTED_TIMESTEP_SHA256:
        raise SystemExit(
            "refusing solver-header substitution: upstream timestep.h SHA-256 "
            f"is {observed}, expected {EXPECTED_TIMESTEP_SHA256}"
        )

    content = centered.read_text(encoding="utf-8")
    if content.count(ORIGINAL_INCLUDE) != 1:
        raise SystemExit("refusing ambiguous centered.h timestep include replacement")
    prepared = content.replace(ORIGINAL_INCLUDE, REPLACEMENT_INCLUDE, 1)
    if prepared.count(ORIGINAL_EMBED_VISCOSITY_INCLUDE) != 1:
        raise SystemExit("refusing ambiguous centered.h embedded-viscosity include replacement")
    prepared = prepared.replace(
        ORIGINAL_EMBED_VISCOSITY_INCLUDE, TRACE_EMBED_VISCOSITY_INCLUDE, 1
    )
    if prepared.count(ORIGINAL_PREDICTION_BLOCK) != 1:
        raise SystemExit("refusing ambiguous centered.h prediction-trace insertion")
    prepared = prepared.replace(
        ORIGINAL_PREDICTION_BLOCK, TRACE_PREDICTION_BLOCK, 1
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(prepared, encoding="utf-8")
    print(f"prepared={args.output}")
    print(f"upstream_timestep_sha256={observed}")
    print(f"prepared_centered_sha256={sha256(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
