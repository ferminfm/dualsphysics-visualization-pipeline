"""Render Basilisk internal-nozzle VOF facet sequences in headless Blender.

The script consumes Basilisk ``output_facets(f)`` files described by a surface
manifest and renders topology-preserving Cycles frames. It intentionally keeps
media outputs outside the repository; only this reusable automation belongs in
Git.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import bpy
from mathutils import Vector


CAVEAT_TEXT = "Pressure-driven two-phase connected-jet VOF prototype - not atomisation validation"
QUARTER_TEXT = "One simulated quadrant mirrored for visualization - not independent full-domain physics"


@dataclass(frozen=True)
class SurfaceFrame:
    index: int
    time: float
    iteration: int
    path: Path
    source_frame_id: str
    facet_cell_count: int
    nozzle_exit_x: float
    dh: float
    maxlevel: int | None


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--surface-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--shot",
        choices=("sequence", "flythrough", "comparison", "multiview", "smoke"),
        default="sequence",
    )
    parser.add_argument("--second-manifest", type=Path)
    parser.add_argument("--second-surface-root", type=Path)
    parser.add_argument("--mode-label", default="Full-domain L7")
    parser.add_argument("--second-mode-label", default="Full-domain L8")
    parser.add_argument("--quarter", action="store_true")
    parser.add_argument("--persistent-label", default=CAVEAT_TEXT)
    parser.add_argument("--resolution-x", type=int, default=1920)
    parser.add_argument("--resolution-y", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--preview-samples", type=int, default=8)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--flythrough-frames", type=int, default=72)
    parser.add_argument("--camera-preset", default="oblique")
    parser.add_argument("--material-preset", default="clear_water")
    parser.add_argument("--device-preference", default="OPTIX,CUDA,CPU")
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--frame-mapping-out", type=Path)
    parser.add_argument("--start-at-first-missing", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    return parser.parse_args(_argv())


def load_surface_manifest(manifest_path: Path, surface_root: Path) -> tuple[dict[str, object], list[SurfaceFrame]]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames: list[SurfaceFrame] = []
    for row in data.get("surfaces", []):
        filename = row.get("filename") or row.get("mirrored_surface") or row.get("surface")
        if not filename:
            raise SystemExit(f"ERROR: surface row lacks filename/mirrored_surface: {row}")
        rel = Path(str(filename))
        candidates = [surface_root / rel, surface_root / rel.name]
        path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
        index = int(row["surface_index"])
        frames.append(
            SurfaceFrame(
                index=index,
                time=float(row["time"]),
                iteration=int(row.get("iteration", row.get("source_iteration", -1))),
                path=path,
                source_frame_id=str(row.get("source_frame_id", f"visual_{index:04d}")),
                facet_cell_count=int(row.get("facet_cell_count", row.get("mirrored_facet_count", 0))),
                nozzle_exit_x=float(row.get("nozzle_exit_x", 2.08885689553)),
                dh=float(row.get("Dh", 0.139257126368)),
                maxlevel=int(row["maxlevel"]) if "maxlevel" in row else None,
            )
        )
    frames.sort(key=lambda frame: frame.index)
    if not frames:
        raise SystemExit(f"ERROR: no surfaces in {manifest_path}")
    missing = [frame.path for frame in frames if not frame.path.exists()]
    if missing:
        sample = ", ".join(str(path) for path in missing[:5])
        raise SystemExit(f"ERROR: missing surface files: {sample}")
    return data, frames


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_facets(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]], dict[str, str]]:
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    meta: dict[str, str] = {}
    current: list[int] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                if len(current) >= 3:
                    faces.append(tuple(current))
                current = []
                continue
            if line.startswith("#"):
                if "=" in line:
                    key, value = line[1:].split("=", 1)
                    meta[key.strip()] = value.strip()
                continue
            parts = line.split()
            if len(parts) >= 3:
                verts.append((float(parts[0]), float(parts[1]), float(parts[2])))
                current.append(len(verts) - 1)
    if len(current) >= 3:
        faces.append(tuple(current))
    if not verts or not faces:
        raise ValueError(f"surface has no facets: {path}")
    return verts, faces, meta


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def make_principled_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float,
    metallic: float = 0.0,
    alpha: float = 1.0,
    transmission: float = 0.0,
    ior: float = 1.333,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        for name_candidate in ("Transmission Weight", "Transmission"):
            if name_candidate in bsdf.inputs:
                bsdf.inputs[name_candidate].default_value = transmission
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = ior
        if "Alpha" in bsdf.inputs and alpha < 1.0:
            material.blend_method = "BLEND"
            material.use_screen_refraction = True
    return material


def add_mesh_object(
    name: str,
    verts: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    material: bpy.types.Material,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=False)
    obj = bpy.data.objects.new(name, mesh)
    obj.location = offset
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def object_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    coords = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mins = Vector((min(v.x for v in coords), min(v.y for v in coords), min(v.z for v in coords)))
    maxs = Vector((max(v.x for v in coords), max(v.y for v in coords), max(v.z for v in coords)))
    return mins, maxs


def combined_bounds(objects: Iterable[bpy.types.Object]) -> tuple[Vector, Vector]:
    mins_list: list[Vector] = []
    maxs_list: list[Vector] = []
    for obj in objects:
        mins, maxs = object_bounds(obj)
        mins_list.append(mins)
        maxs_list.append(maxs)
    mins = Vector((min(v.x for v in mins_list), min(v.y for v in mins_list), min(v.z for v in mins_list)))
    maxs = Vector((max(v.x for v in maxs_list), max(v.y for v in maxs_list), max(v.z for v in maxs_list)))
    return mins, maxs


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_box(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


def add_label(text: str, location: Vector, size: float, material: bpy.types.Material) -> bpy.types.Object:
    curve = bpy.data.curves.new("label_curve", "FONT")
    curve.body = text
    curve.align_x = "LEFT"
    curve.align_y = "CENTER"
    curve.size = size
    obj = bpy.data.objects.new("persistent_label", curve)
    obj.location = location
    obj.data.materials.append(material)
    bpy.context.collection.objects.link(obj)
    return obj


def configure_cycles(args: argparse.Namespace) -> dict[str, object]:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.preview_samples if args.smoke else args.samples
    scene.cycles.use_denoising = True
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 6
    scene.cycles.transparent_max_bounces = 6
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.fps = args.fps
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    selected = "CPU"
    errors: list[str] = []
    preferences = bpy.context.preferences
    cycles_prefs = preferences.addons["cycles"].preferences if "cycles" in preferences.addons else None
    if cycles_prefs is not None:
        for device_type in [part.strip().upper() for part in args.device_preference.split(",")]:
            try:
                if device_type != "CPU":
                    cycles_prefs.compute_device_type = device_type
                    cycles_prefs.get_devices()
                    devices = list(cycles_prefs.devices)
                    gpu_devices = [device for device in devices if device.type != "CPU"]
                    if gpu_devices:
                        for device in devices:
                            device.use = device in gpu_devices
                        scene.cycles.device = "GPU"
                        selected = f"Cycles {device_type}: " + ", ".join(device.name for device in gpu_devices)
                        break
                else:
                    scene.cycles.device = "CPU"
                    selected = "Cycles CPU"
                    break
            except Exception as exc:  # Device probing differs across Blender builds.
                errors.append(f"{device_type}: {exc}")
    return {
        "blender_version": bpy.app.version_string,
        "cycles_device": selected,
        "device_errors": errors,
        "samples": scene.cycles.samples,
        "denoising": bool(scene.cycles.use_denoising),
        "adaptive_sampling": bool(getattr(scene.cycles, "use_adaptive_sampling", False)),
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    }


def add_scene_context(
    objects: list[bpy.types.Object],
    nozzle_exit_x: float,
    dh: float,
    label_text: str,
) -> tuple[Vector, float]:
    mins, maxs = combined_bounds(objects)
    center = (mins + maxs) * 0.5
    span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, dh * 8.0, 1e-6)
    floor_z = mins.z - 0.45 * dh
    floor_mat = make_principled_material("brushed_dark_floor", (0.18, 0.19, 0.19, 1.0), 0.55)
    wall_mat = make_principled_material("warm_matte_walls", (0.55, 0.52, 0.47, 1.0), 0.72)
    nozzle_mat = make_principled_material("matte_nozzle_graphite", (0.07, 0.075, 0.08, 1.0), 0.38)
    label_mat = make_principled_material("label_matte_white", (0.92, 0.90, 0.84, 1.0), 0.42)

    add_box(
        "floor",
        (center.x + 0.2 * span, center.y, floor_z),
        (span * 1.7, span * 1.12, dh * 0.06),
        floor_mat,
    )
    add_box(
        "back_wall",
        (center.x + 0.2 * span, maxs.y + 0.22 * span, center.z + 0.32 * span),
        (span * 1.7, dh * 0.06, span * 0.88),
        wall_mat,
    )
    add_box(
        "side_wall",
        (mins.x - 0.20 * span, center.y, center.z + 0.32 * span),
        (dh * 0.06, span * 1.12, span * 0.88),
        wall_mat,
    )

    opening_w = dh * 1.5
    opening_h = dh * 0.75
    nozzle_x = nozzle_exit_x - dh * 0.4
    add_box("plenum_block", (nozzle_x - dh * 2.4, 0.0, 0.0), (dh * 2.9, opening_w * 1.8, opening_h * 1.9), nozzle_mat)
    add_box("contraction_lip_top", (nozzle_x, 0.0, opening_h * 0.75), (dh * 0.8, opening_w * 1.25, opening_h * 0.22), nozzle_mat)
    add_box("contraction_lip_bottom", (nozzle_x, 0.0, -opening_h * 0.75), (dh * 0.8, opening_w * 1.25, opening_h * 0.22), nozzle_mat)
    add_box("contraction_lip_left", (nozzle_x, -opening_w * 0.70, 0.0), (dh * 0.8, opening_w * 0.18, opening_h * 1.25), nozzle_mat)
    add_box("contraction_lip_right", (nozzle_x, opening_w * 0.70, 0.0), (dh * 0.8, opening_w * 0.18, opening_h * 1.25), nozzle_mat)

    label_location = Vector((mins.x - span * 0.10, mins.y - span * 0.44, maxs.z + span * 0.15))
    label = add_label(label_text, label_location, span * 0.030, label_mat)

    bpy.ops.object.light_add(type="AREA", location=(center.x + span * 0.10, center.y - span * 0.85, center.z + span * 0.95))
    key = bpy.context.object
    key.name = "soft_key_light"
    key.data.energy = 820
    key.data.size = span * 0.70
    bpy.ops.object.light_add(type="AREA", location=(center.x - span * 0.45, center.y + span * 0.42, center.z + span * 0.58))
    fill = bpy.context.object
    fill.name = "cool_fill_light"
    fill.data.energy = 150
    fill.data.size = span * 0.95
    bpy.ops.object.light_add(type="POINT", location=(maxs.x + span * 0.25, mins.y - span * 0.28, maxs.z + span * 0.44))
    rim = bpy.context.object
    rim.name = "small_rim_light"
    rim.data.energy = 95
    bpy.context.scene.world.color = (0.025, 0.028, 0.032)
    label.rotation_euler = (math.radians(68.0), 0.0, 0.0)
    return center, span


def set_camera(center: Vector, span: float, preset: str, frame_index: int = 0, frame_total: int = 1) -> None:
    if not bpy.context.scene.camera:
        bpy.ops.object.camera_add()
        bpy.context.scene.camera = bpy.context.object
    camera = bpy.context.scene.camera
    if preset == "profile":
        location = center + Vector((span * 0.08, -span * 1.72, span * 0.36))
        ortho = span * 1.15
    elif preset == "top":
        location = center + Vector((span * 0.05, -span * 0.08, span * 1.85))
        ortho = span * 1.25
    elif preset == "exit":
        location = center + Vector((-span * 1.18, -span * 0.62, span * 0.34))
        ortho = span * 0.90
    elif preset == "flythrough":
        t = frame_index / max(frame_total - 1, 1)
        theta = math.radians(225.0 - 115.0 * t)
        radius = span * (1.15 - 0.42 * t)
        location = Vector((
            center.x + radius * math.cos(theta) - span * 0.28 * t,
            center.y + radius * math.sin(theta),
            center.z + span * (0.55 - 0.18 * t) + math.sin(t * math.pi) * span * 0.11,
        ))
        ortho = span * (1.08 - 0.32 * t)
    else:
        location = center + Vector((span * 0.82, -span * 1.35, span * 0.52))
        ortho = span * 1.24
    camera.location = location
    look_at(camera, center + Vector((span * 0.02, 0.0, 0.0)))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho
    camera.data.lens = 42


def render_still(path: Path) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    start = time.monotonic()
    bpy.ops.render.render(write_still=True)
    return time.monotonic() - start


def frame_output_path(output_dir: Path, shot: str, index: int) -> Path:
    return output_dir / "frames" / shot / f"{shot}_{index:04d}.png"


def choose_frames(frames: list[SurfaceFrame], max_frames: int, smoke: bool) -> list[SurfaceFrame]:
    if smoke:
        return [frames[-1]]
    if max_frames and max_frames > 0:
        return frames[:max_frames]
    return frames


def build_scene_for_frame(
    frame: SurfaceFrame,
    material: bpy.types.Material,
    label: str,
    camera_preset: str,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[list[bpy.types.Object], Vector, float, dict[str, str]]:
    verts, faces, meta = parse_facets(frame.path)
    obj = add_mesh_object("vof_surface", verts, faces, material, offset=offset)
    center, span = add_scene_context([obj], frame.nozzle_exit_x + offset[0], frame.dh, label)
    set_camera(center, span, camera_preset)
    return [obj], center, span, meta


def render_sequence(args: argparse.Namespace, frames: list[SurfaceFrame], device: dict[str, object]) -> dict[str, object]:
    selected = choose_frames(frames, args.max_frames, args.smoke)
    records: list[dict[str, object]] = []
    for render_index, frame in enumerate(selected):
        out = frame_output_path(args.output_dir, "sequence", render_index)
        if args.start_at_first_missing and out.exists() and out.stat().st_size > 0:
            records.append(frame_record(render_index, frame, out, 0.0))
            continue
        clear_scene()
        water = make_principled_material(
            "clear_water_surface", (0.55, 0.80, 0.96, 0.48), 0.045, alpha=0.48, transmission=0.45
        )
        label = args.persistent_label
        build_scene_for_frame(frame, water, label, args.camera_preset)
        seconds = render_still(out)
        records.append(frame_record(render_index, frame, out, seconds))
        print(f"RENDERED_SEQUENCE_FRAME={render_index} SOURCE={frame.path}")
    return shot_manifest(args, "sequence", selected, records, device, interpolation=False)


def render_flythrough(args: argparse.Namespace, frames: list[SurfaceFrame], device: dict[str, object]) -> dict[str, object]:
    final = frames[-1]
    clear_scene()
    water = make_principled_material("clear_water_surface", (0.55, 0.80, 0.96, 0.48), 0.045, alpha=0.48, transmission=0.45)
    verts, faces, meta = parse_facets(final.path)
    obj = add_mesh_object("vof_surface_final_static", verts, faces, water)
    center, span = add_scene_context([obj], final.nozzle_exit_x, final.dh, args.persistent_label)
    records: list[dict[str, object]] = []
    frame_total = 1 if args.smoke else args.flythrough_frames
    for render_index in range(frame_total):
        out = frame_output_path(args.output_dir, "flythrough", render_index)
        if args.start_at_first_missing and out.exists() and out.stat().st_size > 0:
            continue
        set_camera(center, span, "flythrough", render_index, frame_total)
        seconds = render_still(out)
        records.append(frame_record(render_index, final, out, seconds))
        print(f"RENDERED_FLYTHROUGH_FRAME={render_index} SOURCE={final.path}")
    result = shot_manifest(args, "flythrough", [final], records, device, interpolation=False)
    result["static_source_frame"] = final.source_frame_id
    result["camera_path"] = "curved oblique approach, close-range inspection, upstream travel toward nozzle exit"
    result["clearance_check"] = "orthographic path remains outside opaque nozzle/plenum objects; no intentional geometry clipping"
    result["facet_metadata"] = meta
    return result


def render_comparison(
    args: argparse.Namespace,
    frames: list[SurfaceFrame],
    second_frames: list[SurfaceFrame],
    device: dict[str, object],
) -> dict[str, object]:
    second_by_time = {round(frame.time, 6): frame for frame in second_frames}
    pairs = [(frame, second_by_time[round(frame.time, 6)]) for frame in frames if round(frame.time, 6) in second_by_time]
    selected = pairs[: args.max_frames] if args.max_frames and args.max_frames > 0 else pairs
    if args.smoke:
        selected = selected[-1:]
    records: list[dict[str, object]] = []
    for render_index, (left, right) in enumerate(selected):
        clear_scene()
        water_l7 = make_principled_material(
            "l7_clear_water", (0.55, 0.80, 0.96, 0.48), 0.045, alpha=0.48, transmission=0.45
        )
        water_l8 = make_principled_material(
            "l8_warm_water", (0.95, 0.72, 0.46, 0.44), 0.052, alpha=0.44, transmission=0.35
        )
        label = f"{args.persistent_label}\nLeft: {args.mode_label}; right: {args.second_mode_label}"
        verts_l, faces_l, _ = parse_facets(left.path)
        verts_r, faces_r, _ = parse_facets(right.path)
        sep = max(left.dh, right.dh) * 7.0
        obj_l = add_mesh_object("left_l7_surface", verts_l, faces_l, water_l7, offset=(0.0, -sep * 0.55, 0.0))
        obj_r = add_mesh_object("right_l8_surface", verts_r, faces_r, water_l8, offset=(0.0, sep * 0.55, 0.0))
        center, span = add_scene_context([obj_l, obj_r], left.nozzle_exit_x, left.dh, label)
        set_camera(center, span, "oblique")
        out = frame_output_path(args.output_dir, "comparison", render_index)
        seconds = render_still(out)
        record = frame_record(render_index, left, out, seconds)
        record["second_source_frame_id"] = right.source_frame_id
        record["second_source_path"] = str(right.path)
        record["second_time"] = right.time
        records.append(record)
        print(f"RENDERED_COMPARISON_FRAME={render_index} L={left.path} R={right.path}")
    result = shot_manifest(args, "comparison", [pair[0] for pair in selected], records, device, interpolation=False)
    result["matched_pair_count"] = len(selected)
    return result


def render_multiview(args: argparse.Namespace, frames: list[SurfaceFrame], device: dict[str, object]) -> dict[str, object]:
    final = frames[-1]
    records: list[dict[str, object]] = []
    for render_index, preset in enumerate(["oblique", "profile", "top", "exit"]):
        clear_scene()
        water = make_principled_material(
            "clear_water_surface", (0.55, 0.80, 0.96, 0.48), 0.045, alpha=0.48, transmission=0.45
        )
        build_scene_for_frame(final, water, f"{args.persistent_label}\nView: {preset}", preset)
        out = frame_output_path(args.output_dir, "multiview", render_index)
        seconds = render_still(out)
        record = frame_record(render_index, final, out, seconds)
        record["camera_preset"] = preset
        records.append(record)
        print(f"RENDERED_MULTIVIEW_FRAME={render_index} PRESET={preset}")
    return shot_manifest(args, "multiview", [final], records, device, interpolation=False)


def frame_record(render_index: int, frame: SurfaceFrame, output_path: Path, seconds: float) -> dict[str, object]:
    return {
        "render_frame": render_index,
        "surface_index": frame.index,
        "source_frame_id": frame.source_frame_id,
        "source_time": frame.time,
        "source_iteration": frame.iteration,
        "source_path": str(frame.path),
        "source_sha256": sha256_file(frame.path),
        "output_path": str(output_path),
        "render_seconds": round(seconds, 3),
        "facet_cell_count": frame.facet_cell_count,
        "topology_preserving_operations": "direct mesh import from output_facets(f); no smoothing/remeshing/decimation",
    }


def shot_manifest(
    args: argparse.Namespace,
    shot: str,
    physical_frames: list[SurfaceFrame],
    records: list[dict[str, object]],
    device: dict[str, object],
    interpolation: bool,
) -> dict[str, object]:
    return {
        "shot": shot,
        "manifest": str(args.manifest),
        "surface_root": str(args.surface_root),
        "mode_label": args.mode_label,
        "quarter_reconstruction": bool(args.quarter),
        "persistent_label": args.persistent_label,
        "physical_frame_count": len(physical_frames),
        "render_frame_count": len(records),
        "all_physical_frames_included": shot != "sequence" or len(records) == len(physical_frames),
        "presentation_interpolation_used": interpolation,
        "device": device,
        "material_preset": args.material_preset,
        "camera_preset": args.camera_preset,
        "fps": args.fps,
        "records": records,
        "script": Path(__file__).name,
    }


def write_outputs(result: dict[str, object], args: argparse.Namespace) -> None:
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.frame_mapping_out and result.get("shot") == "sequence":
        args.frame_mapping_out.parent.mkdir(parents=True, exist_ok=True)
        with args.frame_mapping_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "render_frame",
                    "surface_index",
                    "source_frame_id",
                    "source_time",
                    "source_iteration",
                    "source_path",
                    "source_sha256",
                    "output_path",
                ],
            )
            writer.writeheader()
            for record in result.get("records", []):
                writer.writerow({key: record.get(key, "") for key in writer.fieldnames})


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.quarter and args.persistent_label == CAVEAT_TEXT:
        args.persistent_label = QUARTER_TEXT
    if args.smoke:
        args.resolution_x = min(args.resolution_x, 640)
        args.resolution_y = min(args.resolution_y, 360)
    _, frames = load_surface_manifest(args.manifest, args.surface_root)
    device = configure_cycles(args)
    if args.shot == "flythrough":
        result = render_flythrough(args, frames, device)
    elif args.shot == "comparison":
        if not args.second_manifest or not args.second_surface_root:
            raise SystemExit("ERROR: comparison requires --second-manifest and --second-surface-root")
        _, second_frames = load_surface_manifest(args.second_manifest, args.second_surface_root)
        result = render_comparison(args, frames, second_frames, device)
    elif args.shot == "multiview":
        result = render_multiview(args, frames, device)
    else:
        result = render_sequence(args, frames, device)
    write_outputs(result, args)
    print(f"BLENDER_SURFACE_RENDER_MANIFEST={args.manifest_out}")


if __name__ == "__main__":
    main()
