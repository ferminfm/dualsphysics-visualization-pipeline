# 3D Jet Workflow Feasibility - 2026-06-08

## Purpose

Assess whether the current local DualSPHysics CUDA 12.8 installation can safely
produce a small 3D statistically averaged jet/spray-like particle dataset for
SprayGeo and the Ideal Momentum Jet Explorer.

## Inventory Result

Available validated executable:

```text
DualSPHysics5 v5.4.355
```

Available example XML files in the validated local source tree:

```text
examples/main/01_DamBreak/CaseDambreak_Def.xml
examples/main/01_DamBreak/CaseDambreakVal2D_Def.xml
```

Local documentation mentions full-package inlet/outlet examples such as:

```text
05_SHAPESINLET3D
06_BOX4INLET3D
8_IMPINGINGJET
```

However, the corresponding example XML directories are not present in the
validated local installation.

## Feasibility Decision

Simulation route for this pass: `blocked before heavy execution`.

Reason:

- a 3D continuous inlet/open-boundary jet may be supported by the codebase, but
  the safe working XML examples are absent locally;
- building a stationary 3D inlet case directly from XML-format fragments would
  be new solver setup work, not a smoke-test reuse of a validated example;
- the current validated examples are dam-break cases and would repeat the
  existing video workflow rather than move toward stationary jet geometry;
- no multiphase/liquid-gas atomization executable or complete local example was
  validated in this pass.

No DualSPHysics jet case was run, no heavy data were generated, and no MP4 was
created.

## Current Integration Path

Use this repository as the simulation/video source once a safe 3D jet case is
available. Until then:

```text
DualSPHysics 3D jet case: held
SprayGeo geometry backend: active
Ideal Momentum Jet Explorer import/fitting surface: active
```

The current bridge is:

```text
SprayGeo metrics CSV
        |
        v
Ideal Momentum Jet Explorer overlay CSV: zeta,Ahat,Ahat_error
        |
        v
Existing app overlay import and calibration panel
```

## Next Safe Simulation Step

Obtain or reconstruct a complete local DualSPHysics inlet/outlet example, with
preference for:

1. `05_SHAPESINLET3D`,
2. `8_IMPINGINGJET`,
3. another documented small 3D inlet/outlet case.

Before a longer run:

- generate particles with `GenCase`,
- run a short GPU smoke test with strict timeout,
- confirm memory stays below the local GPU budget,
- export only a bounded subset of particle frames,
- label finite-pulse or impinging cases as geometry proxies, not atomization
  validation.

## Scientific Caveat

This feasibility note does not establish statistically stationary atomization.
The immediate target remains an SPH-generated jet/spray-geometry proxy for
testing geometry extraction and reduced-model handoff.
