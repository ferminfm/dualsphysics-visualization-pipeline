"""Render Basilisk atomisation-style facet sequences for internal review.

This Task 07 renderer consumes Basilisk ``output_facets(f)`` surface manifests
and creates topology-preserving Cycles frames. It intentionally keeps generated
media outside the repository; only this reusable automation belongs in Git.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


CAVEAT_TEXT = (
    "Internal scientific review only; solver-derived VOF facets; not validation; "
    "public_ready=false; fit_ready=false"
)
RECTANGULAR_TEXT = "2:1 rectangular top-hat imposed inlet; internal nozzle flow not resolved"
ROUND_TEXT = "Official Basilisk circular pulsed-jet control"


@dataclass(frozen=True)
class SurfaceFrame:
    index: int
    time: float
    iteration: int
    path: Path
    source_frame_id: str
    facet_cell_count: int
    maxlevel: int | None


@dataclass(frozen=True)
class Bounds:
    mins: Vector
    maxs: Vector

    @property
    def center(self) -> Vector:
        return (self.mins + self.maxs) * 0.5

    @property
    def span(self) -> float:
        return max(
            self.maxs.x - self.mins.x,
            self.maxs.y - self.mins.y,
            self.maxs.z - self.mins.z,
            1e-6,
        )


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-manifest", type=Path, required=True)
    parser.add_argument("--primary-surface-root", type=Path, required=True)
    parser.add_argument("--primary-route-id", default="official_round_control")
    parser.add_argument("--comparison-manifest", type=Path)
    parser.add_argument("--comparison-surface-root", type=Path)
    parser.add_argument("--comparison-route-id", default="rectangular_top_hat_imposed_inlet")
    parser.add_argument("--route-manifest", type=Path)
    parser.add_argument("--media-manifest", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("smoke", "sequence", "comparison", "flythrough", "multiview"),
        required=True,
    )
    parser.add_argument("--device-preference", default="OPTIX,CUDA,CPU")
    parser.add_argument("--resolution-x", type=int, default=1920)
    parser.add_argument("--resolution-y", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--preview-samples", type=int, default=8)
    parser.add_argument("--flythrough-frames", type=int, default=96)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--start-at-first-missing", action="store_true")
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--frame-mapping-out", type=Path)
    parser.add_argument("--overlay-title", default="")
    parser.add_argument("--persistent-caveat", default=CAVEAT_TEXT)
    parser.add_argument("--hero-surface-index", type=int, default=-1)
    parser.add_argument("--open-studio", action="store_true")
    parser.add_argument("--corrected-style", action="store_true")
    parser.add_argument("--mask-resolution-x", type=int, default=320)
    parser.add_argument("--mask-resolution-y", type=int, default=180)
    parser.add_argument("--mask-output-root", type=Path)
    return parser.parse_args(_argv())


def load_surface_manifest(manifest_path: Path, surface_root: Path) -> tuple[dict[str, object], list[SurfaceFrame]]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames: list[SurfaceFrame] = []
    for row in data.get("surfaces", []):
        filename = row.get("filename") or row.get("surface") or row.get("mirrored_surface")
        if not filename:
            raise SystemExit(f"ERROR: surface row lacks filename: {row}")
        rel = Path(str(filename))
        candidates = [
            surface_root / rel,
            surface_root / rel.name,
            surface_root.parent / rel,
            surface_root.parent / "surfaces" / rel.name,
        ]
        path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
        frames.append(
            SurfaceFrame(
                index=int(row["surface_index"]),
                time=float(row["time"]),
                iteration=int(row.get("iteration", row.get("source_iteration", -1))),
                path=path,
                source_frame_id=str(row.get("source_frame_id", f"visual_{int(row['surface_index']):04d}")),
                facet_cell_count=int(row.get("facet_cell_count", row.get("mirrored_facet_count", 0))),
                maxlevel=int(row["maxlevel"]) if "maxlevel" in row else None,
            )
        )
    frames.sort(key=lambda frame: frame.index)
    if not frames:
        raise SystemExit(f"ERROR: no surface rows in {manifest_path}")
    missing = [frame.path for frame in frames if not frame.path.exists()]
    if missing:
        raise SystemExit("ERROR: missing surface files: " + ", ".join(str(path) for path in missing[:5]))
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


def bounds_from_verts(verts: Iterable[tuple[float, float, float]]) -> Bounds:
    points = list(verts)
    return Bounds(
        mins=Vector((
            min(point[0] for point in points),
            min(point[1] for point in points),
            min(point[2] for point in points),
        )),
        maxs=Vector((
            max(point[0] for point in points),
            max(point[1] for point in points),
            max(point[2] for point in points),
        )),
    )


def combine_bounds(items: Iterable[Bounds]) -> Bounds:
    bounds = list(items)
    return Bounds(
        mins=Vector((
            min(item.mins.x for item in bounds),
            min(item.mins.y for item in bounds),
            min(item.mins.z for item in bounds),
        )),
        maxs=Vector((
            max(item.maxs.x for item in bounds),
            max(item.maxs.y for item in bounds),
            max(item.maxs.z for item in bounds),
        )),
    )


def scan_sequence_bounds(frames: list[SurfaceFrame]) -> tuple[Bounds, dict[int, Bounds]]:
    per_frame: dict[int, Bounds] = {}
    for frame in frames:
        verts, _, _ = parse_facets(frame.path)
        per_frame[frame.index] = bounds_from_verts(verts)
    return combine_bounds(per_frame.values()), per_frame


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.curves, bpy.data.cameras):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def make_principled_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float,
    metallic: float = 0.0,
    transmission: float = 0.0,
    ior: float = 1.333,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        for key in ("Transmission Weight", "Transmission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = transmission
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = ior
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3]
    material.diffuse_color = color
    return material


def make_emission_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    emission = tree.nodes.new(type="ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = 1.0
    output = tree.nodes.new(type="ShaderNodeOutputMaterial")
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    material.diffuse_color = color
    if color[3] < 1.0:
        material.blend_method = "BLEND"
        material.use_nodes = True
    return material


def add_mesh_object(
    name: str,
    verts: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    material: bpy.types.Material,
    offset: Vector | None = None,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=False)
    obj = bpy.data.objects.new(name, mesh)
    if offset:
        obj.location = offset
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


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


def add_floor_and_walls(bounds: Bounds, y_expand: float = 1.0, include_walls: bool = True) -> None:
    center = bounds.center
    span = bounds.span
    floor_mat = make_principled_material("dark_burnished_floor", (0.105, 0.112, 0.112, 1.0), 0.72)
    wall_mat = make_principled_material("neutral_test_cell_walls", (0.18, 0.19, 0.19, 1.0), 0.84)
    floor_z = bounds.mins.z - 0.16 * span
    add_box(
        "floor_reference",
        (center.x + 0.10 * span, center.y, floor_z),
        (span * 1.45, span * 0.95 * y_expand, span * 0.025),
        floor_mat,
    )
    if not include_walls:
        return
    add_box(
        "back_wall_reference",
        (center.x + 0.12 * span, bounds.maxs.y + 0.32 * span * y_expand, center.z + 0.18 * span),
        (span * 1.55, span * 0.025, span * 0.72),
        wall_mat,
    )
    add_box(
        "side_wall_reference",
        (bounds.mins.x - 0.18 * span, center.y, center.z + 0.18 * span),
        (span * 0.025, span * 0.95 * y_expand, span * 0.72),
        wall_mat,
    )


def add_round_inlet(bounds: Bounds, offset: Vector | None = None) -> None:
    off = offset or Vector((0.0, 0.0, 0.0))
    span = bounds.span
    plate_mat = make_principled_material("thin_inlet_plate_graphite", (0.08, 0.085, 0.088, 1.0), 0.34)
    radius = max(abs(bounds.mins.y), abs(bounds.maxs.y), abs(bounds.mins.z), abs(bounds.maxs.z), span * 0.04)
    outer = radius * 1.42
    x = bounds.mins.x - 0.012 * span + off.x
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    segments = 96
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        verts.append((x, off.y + outer * math.cos(angle), off.z + outer * math.sin(angle)))
        verts.append((x, off.y + radius * math.cos(angle), off.z + radius * math.sin(angle)))
    for i in range(segments):
        a = 2 * i
        b = 2 * ((i + 1) % segments)
        faces.append((a, b, b + 1, a + 1))
    add_mesh_object("thin_round_inlet_reference_plate", verts, faces, plate_mat)


def add_rectangular_inlet(bounds: Bounds, offset: Vector | None = None) -> None:
    off = offset or Vector((0.0, 0.0, 0.0))
    span = bounds.span
    plate_mat = make_principled_material("thin_rectangular_inlet_reference_plate", (0.08, 0.085, 0.088, 1.0), 0.34)
    opening_w = max(bounds.maxs.y - bounds.mins.y, span * 0.11)
    opening_h = max(bounds.maxs.z - bounds.mins.z, span * 0.055)
    frame = max(opening_h * 0.18, span * 0.012)
    x = bounds.mins.x - 0.012 * span + off.x
    add_box("rect_inlet_top_lip", (x, off.y, off.z + opening_h * 0.5 + frame * 0.5), (span * 0.018, opening_w + 2 * frame, frame), plate_mat)
    add_box("rect_inlet_bottom_lip", (x, off.y, off.z - opening_h * 0.5 - frame * 0.5), (span * 0.018, opening_w + 2 * frame, frame), plate_mat)
    add_box("rect_inlet_left_lip", (x, off.y - opening_w * 0.5 - frame * 0.5, off.z), (span * 0.018, frame, opening_h), plate_mat)
    add_box("rect_inlet_right_lip", (x, off.y + opening_w * 0.5 + frame * 0.5, off.z), (span * 0.018, frame, opening_h), plate_mat)
    heat_mat_a = make_principled_material("rect_profile_center_high", (0.93, 0.58, 0.22, 1.0), 0.48)
    heat_mat_b = make_principled_material("rect_profile_edge_low", (0.20, 0.36, 0.58, 1.0), 0.58)
    add_box(
        "rect_profile_heatmap_card",
        (x - 0.035 * span, off.y, off.z),
        (span * 0.012, opening_w * 0.72, opening_h * 0.62),
        heat_mat_a,
    )
    add_box(
        "rect_profile_heatmap_edge_reference",
        (x - 0.038 * span, off.y, off.z),
        (span * 0.006, opening_w * 1.02, opening_h * 1.02),
        heat_mat_b,
    )


def add_lights(bounds: Bounds) -> None:
    center = bounds.center
    span = bounds.span
    bpy.ops.object.light_add(type="AREA", location=(center.x + span * 0.16, center.y - span * 0.72, center.z + span * 0.80))
    key = bpy.context.object
    key.name = "large_soft_key"
    key.data.energy = 430
    key.data.size = span * 0.62
    bpy.ops.object.light_add(type="AREA", location=(center.x - span * 0.32, center.y + span * 0.42, center.z + span * 0.42))
    fill = bpy.context.object
    fill.name = "cool_side_fill"
    fill.data.energy = 105
    fill.data.size = span * 0.85
    bpy.ops.object.light_add(type="POINT", location=(bounds.maxs.x + span * 0.25, bounds.mins.y - span * 0.22, bounds.maxs.z + span * 0.42))
    rim = bpy.context.object
    rim.name = "small_rim_highlight"
    rim.data.energy = 74


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(bounds: Bounds, preset: str, frame_index: int = 0, frame_total: int = 1) -> bpy.types.Object:
    center = bounds.center
    span = bounds.span
    if preset == "profile":
        location = center + Vector((span * 0.04, -span * 1.40, span * 0.24))
        target = center + Vector((span * 0.12, 0.0, 0.0))
        lens = 58
    elif preset == "top":
        location = center + Vector((span * 0.05, -span * 0.10, span * 1.55))
        target = center + Vector((span * 0.08, 0.0, 0.0))
        lens = 50
    elif preset == "inlet":
        location = center + Vector((-span * 0.86, -span * 0.42, span * 0.22))
        target = center + Vector((span * 0.12, 0.0, 0.0))
        lens = 50
    elif preset == "flythrough":
        t = frame_index / max(frame_total - 1, 1)
        theta = math.radians(218.0 - 126.0 * t)
        radius = span * (1.26 - 0.10 * math.sin(t * math.pi))
        stream = span * (-0.12 + 0.30 * t)
        height = span * (0.52 + 0.10 * math.sin(t * math.pi * 1.35))
        location = Vector((
            center.x + stream + radius * math.cos(theta),
            center.y + radius * math.sin(theta),
            center.z + height,
        ))
        target = center + Vector((span * (0.16 - 0.08 * t), 0.0, span * 0.02))
        lens = 30 + 4 * math.sin(t * math.pi)
    else:
        location = center + Vector((span * 0.72, -span * 1.16, span * 0.44))
        target = center + Vector((span * 0.10, 0.0, span * 0.02))
        lens = 48
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "perspective_review_camera"
    camera.data.type = "PERSP"
    camera.data.lens = lens
    camera.data.clip_end = span * 20.0
    look_at(camera, target)
    bpy.context.scene.camera = camera
    return camera


def add_camera_overlay(camera: bpy.types.Object, title: str, lines: list[str]) -> None:
    panel_mat = make_emission_material("overlay_panel_smoke", (0.025, 0.030, 0.034, 0.82))
    text_mat = make_emission_material("overlay_text_warm_white", (0.90, 0.88, 0.80, 1.0))
    accent_mat = make_emission_material("overlay_accent_blue", (0.16, 0.48, 0.66, 1.0))
    distance = 1.65
    half_width = distance * math.tan(camera.data.angle_x * 0.5)
    half_height = distance * math.tan(camera.data.angle_y * 0.5)
    panel_center = (-half_width * 0.43, half_height * 0.62, -distance)
    panel_scale = (half_width * 0.84, half_height * 0.18, 0.002)
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    panel = bpy.context.object
    panel.name = "camera_space_overlay_panel"
    panel.parent = camera
    panel.location = panel_center
    panel.scale = panel_scale
    panel.data.materials.append(panel_mat)
    panel.visible_shadow = False
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    accent = bpy.context.object
    accent.name = "camera_space_overlay_accent"
    accent.parent = camera
    accent.location = (panel_center[0] - panel_scale[0] * 0.96, panel_center[1], -distance + 0.006)
    accent.scale = (half_width * 0.014, panel_scale[1], 0.002)
    accent.data.materials.append(accent_mat)
    accent.visible_shadow = False
    body = "\n".join([title] + lines)
    curve = bpy.data.curves.new("camera_space_overlay_text_curve", "FONT")
    curve.body = body
    curve.align_x = "LEFT"
    curve.align_y = "CENTER"
    curve.size = half_height * 0.034
    curve.space_line = 0.91
    text_obj = bpy.data.objects.new("camera_space_overlay_text", curve)
    text_obj.parent = camera
    text_obj.location = (panel_center[0] - panel_scale[0] * 0.88, panel_center[1], -distance + 0.012)
    text_obj.data.materials.append(text_mat)
    bpy.context.collection.objects.link(text_obj)


def configure_cycles(args: argparse.Namespace) -> dict[str, object]:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.preview_samples if args.mode == "smoke" else args.samples
    scene.cycles.use_denoising = True
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 7
    scene.cycles.transparent_max_bounces = 7
    scene.cycles.transmission_bounces = 7
    scene.render.resolution_x = args.resolution_x if args.mode != "smoke" else min(args.resolution_x, 960)
    scene.render.resolution_y = args.resolution_y if args.mode != "smoke" else min(args.resolution_y, 540)
    scene.render.fps = args.fps
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.world.color = (0.012, 0.014, 0.016)

    selected = "Cycles CPU"
    errors: list[str] = []
    devices_seen: list[dict[str, object]] = []
    cycles_prefs = bpy.context.preferences.addons["cycles"].preferences if "cycles" in bpy.context.preferences.addons else None
    if cycles_prefs is not None:
        for device_type in [part.strip().upper() for part in args.device_preference.split(",")]:
            try:
                if device_type == "CPU":
                    scene.cycles.device = "CPU"
                    selected = "Cycles CPU"
                    break
                cycles_prefs.compute_device_type = device_type
                cycles_prefs.get_devices()
                devices = list(cycles_prefs.devices)
                devices_seen.extend(
                    {"name": device.name, "type": device.type, "use": bool(device.use), "probe": device_type}
                    for device in devices
                )
                gpu_devices = [device for device in devices if device.type != "CPU"]
                if gpu_devices:
                    for device in devices:
                        device.use = device in gpu_devices
                    scene.cycles.device = "GPU"
                    selected = f"Cycles {device_type}: " + ", ".join(device.name for device in gpu_devices)
                    break
            except Exception as exc:
                errors.append(f"{device_type}: {exc}")
    return {
        "blender_version": bpy.app.version_string,
        "cycles_device": selected,
        "gpu_render_used": scene.cycles.device == "GPU",
        "device_errors": errors,
        "devices_seen": devices_seen,
        "samples": scene.cycles.samples,
        "denoising": bool(scene.cycles.use_denoising),
        "adaptive_sampling": bool(getattr(scene.cycles, "use_adaptive_sampling", False)),
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    }


def setup_scene(bounds: Bounds, y_expand: float = 1.0, include_walls: bool = True) -> None:
    add_floor_and_walls(bounds, y_expand=y_expand, include_walls=include_walls)
    add_lights(bounds)


def water_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    return make_principled_material(name, color, roughness=0.035, transmission=0.58, ior=1.333)


def fluid_mask_material() -> bpy.types.Material:
    return make_emission_material("fluid_object_id_mask_white", (1.0, 1.0, 1.0, 1.0))


def measure_mask(path: Path, width: int, height: int) -> dict[str, object]:
    image = bpy.data.images.load(str(path), check_existing=False)
    pixels = list(image.pixels)
    xs: list[int] = []
    ys: list[int] = []
    for yy in range(height):
        for xx in range(width):
            base = 4 * (yy * width + xx)
            # The mask pass still receives color-management/background output in
            # Blender PNGs, so count only the white object-ID emission material.
            if max(pixels[base], pixels[base + 1], pixels[base + 2]) > 0.80:
                xs.append(xx)
                ys.append(yy)
    bpy.data.images.remove(image)
    count = len(xs)
    total = width * height
    if not count:
        return {
            "fluid_pixel_count": 0,
            "fluid_occupancy": 0.0,
            "bbox_norm": [],
            "bbox_intersects_central_80_percent": False,
            "occupancy_between_5_and_70_percent": False,
            "low_visibility_below_10_percent": True,
        }
    bbox = [min(xs) / width, max(xs) / width, min(ys) / height, max(ys) / height]
    occupancy = count / total
    intersects_central = bbox[1] >= 0.10 and bbox[0] <= 0.90 and bbox[3] >= 0.10 and bbox[2] <= 0.90
    return {
        "fluid_pixel_count": count,
        "fluid_occupancy": occupancy,
        "bbox_norm": [round(value, 5) for value in bbox],
        "bbox_intersects_central_80_percent": intersects_central,
        "occupancy_between_5_and_70_percent": 0.05 <= occupancy <= 0.70,
        "low_visibility_below_10_percent": occupancy < 0.10,
    }


def render_fluid_mask(
    output: Path,
    fluid_objects: list[bpy.types.Object],
    width: int,
    height: int,
) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    original = {
        "filepath": scene.render.filepath,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "samples": scene.cycles.samples,
        "world_color": tuple(scene.world.color),
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": scene.view_settings.exposure,
        "gamma": scene.view_settings.gamma,
    }
    original_materials = {obj.name: list(obj.data.materials) for obj in fluid_objects}
    original_hidden = {obj.name: obj.hide_render for obj in bpy.context.scene.objects}
    mask_material = fluid_mask_material()
    try:
        for obj in bpy.context.scene.objects:
            obj.hide_render = obj not in fluid_objects
        for obj in fluid_objects:
            obj.data.materials.clear()
            obj.data.materials.append(mask_material)
            obj.hide_render = False
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.cycles.samples = 1
        scene.world.color = (0.0, 0.0, 0.0)
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        return measure_mask(output, width, height)
    finally:
        for obj in bpy.context.scene.objects:
            if obj.name in original_hidden:
                obj.hide_render = original_hidden[obj.name]
        for obj in fluid_objects:
            obj.data.materials.clear()
            for material in original_materials.get(obj.name, []):
                obj.data.materials.append(material)
        scene.render.filepath = original["filepath"]
        scene.render.resolution_x = original["resolution_x"]
        scene.render.resolution_y = original["resolution_y"]
        scene.cycles.samples = original["samples"]
        scene.world.color = original["world_color"]
        scene.view_settings.view_transform = original["view_transform"]
        scene.view_settings.look = original["look"]
        scene.view_settings.exposure = original["exposure"]
        scene.view_settings.gamma = original["gamma"]


def raycast_fluid_visibility(camera: bpy.types.Object, fluid: bpy.types.Object, sample_count: int = 48) -> dict[str, object]:
    verts = [fluid.matrix_world @ vertex.co for vertex in fluid.data.vertices]
    if not verts:
        return {"sampled_points": 0, "wall_or_floor_first_hit_count": 0, "fluid_first_hit_count": 0}
    step = max(1, len(verts) // sample_count)
    sampled = verts[::step][:sample_count]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    wall_hits = 0
    fluid_hits = 0
    other_hits = 0
    for point in sampled:
        direction = point - camera.location
        if direction.length <= 1e-9:
            other_hits += 1
            continue
        hit, _, _, _, hit_obj, _ = bpy.context.scene.ray_cast(
            depsgraph, camera.location, direction.normalized(), distance=direction.length + 1e-6
        )
        if not hit or hit_obj is None:
            other_hits += 1
        elif hit_obj == fluid or hit_obj.name == fluid.name:
            fluid_hits += 1
        elif "wall" in hit_obj.name.lower() or "floor" in hit_obj.name.lower():
            wall_hits += 1
        else:
            other_hits += 1
    return {
        "sampled_points": len(sampled),
        "wall_or_floor_first_hit_count": wall_hits,
        "fluid_first_hit_count": fluid_hits,
        "other_first_hit_count": other_hits,
        "wall_or_floor_first_hit": wall_hits > 0,
    }


def render_still(path: Path) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    start = time.monotonic()
    bpy.ops.render.render(write_still=True)
    return time.monotonic() - start


def output_path(output_root: Path, mode: str, index: int) -> Path:
    return output_root / "frames" / mode / f"{mode}_{index:04d}.png"


def route_label(route_id: str) -> str:
    if "rectangular" in route_id:
        return "2:1 rectangular top-hat imposed-inlet comparison"
    return "Official circular control"


def add_inlet_for_route(route_id: str, bounds: Bounds, offset: Vector | None = None) -> None:
    if "rectangular" in route_id:
        add_rectangular_inlet(bounds, offset)
    else:
        add_round_inlet(bounds, offset)


def frame_record(render_index: int, frame: SurfaceFrame, output: Path, seconds: float) -> dict[str, object]:
    return {
        "render_frame": render_index,
        "surface_index": frame.index,
        "source_frame_id": frame.source_frame_id,
        "source_time": frame.time,
        "source_iteration": frame.iteration,
        "source_path": str(frame.path),
        "source_sha256": sha256_file(frame.path),
        "output_path": str(output),
        "render_seconds": round(seconds, 3),
        "facet_cell_count": frame.facet_cell_count,
        "topology_preserving_operations": "direct mesh import from output_facets(f); no smoothing, remeshing, decimation, or interpolation",
    }


def render_sequence(args: argparse.Namespace, frames: list[SurfaceFrame], device: dict[str, object]) -> dict[str, object]:
    sequence_bounds, per_frame_bounds = scan_sequence_bounds(frames)
    inlet_bounds = per_frame_bounds[frames[0].index]
    selected = frames[-1:] if args.mode == "smoke" else frames
    if args.max_frames > 0:
        selected = selected[: args.max_frames]
    records: list[dict[str, object]] = []
    title = args.overlay_title or route_label(args.primary_route_id)
    for render_index, frame in enumerate(selected):
        out = output_path(args.output_root, "smoke" if args.mode == "smoke" else "sequence", render_index)
        if args.start_at_first_missing and out.exists() and out.stat().st_size > 0:
            records.append(frame_record(render_index, frame, out, 0.0))
            continue
        clear_scene()
        verts, faces, meta = parse_facets(frame.path)
        water_color = (0.28, 0.74, 0.98, 1.0) if "rectangular" not in args.primary_route_id else (0.95, 0.58, 0.24, 1.0)
        water = water_material("clear_water_primary_route", water_color)
        add_mesh_object("vof_surface_primary", verts, faces, water)
        setup_scene(sequence_bounds)
        add_inlet_for_route(args.primary_route_id, inlet_bounds)
        camera = add_camera(sequence_bounds, "sequence")
        route_note = RECTANGULAR_TEXT if "rectangular" in args.primary_route_id else ROUND_TEXT
        add_camera_overlay(
            camera,
            title,
            [
                f"t={frame.time:.3f}; physical frame {frame.index:04d}; level {frame.maxlevel or 'n/a'}",
                route_note,
                args.persistent_caveat,
            ],
        )
        seconds = render_still(out)
        record = frame_record(render_index, frame, out, seconds)
        record["facet_metadata"] = meta
        records.append(record)
        print(f"RENDERED_{args.mode.upper()}_FRAME={render_index} SOURCE={frame.path}")
    return shot_manifest(args, "smoke" if args.mode == "smoke" else "sequence", selected, records, device)


def render_comparison(
    args: argparse.Namespace,
    primary_frames: list[SurfaceFrame],
    comparison_frames: list[SurfaceFrame],
    device: dict[str, object],
) -> dict[str, object]:
    primary_bounds, primary_frame_bounds = scan_sequence_bounds(primary_frames)
    comparison_bounds, comparison_frame_bounds = scan_sequence_bounds(comparison_frames)
    primary_inlet_bounds = primary_frame_bounds[primary_frames[0].index]
    comparison_inlet_bounds = comparison_frame_bounds[comparison_frames[0].index]
    second_by_time = {round(frame.time, 6): frame for frame in comparison_frames}
    pairs = [(frame, second_by_time[round(frame.time, 6)]) for frame in primary_frames if round(frame.time, 6) in second_by_time]
    if args.max_frames > 0:
        pairs = pairs[: args.max_frames]
    sep = max(primary_bounds.span, comparison_bounds.span) * 0.95
    combined = combine_bounds(
        [
            Bounds(primary_bounds.mins + Vector((0.0, -sep, 0.0)), primary_bounds.maxs + Vector((0.0, -sep, 0.0))),
            Bounds(comparison_bounds.mins + Vector((0.0, sep, 0.0)), comparison_bounds.maxs + Vector((0.0, sep, 0.0))),
        ]
    )
    records: list[dict[str, object]] = []
    for render_index, (left, right) in enumerate(pairs):
        out = output_path(args.output_root, "comparison", render_index)
        if args.start_at_first_missing and out.exists() and out.stat().st_size > 0:
            record = frame_record(render_index, left, out, 0.0)
            record["second_source_frame_id"] = right.source_frame_id
            records.append(record)
            continue
        clear_scene()
        verts_l, faces_l, _ = parse_facets(left.path)
        verts_r, faces_r, _ = parse_facets(right.path)
        add_mesh_object("official_round_control_surface", verts_l, faces_l, water_material("round_water_blue", (0.32, 0.66, 0.94, 1.0)), Vector((0.0, -sep, 0.0)))
        add_mesh_object("rectangular_imposed_inlet_surface", verts_r, faces_r, water_material("rect_water_gold", (0.92, 0.58, 0.28, 1.0)), Vector((0.0, sep, 0.0)))
        setup_scene(combined, y_expand=2.1)
        add_inlet_for_route(args.primary_route_id, primary_inlet_bounds, Vector((0.0, -sep, 0.0)))
        add_inlet_for_route(args.comparison_route_id, comparison_inlet_bounds, Vector((0.0, sep, 0.0)))
        camera = add_camera(combined, "sequence")
        add_camera_overlay(
            camera,
            "Official circular control vs rectangular top-hat imposed inlet",
            [
                f"exact physical-time pair; t={left.time:.3f}; frame {left.index:04d}",
                "left: official circular control; right: 2:1 rectangular top-hat imposed inlet",
                "rectangular velocity is imposed at the inlet plane; internal nozzle flow is not resolved",
            ],
        )
        seconds = render_still(out)
        record = frame_record(render_index, left, out, seconds)
        record["second_source_frame_id"] = right.source_frame_id
        record["second_source_time"] = right.time
        record["second_source_path"] = str(right.path)
        record["second_source_sha256"] = sha256_file(right.path)
        record["second_facet_cell_count"] = right.facet_cell_count
        records.append(record)
        print(f"RENDERED_COMPARISON_FRAME={render_index} L={left.path} R={right.path}")
    result = shot_manifest(args, "comparison", [pair[0] for pair in pairs], records, device)
    result["exact_time_pair_count"] = len(pairs)
    return result


def projected_visibility(camera: bpy.types.Object, objects: list[bpy.types.Object]) -> dict[str, object]:
    scene = bpy.context.scene
    coords: list[Vector] = []
    for obj in objects:
        coords.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    projected = [world_to_camera_view(scene, camera, coord) for coord in coords]
    min_x = min(point.x for point in projected)
    max_x = max(point.x for point in projected)
    min_y = min(point.y for point in projected)
    max_y = max(point.y for point in projected)
    min_z = min(point.z for point in projected)
    target = sum(coords, Vector((0.0, 0.0, 0.0))) / len(coords)
    direction = target - camera.location
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, _, _, _, hit_obj, _ = scene.ray_cast(depsgraph, camera.location, direction.normalized(), distance=direction.length)
    return {
        "projected_bounds": [round(min_x, 4), round(max_x, 4), round(min_y, 4), round(max_y, 4)],
        "min_camera_depth": round(min_z, 4),
        "partly_in_frame": max_x > 0.05 and min_x < 0.95 and max_y > 0.05 and min_y < 0.95 and min_z > 0,
        "fills_entire_frame": min_x < -0.10 and max_x > 1.10 and min_y < -0.10 and max_y > 1.10,
        "raycast_hit": bool(hit),
        "raycast_hit_object": hit_obj.name if hit_obj else "",
    }


def render_flythrough(args: argparse.Namespace, frames: list[SurfaceFrame], device: dict[str, object]) -> dict[str, object]:
    sequence_bounds, per_frame_bounds = scan_sequence_bounds(frames)
    inlet_bounds = per_frame_bounds[frames[0].index]
    if args.hero_surface_index >= 0:
        selected = next((frame for frame in frames if frame.index == args.hero_surface_index), None)
        if selected is None:
            raise SystemExit(f"ERROR: hero surface index {args.hero_surface_index} not present in manifest")
    else:
        selected = frames[-1]
    verts, faces, meta = parse_facets(selected.path)
    records: list[dict[str, object]] = []
    visibility: list[dict[str, object]] = []
    frame_total = args.flythrough_frames
    low_visibility_run = 0
    max_low_visibility_run = 0
    for render_index in range(frame_total):
        out = output_path(args.output_root, "flythrough", render_index)
        if args.start_at_first_missing and out.exists() and out.stat().st_size > 0:
            continue
        clear_scene()
        water = water_material("final_complex_clear_water", (0.34, 0.68, 0.95, 1.0))
        obj = add_mesh_object("vof_surface_final_complex_static", verts, faces, water)
        setup_scene(sequence_bounds, include_walls=not args.open_studio)
        add_inlet_for_route(args.primary_route_id, inlet_bounds)
        camera = add_camera(sequence_bounds, "flythrough", render_index, frame_total)
        add_camera_overlay(
            camera,
            "Safe-frame complex geometry flythrough",
            [
                f"static solver frame {selected.index:04d}; t={selected.time:.3f}; cinematic camera path",
                ROUND_TEXT if "rectangular" not in args.primary_route_id else RECTANGULAR_TEXT,
                "camera remains external; no probe or extra solver states implied",
            ],
        )
        check = projected_visibility(camera, [obj])
        mask_path = (args.mask_output_root or (args.output_root / "masks")) / f"flythrough_mask_{render_index:04d}.png"
        mask = render_fluid_mask(mask_path, [obj], args.mask_resolution_x, args.mask_resolution_y)
        raycast = raycast_fluid_visibility(camera, obj)
        check["render_frame"] = render_index
        check["mask_path"] = str(mask_path)
        check.update(mask)
        check.update(raycast)
        check["visibility_frame_passed"] = (
            bool(check["occupancy_between_5_and_70_percent"])
            and bool(check["bbox_intersects_central_80_percent"])
            and not bool(check["wall_or_floor_first_hit"])
        )
        if check["low_visibility_below_10_percent"]:
            low_visibility_run += 1
        else:
            low_visibility_run = 0
        max_low_visibility_run = max(max_low_visibility_run, low_visibility_run)
        visibility.append(check)
        seconds = render_still(out)
        records.append(frame_record(render_index, selected, out, seconds))
        print(
            "RENDERED_FLYTHROUGH_FRAME="
            f"{render_index} SOURCE={selected.path} OCCUPANCY={check['fluid_occupancy']:.4f} "
            f"PASS={check['visibility_frame_passed']}"
        )
    result = shot_manifest(args, "flythrough", [selected], records, device)
    result["static_source_frame"] = selected.source_frame_id
    result["static_source_time"] = selected.time
    result["static_source_index"] = selected.index
    result["camera_path"] = "curved external orbit/approach with streamwise travel and final hero composition"
    result["visibility_checks"] = visibility
    result["visibility_passed"] = all(item["visibility_frame_passed"] for item in visibility) and max_low_visibility_run <= 5
    result["maximum_consecutive_low_visibility_frames"] = max_low_visibility_run
    result["visibility_thresholds"] = {
        "fluid_occupancy_min": 0.05,
        "fluid_occupancy_max": 0.70,
        "central_frame_region": [0.10, 0.90, 0.10, 0.90],
        "maximum_consecutive_frames_below_10_percent_occupancy": 5,
        "wall_or_floor_first_hit_allowed": False,
    }
    result["raycast_checked"] = True
    result["facet_metadata"] = meta
    return result


def render_multiview(args: argparse.Namespace, frames: list[SurfaceFrame], device: dict[str, object]) -> dict[str, object]:
    sequence_bounds, per_frame_bounds = scan_sequence_bounds(frames)
    inlet_bounds = per_frame_bounds[frames[0].index]
    final = frames[-1]
    verts, faces, meta = parse_facets(final.path)
    records: list[dict[str, object]] = []
    for render_index, preset in enumerate(["sequence", "profile", "top"]):
        out = output_path(args.output_root, "multiview", render_index)
        clear_scene()
        obj = add_mesh_object("vof_surface_multiview_final", verts, faces, water_material("multiview_clear_water", (0.34, 0.68, 0.95, 1.0)))
        setup_scene(sequence_bounds)
        add_inlet_for_route(args.primary_route_id, inlet_bounds)
        camera = add_camera(sequence_bounds, preset)
        add_camera_overlay(
            camera,
            f"Final complex geometry: {preset} view",
            [
                f"static solver frame {final.index:04d}; t={final.time:.3f}",
                ROUND_TEXT if "rectangular" not in args.primary_route_id else RECTANGULAR_TEXT,
                args.persistent_caveat,
            ],
        )
        seconds = render_still(out)
        record = frame_record(render_index, final, out, seconds)
        record["camera_preset"] = preset
        record["visibility"] = projected_visibility(camera, [obj])
        records.append(record)
        print(f"RENDERED_MULTIVIEW_FRAME={render_index} PRESET={preset}")
    result = shot_manifest(args, "multiview", [final], records, device)
    result["facet_metadata"] = meta
    return result


def shot_manifest(
    args: argparse.Namespace,
    shot: str,
    physical_frames: list[SurfaceFrame],
    records: list[dict[str, object]],
    device: dict[str, object],
) -> dict[str, object]:
    return {
        "shot": shot,
        "primary_manifest": str(args.primary_manifest),
        "primary_surface_root": str(args.primary_surface_root),
        "primary_route_id": args.primary_route_id,
        "comparison_manifest": str(args.comparison_manifest) if args.comparison_manifest else "",
        "comparison_surface_root": str(args.comparison_surface_root) if args.comparison_surface_root else "",
        "comparison_route_id": args.comparison_route_id,
        "route_manifest": str(args.route_manifest) if args.route_manifest else "",
        "media_manifest": str(args.media_manifest) if args.media_manifest else "",
        "physical_frame_count": len(physical_frames),
        "render_frame_count": len(records),
        "all_primary_physical_frames_included": shot != "sequence" or len(records) == len(physical_frames),
        "presentation_interpolation_used": False,
        "render_holds_used": False,
        "device": device,
        "fps": args.fps,
        "samples": device.get("samples"),
        "resolution": device.get("resolution"),
        "renderer": "Cycles",
        "liquid_material": {
            "ior": 1.333,
            "transmission": 0.58,
            "roughness": 0.035,
            "alpha_policy": "opaque alpha with transmission/refraction; not made invisible",
        },
        "topology_preserving_operations": "direct mesh import from Basilisk output_facets(f); no smoothing, remeshing, decimation, boolean cleanup, or generated solver frames",
        "overlay_policy": "camera-space 2D review panels with dark backing; no labels laid across geometry",
        "claim_boundary": {
            "fit_ready": False,
            "public_ready": False,
            "portfolio_candidate_requires_human_review": True,
        },
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
                    "facet_cell_count",
                    "topology_preserving_operations",
                ],
            )
            writer.writeheader()
            for record in result.get("records", []):
                writer.writerow({key: record.get(key, "") for key in writer.fieldnames})


def main() -> None:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    _, primary_frames = load_surface_manifest(args.primary_manifest, args.primary_surface_root)
    device = configure_cycles(args)
    if args.mode in {"smoke", "sequence"}:
        result = render_sequence(args, primary_frames, device)
    elif args.mode == "comparison":
        if not args.comparison_manifest or not args.comparison_surface_root:
            raise SystemExit("ERROR: comparison mode requires comparison manifest/root")
        _, comparison_frames = load_surface_manifest(args.comparison_manifest, args.comparison_surface_root)
        result = render_comparison(args, primary_frames, comparison_frames, device)
    elif args.mode == "flythrough":
        result = render_flythrough(args, primary_frames, device)
    elif args.mode == "multiview":
        result = render_multiview(args, primary_frames, device)
    else:
        raise SystemExit(f"ERROR: unsupported mode {args.mode}")
    write_outputs(result, args)
    print(f"BLENDER_RECTANGULAR_ATOMISATION_MANIFEST={args.manifest_out}")


if __name__ == "__main__":
    main()
