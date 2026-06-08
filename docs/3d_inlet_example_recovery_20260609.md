# DualSPHysics 3D Inlet Example Recovery Path - 2026-06-09

## Purpose

This note records a feasibility/recovery pass for the missing DualSPHysics 3D
inlet/open-boundary examples needed before attempting statistically averaged
jet/spray-geometry data. No simulation was run, no package was downloaded, and
no XML case was fabricated.

The research target remains statistically stationary, fully atomized liquid
jets/sprays. The current DualSPHysics repository should not substitute another
dam-break or splash visualization for that target.

## Disk And Repo State

`df -h / /home` showed:

| Mount | Size | Used | Available | Use |
| --- | ---: | ---: | ---: | ---: |
| `/` | 94G | 77G | 13G | 87% |
| `/home` | 713G | 414G | 264G | 62% |

The repo was clean before this documentation change.

## Validated Executable

The working wrapper is:

```text
/home/franco/bin/dualsphysics5.4-cuda128
```

The wrapper points to:

```text
/home/franco/opt/dualsphysics/DualSPHysics-cuda128-20260606-0340-retry2/bin/linux/DualSPHysics5.4_linux64
```

`dualsphysics5.4-cuda128 -ver` printed:

```text
DualSPHysics5 v5.4.355 (08-04-2025)
```

The command prints the version but exits nonzero in this CLI mode, so it is
useful as an information probe, not a pass/fail runtime test.

## Local Binary Inventory

The active `bin/linux` directory contains:

| File | Role |
| --- | --- |
| `DualSPHysics5.4_linux64` | Main solver used by the CUDA 12.8 wrapper |
| `GenCase_linux64` | Case preprocessor |
| `PartVTK_linux64` | Particle VTK postprocessor |
| `PartVTKOut_linux64` | Particle VTK output helper |
| `IsoSurface_linux64` | Iso-surface postprocessor |
| `MeasureTool_linux64` | Measurement postprocessor |
| `DsphConfig.xml`, `VERSION_INFO.txt`, `README.txt` | Runtime/config metadata |
| `libChronoEngine.so`, `libdsphchrono.so` | Runtime libraries |

No separate `mphase`, `LiquidGas`, or liquid-gas solver executable was found in
the active `bin/linux` directory.

## Local Example Inventory

The active examples tree is:

```text
examples/
examples/Examples_inletoutlet.pdf
examples/Examples_mphase_liquidgas.pdf
examples/Examples_mphase_nnewtonian.pdf
examples/README.txt
examples/main/01_DamBreak/
```

The only XML case directory present locally is:

```text
examples/main/01_DamBreak/
```

The expected 3D inlet/open-boundary examples are not present as local XML
directories. Specifically, local searches found no case directories or XML files
named:

- `05_SHAPESINLET3D`
- `06_BOX4INLET3D`
- `8_IMPINGINGJET`
- `inletoutlet/05_*`
- `inletoutlet/06_*`
- `inletoutlet/8_*`

## Why The Examples Are Missing

The local `examples/README.txt` says the GitHub repository includes only some
examples to minimize binary-file storage, and that the rest are in the full
DualSPHysics package from the official downloads site.

This matches the local state: the active tree is a Git checkout/build with
documentation PDFs and XML-format templates, but without the full example
directory set.

Classification:

| Question | Current answer |
| --- | --- |
| Present in another local path? | Not found under `/home/franco/opt/dualsphysics`, `/home/franco/Documents/GitHub`, or relevant stack-validation paths. |
| Absent because package incomplete? | Yes, most likely. The local examples README explicitly says the GitHub repository omits most examples. |
| Absent because build stripped examples? | No evidence. The source checkout itself lacks the directories. |
| Incompatible with current executable? | No evidence of incompatibility. The v5.4 executable, XML templates, source code, and changelog all reference inlet/open-boundary support. |

## Evidence That Inlet/Open-Boundary Support Exists

The active tree includes:

- `doc/xml_format/_FmtXML_InOut.xml`
- `doc/xml_format/_FmtXML_InOutMesh.xml`
- source files such as `JSphInOut*` and `JSphGpu_InOut_iker.h`
- changelog entries for 3D inlet definitions, circular jets, arbitrary inlet
  directions, and inlet/outlet mesh data

