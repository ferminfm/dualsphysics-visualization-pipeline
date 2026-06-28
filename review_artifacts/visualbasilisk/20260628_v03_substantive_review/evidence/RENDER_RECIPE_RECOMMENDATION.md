# Render Recipe Recommendation

Default synthetic-fixture smoke recipe:

- camera preset: `orbit`
- material preset: `blue`
- resolution: `640x480`
- frame selection: fixture-dependent, prefer `--frame-range 0:1` when a fixture has two frames

Why this default:

- It keeps geometry visible for the tiny sheet and arc fixtures.
- It works across the synthetic fixture pack without per-fixture tuning.
- It avoids presenting the diagnostic `glass` material as a production-quality water shader.

Diagnostic variants:

- `front/matte` is useful for disconnected components.
- `top/glass` is useful for arc/ribbon shape inspection but can flatten depth cues.

These are software QA choices for a bridge utility, not visual claims about CFD output.
