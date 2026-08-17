# Claim Language Matrix

Task: `01_physical_framing_claim_strategy`

Status: `claim_matrix_ready`

Persistent flags:

- `fit_ready=false`
- `public_ready=false`

## Approved Internal Wording

| Topic | Approved wording | Required caveat |
| --- | --- | --- |
| Overall case | Long Basilisk two-phase VOF pulsed-jet benchmark | Internal review evidence only |
| Primary route | Official circular pulsed-jet control benchmark candidate | Not validation or public-ready |
| Rectangular route | `C1_rect_area_top_hat` / `rect_area_top_hat`, a 2:1 rectangular top-hat imposed-inlet comparison | Not Poiseuille and not internal-nozzle flow |
| Phase model | Two-phase VOF interface benchmark with surface tension and density ratio `27.84` | Current media mostly visualize the liquid interface, not separate ambient fields |
| Current physical analog | Dense-ambient or no-gravity two-phase jet benchmark | Not ordinary room-condition water-in-air |
| Metrics | Thresholded topology/component diagnostics | Not droplet statistics, D32, SMD, or fit data |
| Media | Solver-derived native VOF/facet and Blender/Cycles review media | Internal visual review only |
| Gravity | Current branch is no-gravity; future gravity branch is design-only | Do not imply gravity in current data |

## Approved Later-Public Wording After Human Review

Use only after a separate public-packaging task approves final copy and assets:

| Topic | Possible wording | Mandatory visible caveat |
| --- | --- | --- |
| Case-study label | Two-phase VOF pulsed-jet benchmark and visualization pipeline | Not validation or production CFD |
| Capability evidence | Reproducible solver-to-review-media workflow with native/facet evidence and claim boundaries | Internal benchmark lineage; public-ready only after approval |
| Rectangular comparison | Caveated rectangular imposed-inlet comparison | Not an internal-nozzle simulation |

## Prohibited Wording

| Prohibited claim | Reason |
| --- | --- |
| Validated atomisation simulation | No validation dataset or experimental agreement is established |
| Production CFD | The packet is an internal benchmark/review package |
| Stationary spray evidence | No quantified stationary window is demonstrated |
| Experimental agreement | No experimental comparison is present |
| Room-condition water-in-air spray | Density ratio is `27.84`, current case has no gravity, and dimensional mapping is not established |
| Pressure-atomized nozzle validation | Rectangular route imposes the velocity at the inlet plane and does not resolve internal nozzle flow |
| Rectangular internal-nozzle flow | No plenum, contraction, wall boundary layer, or natural exit development is resolved |
| Poiseuille rectangular route | Poiseuille-series profiles were tested but were not selected |
| Resolution-independent rectangular conclusion | L9 confirmation did not pass quantitative resolution invariance |
| Droplet-size statistics, D32, SMD | Component counts are thresholded diagnostics only |
| Fit-ready calibration data | Review packet explicitly records `fit_ready=false` |
| Public-ready media | Review packet and blockers record `public_ready=false` |
| Gravity-included current benchmark | Current source/run has no active gravity/body-force term |

## Replacement Phrases

| Instead of | Use |
| --- | --- |
| water-in-air atomization | nondimensional dense-ambient/no-gravity two-phase VOF benchmark |
| rectangular nozzle | rectangular imposed-inlet comparison |
| Poiseuille case | `C1_rect_area_top_hat` / `rect_area_top_hat` selected route |
| validated droplets | thresholded topology/component diagnostics |
| public showcase | internal review media pending human public-packaging approval |
| gravity run | future gravity/body-force branch design |

## Required Boilerplate

Use this paragraph when a reader might infer stronger physical claims:

> This is internal solver-derived benchmark evidence. It is not validation, not production CFD, not stationary spray evidence, not experimental agreement, not pressure-atomized-nozzle validation, and not a public-ready package. The rectangular route is a 2:1 top-hat velocity imposed at the inlet plane, not resolved internal-nozzle flow.
