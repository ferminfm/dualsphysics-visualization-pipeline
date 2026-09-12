# Restart stencil-validity candidate

Scope: source implementation candidate, not accepted restart qualification.
Successor batch: 20260912-internal-nozzle-restart-state-closure-r1.

The same-source compact diagnostic at source
0cf0732d761d3a2cffdaae83087343533bf89491 localized the first physical
divergence to prediction at native iteration 713. Recorded u/g values match
before prediction. Coarse/ghost u/g changes inside prediction in the continuing
reference, but not in the replay. Predicted face velocity then differs (maximum
axial absolute difference about 0.0028844). This precedes pressure projection.
The replay was memory-guard stopped after the completed observation interval;
its negative terminal remains explicit and is not a successful-run receipt.

The installed stencil implementation computes boundary/restriction work from
each field's persistent stencil.bc bits and its declared dependencies. The
predictor does not otherwise write u or g. The prior keyed closure restored
their values after boundary reconstruction without restoring validity metadata.

Candidate metadata v9 retains the existing native dump and exact keyed v4
payload and adds the recorded boundary-validity bits for u, g and their cs
dependency. Bits are captured after checkpoint serialization and restored only
after keyed state restoration/verification. A recorded dirty value remains
dirty; no unconditional clean/dirty value is invented. Loop-local io and width
are not persisted. Small native stencil traces expose the actual read state.
Legacy metadata without these bits is accepted only through the existing
explicit historical diagnostic route, never as new-source production evidence.

Strict native/Python tests reject missing, duplicated, malformed and unknown
metadata. The existing accepted-step functional, 5e-8/1e-12 volume tolerances,
core 1e-7, profile/raw 1e-8, physics, geometry, pressure BCs and solver
tolerances are unchanged. All original source-bound numerical gates and probe
neutrality must still pass before production A/B. No unknown inactive values
are copied, zeroed or newly serialized by this candidate.
