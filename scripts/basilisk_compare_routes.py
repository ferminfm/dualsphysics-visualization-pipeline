#!/usr/bin/env python3
"""Route-level comparison wrapper for the Basilisk diagnostics harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from basilisk_collect_diagnostics import DEFAULT_ROOTS, collect_roots, summarize_routes, write_route_comparison


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Basilisk routes using the shared diagnostics collector."
    )
    parser.add_argument("roots", nargs="*", help="Basilisk output roots to compare")
    parser.add_argument(
        "--output-md",
        default="",
        help="Optional Markdown output path for the route comparison",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional JSON output path for the route comparison",
    )
    args = parser.parse_args()

    roots = args.roots or list(DEFAULT_ROOTS)
    inventory, cases = collect_roots(roots)
    comparison = summarize_routes(cases, inventory)
    if args.output_md:
        write_route_comparison(Path(args.output_md), comparison)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    if not args.output_md and not args.output_json:
        print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
