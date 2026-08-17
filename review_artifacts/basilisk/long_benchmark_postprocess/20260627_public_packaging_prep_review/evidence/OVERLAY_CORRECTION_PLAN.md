# Overlay Correction Plan

No corrected proxy overlays were generated in this task. The current V3.1 overlays pass internal-review bounds and the request prohibits long rerenders unless short overlay fixes are required.

## Future lightweight overlay-only plan

If human review approves public-prep refinement, create short overlay-only proxies from the existing MP4s with ffmpeg/Pillow compositing:

1. Strip or cover internal `public_ready=false` overlays for public draft copies only.
2. Replace with compact lower-third text:
   - `Basilisk-to-Blender technical sample`
   - `two-phase VOF benchmark; solver-derived facets; not validation`
   - `Rectangular route: imposed-inlet top-hat comparison`
3. Keep the original internal V3.1 media unchanged in the review packet.
4. Generate 10-20 second public-draft proxies first, not full rerenders.
5. Require human wording review before any site copy or publication.

## Full rerender condition

A full Blender rerender should only be authorized if public review rejects the composition, transparency, or camera path itself. Overlay wording alone should be handled by compositor proxies.
