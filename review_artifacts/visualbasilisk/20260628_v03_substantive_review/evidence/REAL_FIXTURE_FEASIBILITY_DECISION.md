# Real Basilisk Fixture Feasibility Decision

Decision: defer real Basilisk-derived fixtures for VisualBasilisk v0.3.

## Search Result

The feasibility pass found local Basilisk facet outputs in stack-validation
solver-output trees, especially long-benchmark `output_facets(f)` files. These
are generated research artifacts and many are too large for a source-first
fixture pack.

No candidate was identified that simultaneously met all requirements:

- tiny enough for source review;
- clear provenance and generation command;
- unambiguous license/citation status;
- safe for GitHub review without exposing local generated output trees;
- approved claim boundary for reusable package tests.

## Rationale

VisualBasilisk v0.3 is a bridge utility. Adding real solver-derived output would
change the package from source/test fixture scope toward data distribution. That
needs a separate human decision.

## Current Policy

Keep v0.3 fixtures synthetic-only. Use real Basilisk outputs only as local
stack-validation evidence until a later fixture-inclusion review approves a tiny
curated excerpt.

## Future Inclusion Gate

A future real fixture should include:

- a tiny one- or two-frame facet excerpt;
- `surface_manifest.json`;
- source case and export command;
- license/citation note;
- SHA256 provenance;
- explicit statement that it is a parser/render fixture, not validation,
  atomisation evidence, fit readiness, or public readiness.
