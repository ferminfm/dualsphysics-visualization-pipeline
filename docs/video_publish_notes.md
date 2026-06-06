# Video Publishing Notes

This note prepares manual publishing metadata for the front-view dam-break
portfolio video. It does not upload anything and does not include the MP4 file
in Git.

## Source Artifact

- Local MP4:
  `/home/franco/stack-validation/20260607-0219-dambreak-frontview-final-video/dambreak2d_frontview_final_0000_0150.mp4`
- Local thumbnail:
  `/home/franco/stack-validation/20260607-0219-dambreak-frontview-final-video/thumbs/dambreak2d_frontview_final_thumbnail.png`
- Committed thumbnail:
  `assets/dambreak_frontview_video_thumbnail.png`
- Technical format: H.264, yuv420p, 1280 x 720, 24 fps, 22.708333 s

## Titles

English:

```text
DualSPHysics to Blender: Front-view Dam-break Visualization Pipeline
```

Japanese alternative:

```text
DualSPHysicsからBlenderへ：正面視点ダムブレイク可視化パイプライン
```

Spanish alternative:

```text
De DualSPHysics a Blender: visualizacion frontal de dam-break
```

## Descriptions

English:

```text
Front-view dam-break visualization pipeline demo generated from a local
DualSPHysics CUDA run, converted to VTK, assembled with Python, rendered in
headless Blender, and encoded as MP4.

This is a small visualization-pipeline demonstration, not production CFD
validation of dam-break physics. Frame 0200 was excluded after visual QA; the
published sequence uses frames 0000-0150.

Pipeline: DualSPHysics CUDA -> VTK -> Python -> Headless Blender -> MP4

Future YouTube URL: TBD
```

Japanese:

```text
ローカル環境で実行したDualSPHysics CUDAの小規模ダムブレイク結果をVTKに変換し、
PythonでHUDとカードを追加し、ヘッドレスBlenderで可視化してMP4にした
可視化パイプラインのデモです。

これは可視化ワークフローのデモであり、ダムブレイク物理の本格的なCFD検証では
ありません。視覚QAの結果、フレーム0200は除外し、公開用シーケンスは
0000-0150の範囲を使用しています。

パイプライン: DualSPHysics CUDA -> VTK -> Python -> Headless Blender -> MP4

将来のYouTube URL: TBD
```

Spanish:

```text
Demostracion de una tuberia de visualizacion dam-break generada desde una
corrida local de DualSPHysics CUDA, convertida a VTK, ensamblada con Python,
renderizada con Blender en modo headless y codificada como MP4.

Este video es una demostracion pequena de la tuberia de visualizacion, no una
validacion CFD de produccion de la fisica del dam-break. El frame 0200 fue
excluido despues de QA visual; la secuencia publicada usa frames 0000-0150.

Pipeline: DualSPHysics CUDA -> VTK -> Python -> Headless Blender -> MP4

URL futura de YouTube: TBD
```

## Tags

```text
DualSPHysics, Blender, CFD visualization, SPH, smoothed particle hydrodynamics,
dam-break, free-surface flow, GPU computing, CUDA, VTK, headless rendering,
scientific visualization, portfolio, fluid simulation
```

## Manual Upload Checklist

- Rewatch the full MP4 locally before upload.
- Confirm the title card remains readable on mobile-sized preview.
- Confirm the HUD text is not too small after YouTube compression.
- Use the committed thumbnail:
  `assets/dambreak_frontview_video_thumbnail.png`.
- Recommended visibility: upload as unlisted first.
- Add the caveat in the first paragraph of the description.
- Verify frame 0200 is not referenced as included.
- After review, replace the placeholder below with the final public or unlisted
  URL.

## Future YouTube URL

```text
TBD
```
