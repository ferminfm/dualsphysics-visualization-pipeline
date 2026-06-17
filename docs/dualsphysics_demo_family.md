# DualSPHysics Scientific Visualization Demo Family

This repo now contains a family of DualSPHysics visualization and
post-processing demonstrations. They share a pipeline:

```text
DualSPHysics GPU output -> PartVTK / IsoSurface -> headless Blender -> ffmpeg
```

The demos have different roles. They should not be presented as production CFD,
physical validation, experimental agreement, or fully atomized spray
simulation.

## Public Family Table

| Demo | Base case/source | Role | Visual status | YouTube/site status | Metrics status | Public classification | Best audience |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dam-break workflow | Small DualSPHysics dam-break run | Compact proof of GPU SPH -> VTK -> Blender -> MP4 workflow and QA discipline. | Accepted front-view video and thumbnail. | YouTube: <https://youtu.be/EDUGMpGn5MI>; included on personal SPH case-study page. | No jet metrics; visualization-pipeline evidence only. | Supporting workflow demo. | Recruiter, Developer Advocate, client |
| ShapesInlet3D | Official `05_ShapesInlet3D` inlet/open-boundary example | Primary official 3D inlet scientific-demonstration video. | Accepted v1 scientific-demonstration video with particle, surface, and velocity views. | YouTube: <https://youtu.be/eMUbVgLRkHY>; included on personal SPH case-study page. | Geometry-extraction preparation only; no stationary jet metrics. | Public scientific-demonstration candidate. | Collaborator, Developer Advocate, technical client |
| ImpingingJet | Official `08_ImpingingJet` / `CaseJet2D` | Front-on 2D reconstructed-surface and scalar-analysis example. | Composite showcase with surface, particle, impact zoom, velocity, density, and pressure analysis. | YouTube used by personal site: <https://youtu.be/5JkdLRPYWUI>. | Scalar visualization only; no 3D free-jet metrics. | Public showcase candidate, with 2D caveat. | Developer Advocate, research collaborator |
| Rectangular high-speed jet proxy, first pass | Modified `06_Box4Inlet3D` | Early single-rectangular-inlet proof that custom copied cases can run and export proxy metrics. | Technically successful but visually coarse; superseded. | Internal only. | Preliminary particle-slab metrics. | Internal technical evidence. | Research workflow |
| Rectangular jet v2 | Copied modified rectangular inlet profile | Accepted improvement over first pass: larger view, finer spacing, surface/velocity render package. | Accepted review package, superseded by v3/v4. | Internal/public-preview lineage only. | Preliminary slice metrics. | Superseded public-preview lineage. | Research workflow |
| Rectangular jet v3 | Streamwise-gravity rectangular inlet proxy | Corrected gravity/jet-axis convention and added pressure, velocity, and moving-slice diagnostics. | Stronger transparent-water and analysis package, superseded by v4. | Internal/public-preview lineage only. | Diagnostics and moving-slice metrics. | Superseded public-preview lineage. | Research workflow |
| Rectangular jet final-polish | Extended streamwise-gravity rectangular inlet proxy | Current rectangular geometry-proxy and data-bridge case. | v4.3 corrected the cinematic/cross-section story; the final-polish pass adds EN/JA/ES publication cards, gas-phase clarification, and YouTube/web metadata. | Not uploaded yet; metadata prepared for manual hosting. Personal site may mention it as analysis-ready, not embed it until reviewed. | 414-row SprayGeo-compatible handoff plus 24-row Ideal Momentum Jet Explorer overlay preview lineage. | Public-preview candidate, blocked for fitting until stationary window exists. | Research collaborator, Developer Advocate, technical client |

## Recommended Public Structure

- Lead with one umbrella project page: **SPH simulation and visualization**.
- Embed or link the three hosted videos there: ShapesInlet3D, dam break, and
  ImpingingJet.
- Mention the rectangular final-polish proxy as the analysis/data-bridge step
  until its video is hosted externally.
- Keep detailed solver provenance in this repo's per-demo docs, not on the
  public site page.
- Do not add separate thin public pages for every intermediate rectangular
  version.

## Caveats To Keep Near Public Media

- Visualization and post-processing demonstration; not physical validation.
- GPU SPH to Blender workflow demonstration; not production CFD validation.
- Single-phase geometry-proxy demonstration; not atomization validation.
- The rectangular overlay is a non-stationary format bridge, not fit-ready
  reduced-model evidence.

## Detailed Docs

- Dam-break: [video_publish_notes.md](video_publish_notes.md)
- ShapesInlet3D: [dualsphysics_shapesinlet3d_showcase.md](dualsphysics_shapesinlet3d_showcase.md)
- ImpingingJet: [dualsphysics_impingingjet_showcase.md](dualsphysics_impingingjet_showcase.md)
- Rectangular proxy: [dualsphysics_rectangular_highspeed_jet_proxy.md](dualsphysics_rectangular_highspeed_jet_proxy.md)
- Video metadata: [video_metadata.md](video_metadata.md)
- Walkthrough: [walkthrough_dualsphysics_to_blender.md](walkthrough_dualsphysics_to_blender.md)
- Troubleshooting: [troubleshooting.md](troubleshooting.md)
- Cloud-extension plan: [cloud_extension_plan.md](cloud_extension_plan.md)
