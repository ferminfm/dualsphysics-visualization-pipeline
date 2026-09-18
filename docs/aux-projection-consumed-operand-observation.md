# Auxiliary projection consumed-operand observation

This successor extends observation and source/build identity, not solver physics.
Scientific base: 913873858cce9878d949d3d563131133f39841f8. No governing equation,
boundary condition, material coefficient, grid spacing, tolerance or timestep
rule is changed. No restart repair or qualification is claimed by these files.

The compiler adapter operates **after qcc stencil inference**. It wraps generated
field lvalues with pointer-preserving observations. Read and read-modify-write
operands are copied without floating arithmetic; write-only storage is never
read by the probe. Observer callbacks are explicitly excluded from claims about
solver consumption. Actual pointer escapes fail trace qualification. Metadata,
constant operands and topology predicates are distinguished from field values.
Erasing inserted hooks/wrappers reconstructs the original generated C exactly.

The scoped window is auxiliary pressure `pf`, iteration 363, within the existing
declared forensic interval and forensic mode 2. The trace records each accepted
access's site, original function/file/line, role, level, cell, field, stencil
offset, boundary-validity value, sequence and consumed numeric value. Operator
markers bind projection, residual, cycle and relaxation level/order. Field
metadata includes restriction/prolongation/boundary function identities relative
to the same executable, not exported absolute process addresses.

The concrete matched question is whether the first coarse/ghost pressure,
coefficient, geometry, RHS or correction operand read differs before the first
divergent auxiliary residual/relaxation action. Warm-start and work-vector
differences must be shown at actual reads, not inferred from whole-field hashes.
Predicate return values show actual boundary/neighbor selection; they are not
arbitrary raw memory snapshots or proof that every unused flag was causal.

Output is a streaming gzip trace with explicit little-endian 64-byte records,
bounded to 300 million records and 1 GiB compressed. The strict streaming decoder
requires closed operator intervals, complete phase coverage, exact sequence and
site identities, finite consumed values, field metadata and terminal counts.
The paired comparator refuses to subtract unmatched vectors; it reports earliest
identity/value differences and per-level/function/field numeric norms. These
norms do not replace or relax the original acceptance tests.

The optional observation source/build formats are explicitly versioned. Legacy
formats retain their behavior. The overlay format binds the transformer, runtime,
compiler adapter, generated C, transformed C, site inventory, compiler and binary.
The qualified launcher remains the only scientific entry point. This successor
gate rejects predecessor batch permits and enforces ceilings of 8 full-resolution
and 10 total scientific starts; the parent additionally reserves two diagnostic
roles together with all six final roles.

Deterministic evidence at this checkpoint: 128 synthetic/unit/adversarial tests
passed in supervised run f54cf7bb-63f5-4149-9cc3-6c1c1cd91f5d. A generated-C draft
with 9300 potential sites compiled; no CFD binary was executed. The actual trace
writer's synthetic probe-on/off output was bit-exact. This does **not** establish
full-resolution probe neutrality or scientific qualification: those remain
source-bound execution gates. The M1 admission decision also requires the final
sealed build, exact coverage audit and resource forecast.
