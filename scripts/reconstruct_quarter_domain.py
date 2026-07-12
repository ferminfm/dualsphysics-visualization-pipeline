#!/usr/bin/env python3
"""Mirror quarter-domain Basilisk facets into a render-only four-quadrant asset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from export_basilisk_vof_surface import parse_facets


LABEL = "RENDER ONLY - ONE SIMULATED QUADRANT MIRRORED; NOT FULL-DOMAIN PHYSICS"
TRANSFORMS = ((1, 1), (-1, 1), (1, -1), (-1, -1))


def transform_facet(
    facet: list[tuple[float, float, float]], sy: int, sz: int
) -> list[tuple[float, float, float]]:
    transformed = [(x, sy * y, sz * z) for x, y, z in facet]
    # One reflection reverses handedness. Reverse winding so transformed face
    # normals follow the reflected physical surface rather than pointing inward.
    if sy * sz < 0:
        transformed.reverse()
    return transformed


def write_facets(
    path: Path,
    facets: list[list[tuple[float, float, float]]],
    source: Path,
) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"# {LABEL}\n")
        handle.write(f"# source={source}\n")
        handle.write("# transforms=(y,z),(−y,z),(y,−z),(−y,−z)\n")
        handle.write("# odd-reflection facet winding reversed=true\n")
        for facet in facets:
            for x, y, z in facet:
                handle.write(f"{x:.12g} {y:.12g} {z:.12g}\n")
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plane-tolerance", type=float, default=1e-10)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    passed = True
    for source in sorted(args.input):
        facets, metadata = parse_facets(source)
        vertices = [vertex for facet in facets for vertex in facet]
        min_y = min((point[1] for point in vertices), default=0.0)
        min_z = min((point[2] for point in vertices), default=0.0)
        source_is_quarter = (
            metadata.get("domain_mode") == "quarter"
            and min_y >= -args.plane_tolerance
            and min_z >= -args.plane_tolerance
        )
        reconstructed: list[list[tuple[float, float, float]]] = []
        transform_records = []
        for sy, sz in TRANSFORMS:
            transformed = [transform_facet(facet, sy, sz) for facet in facets]
            reconstructed.extend(transformed)
            transform_records.append(
                {
                    "y_sign": sy,
                    "z_sign": sz,
                    "determinant": sy * sz,
                    "winding_reversed": sy * sz < 0,
                    "facet_count": len(transformed),
                }
            )
        destination = args.output_dir / f"{source.stem}_render_only_4q.facets"
        write_facets(destination, reconstructed, source)
        record_passed = source_is_quarter and len(reconstructed) == 4 * len(facets)
        passed = passed and record_passed
        records.append(
            {
                "source": str(source),
                "output": str(destination),
                "source_domain_mode": metadata.get("domain_mode"),
                "source_facet_count": len(facets),
                "reconstructed_facet_count": len(reconstructed),
                "source_min_y": min_y,
                "source_min_z": min_z,
                "source_is_nonnegative_quarter": source_is_quarter,
                "orientation_policy": "reverse_winding_for_odd_reflection_parity",
                "transforms": transform_records,
                "passed": record_passed,
            }
        )

    result = {
        "classification": "render_only_quarter_reconstruction",
        "persistent_label": LABEL,
        "simulated_domains": 1,
        "rendered_quadrants": 4,
        "independent_full_domain_physics": False,
        "breakup_evidence_allowed": False,
        "periodic_boundaries_used": False,
        "records": records,
        "passed": passed and bool(records),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"QUARTER_RECONSTRUCTION_MANIFEST={args.manifest}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