The bundled `Examples_inletoutlet.pdf` lists these full-package examples:

| Example | Description from local PDF |
| --- | --- |
| `05_SHAPESINLET3D` | 3D inlet buffers with rectangular, cylindrical, diamond, and angled cylindrical shapes |
| `06_BOX4INLET3D` | 3D case with several inlet buffers in the same simulation |
| `7_CURRENTHULL` | 3D constant-velocity flow past a ship hull |
| `8_IMPINGINGJET` | 3D vertical jet impinging on a flat bottom |

This is documentation evidence only. It is not a recovered XML case.

## Multiphase / Liquid-Gas Status

Local evidence for multiphase/liquid-gas is incomplete for the current target:

- `Examples_mphase_liquidgas.pdf` exists.
- `doc/help/DualSPHysics4.0_LiquidGas_Help.out` exists.
- `doc/xml_format/_FmtXML_MphaseNNewtonian.xml` exists.
- `src_mphase/DSPH_v5.0_NNewtonian/` exists.
- No active `bin/linux` multiphase/liquid-gas executable was found.

Therefore, the current validated wrapper should be treated as a main
DualSPHysics v5.4 single-phase/free-surface executable for this recovery pass.
It should not be used to claim fully atomized multiphase liquid-gas validation.

## Safe Recovery Options

### Option A - Recover From Existing Local Archive

Status: not available.

Searches under `/home/franco` did not find a local full-package archive such as
`DualSPHysics*.zip`, `DualSPHysics*.tar*`, `DualSPHysics*.7z`, or similar.

### Option B - Manual Official Full-Package Recovery

Status: recommended next step, but manual.

Recover the full DualSPHysics package matching the local v5.4 build and extract
only the missing example directories, preferably into a non-Git workspace such
as:

```text
/home/franco/stack-validation/YYYYMMDD-HHMM-dualsphysics-inlet-examples/
```

Then inspect these first:

```text
examples/main/inletoutlet/05_SHAPESINLET3D/
examples/main/inletoutlet/06_BOX4INLET3D/
examples/main/inletoutlet/8_IMPINGINGJET/
```

Do not commit raw case outputs, BI4, VTK, logs, or generated particle data.
Commit only a small report or a small reviewed XML snippet if it is needed for
documentation.

### Option C - Reconstruct From XML Templates Only

Status: not recommended yet.

The local `_FmtXML_InOut.xml` template contains useful 3D `<zone3d>` examples,
including particle-based inlet zones, rotations, and fixed velocities. However,
reconstructing a statistically meaningful 3D jet case from templates alone would
require scientific and XML-design assumptions that have not been validated.

This option should remain blocked until a real example XML can be compared.

### Option D - Use GitHub/Source Docs Only

Status: insufficient for this pass.

The local checkout remote is `https://github.com/DualSPHysics/DualSPHysics.git`,
and the local examples README says that GitHub intentionally omits many example
files. Without downloading or browsing, the local source docs are not enough to
recover a complete case safely.

## Recommended Next Simulation Route

1. Manually recover the full v5.4 example package or a verified official example
   subset.
2. Inspect `05_SHAPESINLET3D` first because it directly exercises 3D inlet
   shapes, including non-circular inlet buffers.
3. Inspect `8_IMPINGINGJET` second because it is jet-like, but document it as an
   impinging-jet/open-boundary proof, not atomization validation.
4. Run only a tiny bounded smoke case outside Git after XML inspection.
5. If the smoke case works, define a short quasi-stationary window, discard early
   transients, export VTK/particle frames, and compute time-averaged slice
   metrics for SprayGeo/Ideal Momentum Jet Explorer.

## Stop Conditions For The Next Prompt

- Do not use dam-break outputs as the jet/spray substitute.
- Do not fabricate XML from templates without comparing to a real recovered
  example.
- Do not download the full package unattended.
- Do not run large GPU cases before a tiny smoke case proves the inlet example
  setup.
- Do not claim fully atomized or multiphase pressure-atomization behavior from
  the current main solver path.
