# Scalar Media Method

This task reuses the accepted V3.1 no-pressure scalar field media from the prior long-benchmark postprocess packet. It does not fabricate pressure panels.

Displayed fields are limited to real available diagnostics:

- phase/VOF context;
- velocity magnitude / speed;
- diagnostic vorticity magnitude;
- ambient-phase speed/context where available.

Pressure is blocked because restored `p` had zero range in prior exports and no validated runtime pressure export exists for this batch.
