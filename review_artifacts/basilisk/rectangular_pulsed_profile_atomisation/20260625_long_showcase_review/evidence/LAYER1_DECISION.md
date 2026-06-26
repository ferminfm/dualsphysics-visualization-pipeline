# Layer-1 Decision

Status: `internal_review_decision_recorded`

This note records the Layer-1 review decision for the long Basilisk rectangular pulsed-profile benchmark packet. It is not a public release approval.

## Accepted Internal Lead

The official circular route is accepted as the internal visual/scientific lead candidate for continued review.

Rationale:
- it is the official circular control route;
- it completed the long window to `t=2.0`;
- it has 101 physical frames;
- the corrected primary sequence includes all 101 physical frames exactly once;
- the boundary-clearance audit found no meaningful downstream or lateral boundary contact through `t=2.0`;
- the corrected flythrough uses a scientifically safe pre-boundary hero frame and passed rendered mask/raycast visibility QA.

## Rectangular Route Boundary

The rectangular route may be shown only as a secondary caveated comparison.

Required wording:
- selected case: `C1_rect_area_top_hat`;
- selected profile: `rect_area_top_hat`;
- description: `2:1 rectangular top-hat imposed-inlet comparison`;
- the rectangular velocity is imposed at the inlet plane;
- internal nozzle flow is not resolved.

Poiseuille-series profiles were implemented and tested, but they were not selected by the bounded candidate gate. The selected long rectangular route must not be called Poiseuille.

## Publication Boundary

Public packaging remains blocked.

Required gates remain:
- `fit_ready=false`;
- `public_ready=false`;
- no validation claim;
- no production-CFD claim;
- no stationary-spray claim;
- no experimental-agreement claim;
- no true-atomisation claim;
- no pressure-atomized-nozzle validation claim;
- no final-predictive-modeling claim.

The v2 flythrough remains subject to direct human visual inspection before any public packaging task is authorized.
