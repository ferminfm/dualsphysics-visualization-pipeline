# Decision Tree

## If Layer 1 accepts v0.3 as enough for source hardening

Proceed to a small public-release-prep task that checks repository visibility, package metadata, README wording, and whether a PR/release is appropriate.

## If Layer 1 wants more source hardening

Prioritize parser/manifest schema strictness, richer render-plan validation, and more tests before any public-prep task.

## If Layer 1 wants site work

Run a separate non-deployed site route task. Do not deploy or publish until a human publication gate approves it.

## If Layer 1 wants real Basilisk fixtures

Run a dedicated fixture-inclusion review. Do not copy raw stack-validation outputs directly into the repo.
