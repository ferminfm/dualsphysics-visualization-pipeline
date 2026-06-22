#!/usr/bin/env python3
"""Parse Basilisk output_facets files and optionally write simple OBJ surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_facets(path: Path) -> tuple[list[list[tuple[float, float, float]]], dict[str, str]]:
    facets: list[list[tuple[float, float, float]]] = []
    current: list[tuple[float, float, float]] = []
    metadata: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            if current:
                facets.append(current)
                current = []
            continue
        if line.startswith("#"):
            payload = line[1:].strip()
            if "=" in payload:
                key, value = payload.split("=", 1)
                metadata[key.strip()] = value.strip()
            continue
        parts = line.split()
        if len(parts) != 3:
            raise ValueError(f"{path}: expected 3 coordinates, got {line!r}")
        current.append(tuple(float(part) for part in parts))
    if current:
        facets.append(current)
    return facets, metadata


def write_obj(path: Path, facets: list[list[tuple[float, float, float]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Generated from Basilisk output_facets; topology cleanup operations: none\n")
        vertex_index = 1
        for facet in facets:
            for vertex in facet:
                handle.write(f"v {vertex[0]:.12g} {vertex[1]:.12g} {vertex[2]:.12g}\n")
            if len(facet) >= 3:
                face = " ".join(str(i) for i in range(vertex_index, vertex_index + len(facet)))
                handle.write(f"f {face}\n")
            vertex_index += len(facet)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True, help="Facet file to parse.")
    parser.add_argument("--obj-dir", type=Path, help="Optional directory for OBJ exports.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--min-facets", type=int, default=1)
    args = parser.parse_args()

    records = []
    total_facets = 0
    total_vertices = 0
    for path in sorted(args.input):
        facets, metadata = parse_facets(path)
        vertex_count = sum(len(facet) for facet in facets)
        total_facets += len(facets)
        total_vertices += vertex_count
        obj_path = None
        if args.obj_dir:
            obj_path = args.obj_dir / f"{path.stem}.obj"
            write_obj(obj_path, facets)
        records.append(
            {
                "input": str(path),
                "facet_count": len(facets),
                "vertex_count": vertex_count,
                "metadata": metadata,
                "obj_path": str(obj_path) if obj_path else "",
                "nonzero_geometry": len(facets) >= args.min_facets and vertex_count > 0,
            }
        )

    result = {
        "surface_export_ready": total_facets >= args.min_facets and total_vertices > 0,
        "total_facets": total_facets,
        "total_vertices": total_vertices,
        "records": records,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SURFACE_PARSE_MANIFEST={args.manifest}")
    return 0 if result["surface_export_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
