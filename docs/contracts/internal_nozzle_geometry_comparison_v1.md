# Internal-nozzle geometry comparison contract v1

This contract defines comparable CFD records for a future rectangular
aspect-ratio study and later square or elliptical cases. It does not authorize
those runs. It preserves the present claim boundary: the CFD may be transient
and resolution-sensitive, while the analytical momentum-jet formulation
assumes statistical stationarity and total momentum conservation.

## Case identity and provenance

Each record must identify the scientific Git commit, case/configuration hash,
geometry family, full/quarter domain, resolution policy, physical properties,
pressure forcing, boundary-condition types, solver tolerances, checkpoint
generation, output frame, and local-evidence manifest. A quarter-domain record
must state its symmetry classification and must never be described as
independent full-domain physics.

The geometry definition must report nozzle area, hydraulic diameter, major and
minor dimensions, aspect ratio, contraction, straight length, exit coordinate,
and downstream domain. The experimental design must declare rather than imply
which quantities are held fixed across geometries.

## Required coordinates

Every observation reports all coordinates available from the same accepted
state:

- nondimensional time, `t_star = t U_ref / D_h`;
- cumulative discharged liquid volume normalized by `A0 D_h`;
- liquid volumetric and mass flow, `Q_l` and `mdot_l`;
- profile-integrated kinetic axial momentum flux, `J_k`;
- pressure contribution, `J_p`;
- total axial flux, `J_total = J_k + J_p`;
- pressure drop from the declared forcing plane to the exit.

The legacy product of flow and a mean velocity may be retained only as a
labeled proxy. It is not a substitute for either `J_k` or `J_total`.

## Required geometric and field observations

At the exit and declared downstream stations, report exit area, VOF and axial
velocity profiles, `A/A0`, major and minor widths, aspect ratio, centroid,
principal-axis orientation, interface/perimeter proxy, and active-front
position. Report integration planes, masks, cut-cell treatment, density/phase
convention, quadrature, signs, units, and time sampling.

Every record includes checkpoint and resource provenance plus an explicit
L7/L8 resolution-uncertainty marker. Missing quantities remain missing; they
must not be replaced by differently defined surrogates.

## Matching and interpolation

All geometry comparisons report an equal-`t_star` view and at least one
hydraulic-state view when the data support it. Candidate hydraulic matching
coordinates are cumulative discharge, `mdot_l`, `J_k`, and `J_total`.

Hydraulic-state matching is valid only when the selected coordinate brackets
the target within a single monotonic interval. Use linear interpolation between
the two bracketing accepted observations and report their times, values,
separation, and the interpolation fraction. Do not extrapolate. If the target
has multiple crossings, report the ambiguity and either compare every crossing
or decline the match. Propagate at least temporal-bracketing, numerical-reducer,
and declared resolution uncertainties; do not report more precision than those
supports permit.

The default reporting recommendation is therefore dual-coordinate: equal
`t_star` plus a matched hydraulic state. For a transient pressure-driven case,
prefer cumulative discharge for integrated material evolution and `J_total`
for the analytical momentum bridge; report both when monotonic coverage permits.
This reporting recommendation does not select the future geometry design.

## Future design alternatives requiring Layer 1 selection

Scientifically non-equivalent alternatives remain separate:

1. equal nozzle area with common pressure forcing;
2. equal hydraulic diameter with common pressure forcing;
3. equal pressure forcing with geometry-specific area and diameter;
4. matched initial flow or momentum where a defensible initialization exists.

Equal area plus common pressure forcing is a useful default candidate because
it preserves the material exit scale while exposing shape effects, but it is
not automatically interchangeable with equal hydraulic diameter or a matched
initial hydraulic state. Layer 1 must select the experiment after reviewing the
terminal transient classification and resolution uncertainty.

## Claim boundary

This contract supports reproducible transient comparisons. It does not by
itself establish stationarity, grid convergence, experimental or physical-model
validation, production readiness, atomization, or analytical-model calibration.
