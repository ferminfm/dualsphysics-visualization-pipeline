"""Render tiny Basilisk 3D VOF point-cloud frames in headless Blender.

Input files are legacy VTK POLYDATA point clouds produced by
scripts/run_basilisk_jet_showcase.py. The renderer creates still PNG frames;
assemble MP4/contact sheets outside Blender with ffmpeg.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--vtk-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=720)
    parser.add_argument("--samples", type=int, default=48)
    parser.add_argument("--particle-radius", type=float, default=0.0025)
    parser.add_argument(
        "--caption",
        default="",
    )
    args = parser.parse_args(argv)
    if args.vtk_dir is None and os.environ.get("BASILISK_SHOWCASE_VTK_DIR"):
        args.vtk_dir = Path(os.environ["BASILISK_SHOWCASE_VTK_DIR"])
    if args.output_dir is None and os.environ.get("BASILISK_SHOWCASE_OUTPUT_DIR"):
        args.output_dir = Path(os.environ["BASILISK_SHOWCASE_OUTPUT_DIR"])
    if args.vtk_dir is None or args.output_dir is None:
        parser.error(
            "--vtk-dir and --output-dir are required, or set "
            "BASILISK_SHOWCASE_VTK_DIR and BASILISK_SHOWCASE_OUTPUT_DIR"
        )
    return args


def parse_vtk_points(path: Path) -> tuple[list[tuple[float, float, float]], list[float]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    points: list[tuple[float, float, float]] = []
    scalars: list[float] = []
    idx = 0
    while idx < len(lines):
        parts = lines[idx].split()
        if parts and parts[0].upper() == "POINTS":
            count = int(parts[1])
            idx += 1
            while len(points) < count and idx < len(lines):
                values = [float(value) for value in lines[idx].split()]
                for pos in range(0, len(values), 3):
                    if pos + 2 < len(values):
                        points.append((values[pos], values[pos + 1], values[pos + 2]))
                idx += 1
            continue
        if len(parts) >= 2 and parts[0].upper() == "SCALARS" and parts[1] == "f":
            idx += 2
            while len(scalars) < len(points) and idx < len(lines):
                if not lines[idx].strip():
                    idx += 1
                    continue
                if lines[idx].split()[0].isalpha():
                    break
                scalars.extend(float(value) for value in lines[idx].split())
                idx += 1
            continue
        idx += 1
    if len(scalars) < len(points):
        scalars.extend([1.0] * (len(points) - len(scalars)))
    return points, scalars[: len(points)]


def make_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Alpha"].default_value = color[3]
    if "Roughness" in shader.inputs:
        shader.inputs["Roughness"].default_value = 0.32
    if "Specular IOR Level" in shader.inputs:
        shader.inputs["Specular IOR Level"].default_value = 0.22
    material.blend_method = "BLEND" if color[3] < 0.99 else "OPAQUE"
    material.use_screen_refraction = False
    return material


def add_octa_cloud(
    points: list[tuple[float, float, float]],
    scalars: list[float],
    radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    marker_faces = [
        (0, 2, 4),
        (2, 1, 4),
        (1, 3, 4),
        (3, 0, 4),
        (2, 0, 5),
        (1, 2, 5),
        (3, 1, 5),
        (0, 3, 5),
    ]
    for point, scalar in zip(points, scalars):
        local_radius = radius * (0.6 + 0.7 * max(0.0, min(1.0, scalar)))
        marker = [
            (local_radius, 0.0, 0.0),
            (-local_radius, 0.0, 0.0),
            (0.0, local_radius, 0.0),
            (0.0, -local_radius, 0.0),
            (0.0, 0.0, local_radius),
            (0.0, 0.0, -local_radius),
        ]
        base = len(verts)
        verts.extend((point[0] + dx, point[1] + dy, point[2] + dz) for dx, dy, dz in marker)
        faces.extend((base + a, base + b, base + c) for a, b, c in marker_faces)

    mesh = bpy.data.meshes.new("basilisk_vof_points")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("basilisk_vof_points", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_label(text: str, location: tuple[float, float, float], size: float) -> None:
    curve = bpy.data.curves.new("caption", "FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "LEFT"
    obj = bpy.data.objects.new("caption", curve)
    obj.location = location
    bpy.context.collection.objects.link(obj)


def add_scene_static(
    all_points: list[tuple[float, float, float]],
    caption: str,
) -> tuple[Vector, float, bpy.types.Material]:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    mins = Vector((
        min(point[0] for point in all_points),
        min(point[1] for point in all_points),
        min(point[2] for point in all_points),
    ))
    maxs = Vector((
        max(point[0] for point in all_points),
        max(point[1] for point in all_points),
        max(point[2] for point in all_points),
    ))
    center = (mins + maxs) * 0.5
    span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, 1e-6)

    jet_material = make_material("vof_water_blue", (0.05, 0.34, 0.90, 1.0))
    nozzle_material = make_material("nozzle_dark_matte", (0.08, 0.09, 0.11, 1.0))

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48,
        radius=span * 0.035,
        depth=span * 0.035,
        location=(mins.x - span * 0.035, 0.0, 0.0),
        rotation=(0.0, math.radians(90.0), 0.0),
    )
    nozzle = bpy.context.object
    nozzle.name = "inlet_nozzle_marker"
    nozzle.data.materials.append(nozzle_material)

    if caption:
        add_label(caption, (mins.x, mins.y - span * 0.18, maxs.z + span * 0.08), span * 0.045)

    bpy.ops.object.light_add(type="AREA", location=center + Vector((span * 0.5, -span * 1.4, span * 1.8)))
    light = bpy.context.object
    light.name = "large_softbox"
    light.data.energy = 650
    light.data.size = span * 1.6

    bpy.ops.object.camera_add(location=center + Vector((span * 1.4, -span * 2.4, span * 1.15)))
    camera = bpy.context.object
    look_at(camera, center)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = span * 1.85
    bpy.context.scene.camera = camera

    return center, span, jet_material


def main() -> None:
    args = parse_args()
    vtk_paths = sorted(args.vtk_dir.glob("*.vtk"))
    if not vtk_paths:
        raise SystemExit(f"ERROR no VTK frames found under {args.vtk_dir}")

    frames = [parse_vtk_points(path) for path in vtk_paths]
    all_points = [point for points, _ in frames for point in points]
    if not all_points:
        raise SystemExit("ERROR VTK frames have no points")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _, span, material = add_scene_static(all_points, args.caption)
    radius = args.particle_radius if args.particle_radius > 0.0 else span * 0.012

    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    bpy.context.scene.eevee.taa_render_samples = args.samples
    if hasattr(bpy.context.scene.eevee, "use_gtao"):
        bpy.context.scene.eevee.use_gtao = True
    bpy.context.scene.render.resolution_x = args.resolution_x
    bpy.context.scene.render.resolution_y = args.resolution_y
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.world.color = (0.018, 0.022, 0.028)

    cloud_obj: bpy.types.Object | None = None
    for index, (path, (points, scalars)) in enumerate(zip(vtk_paths, frames)):
        if cloud_obj is not None:
            bpy.data.objects.remove(cloud_obj, do_unlink=True)
        cloud_obj = add_octa_cloud(points, scalars, radius, material)
        bpy.context.scene.render.filepath = str(args.output_dir / f"basilisk_jet_showcase_{index:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"RENDERED_FRAME={index} INPUT={path} POINTS={len(points)}")

    print(f"RENDER_OUTPUT_DIR={args.output_dir}")


if __name__ == "__main__":
    main()
