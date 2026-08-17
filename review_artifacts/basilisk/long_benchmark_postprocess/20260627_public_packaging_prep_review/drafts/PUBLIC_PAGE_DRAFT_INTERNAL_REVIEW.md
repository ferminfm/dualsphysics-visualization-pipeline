# Public Page Draft - Internal Review Only

## Draft title

Basilisk-to-Blender VOF Visualization Pipeline

## Draft summary

A compact technical sample showing a Basilisk two-phase VOF benchmark carried through a reproducible visualization pipeline: solver-derived facets, frame manifests, topology-preserving surface preparation, Blender rendering, contact sheets, and media metadata. The example includes an official circular control route and a secondary 2:1 rectangular top-hat imposed-inlet comparison.

## What was computed

A bounded Basilisk two-phase VOF benchmark was run previously and postprocessed into solver-derived interface facets and diagnostic field views. The accepted internal review assets use existing solver outputs only.

## What the bridge layer does

The bridge layer connects Basilisk output to Blender review media:

- records frame and surface manifests;
- imports VOF facet surfaces;
- applies topology-preserving surface-normal recipes;
- automates Blender camera/material setup;
- creates contact sheets, stills, ffprobe metadata, and claim-boundary manifests.

## What the videos show

- A lead official circular control sequence.
- A flythrough/inspection clip of a selected high-complexity frame.
- A synchronized circular-vs-rectangular comparison.
- Diagnostic field panels for phase, velocity magnitude, vorticity magnitude, and ambient-phase context.

## What is not claimed

This is not validation, production CFD, experimental agreement, true atomisation prediction, pressure-atomized-nozzle validation, stationary spray analysis, or final predictive modeling. The rectangular route is an imposed-inlet comparison and does not resolve internal-nozzle flow.

## Link placeholders

- Video: `[future reviewed video URL]`
- Code: `[future basilisk-blender-bridge repository]`
- Technical note: `[future claim-boundary and method note]`
