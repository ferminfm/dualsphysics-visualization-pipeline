# Field Visualization Feasibility Decision

Status: `partial_success`

Field visualizations are enabled from existing saved data for phase, velocity, velocity magnitude, and vorticity-magnitude diagnostics. They are not enabled for pressure, lambda2, or Q-like fields.

## Enabled

- Phase/VOF slices from restored `f`.
- Liquid/interface/ambient phase separation using `f` thresholds.
- Velocity component and speed slices from restored `u`.
- Vorticity-magnitude diagnostic slices derived from restored velocity.

## Blocked

- Pressure heatmaps are blocked because restored `p` is all zero in the selected checkpoints.
- Lambda2/Q-like visualizations are blocked until a separate validated adaptive-grid gradient export is implemented.

## Future Export Plan

For pressure and vortex-criterion media, add an explicit postprocess event to the Basilisk source or a dedicated extractor that writes pressure and gradient diagnostics at runtime/checkpoint time, then verify nonzero pressure range and gradient conventions before any media task consumes them.
