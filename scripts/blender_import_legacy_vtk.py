"""Render a small DualSPHysics VTK fallback preview directly in Blender.

This is a narrow, dependency-free fallback path for legacy VTK POLYDATA files
exported by DualSPHysics tools. It handles ASCII or BINARY VTK files containing:

- POINTS
- optional triangular POLYGONS
- simple SCALARS or VECTORS in POINT_DATA

Run with portable Blender:

    blender --background --python scripts/blender_import_legacy_vtk.py -- \
      --fluid path/to/fluid.vtk \
      --boundary path/to/boundary.vtk \
      --iso path/to/iso.vtk \
      --output preview.png
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

import bpy
from mathutils import Vector


DEFAULT_FLUID_COLOR = (0.1, 0.45, 0.95, 0.9)
DEFAULT_BOUNDARY_COLOR = (0.52, 0.52, 0.5, 1.0)
DEFAULT_ISO_COLOR = (0.18, 0.65, 0.95, 0.42)
DEFAULT_BACKGROUND_COLOR = (0.03, 0.035, 0.04)


@dataclass
class VtkPolyData:
    points: list[tuple[float, float, float]] = field(default_factory=list)
    polygons: list[tuple[int, int, int]] = field(default_factory=list)
    point_scalars: dict[str, list[float | int | tuple[float, ...]]] = field(
        default_factory=dict
    )


def _read_line(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\n", offset)
    if end < 0:
        return data[offset:].decode("ascii", errors="replace"), len(data)
    return data[offset:end].decode("ascii", errors="replace"), end + 1


def _skip_ws(data: bytes, offset: int) -> int:
    while offset < len(data) and chr(data[offset]).isspace():
        offset += 1
    return offset


def _read_ascii_values(data: bytes, offset: int, count: int, cast=float) -> tuple[list, int]:
    values = []
    while len(values) < count and offset < len(data):
        offset = _skip_ws(data, offset)
        start = offset
        while offset < len(data) and not chr(data[offset]).isspace():
            offset += 1
        if start < offset:
            values.append(cast(data[start:offset].decode("ascii")))
    return values, offset


def _fmt_count(fmt_char: str, values: int) -> str:
    return f">{values}{fmt_char}"


def _vtk_type(type_name: str) -> tuple[str, int, type]:
    name = type_name.lower()
    if name in {"float", "float32"}:
        return "f", 4, float
    if name in {"double", "float64"}:
        return "d", 8, float
    if name in {"int", "unsigned_int"}:
        return "i" if name == "int" else "I", 4, int
    if name in {"short", "unsigned_short"}:
        return "h" if name == "short" else "H", 2, int
    if name in {"char", "unsigned_char"}:
        return "b" if name == "char" else "B", 1, int
    raise ValueError(f"unsupported VTK data type: {type_name}")


def _read_numeric_block(
    data: bytes,
    offset: int,
    count: int,
    type_name: str,
    binary: bool,
) -> tuple[list, int]:
    fmt_char, size, cast = _vtk_type(type_name)
    offset = _skip_ws(data, offset)
    if not binary:
        return _read_ascii_values(data, offset, count, cast=cast)

    byte_count = count * size
    raw = data[offset : offset + byte_count]
    if len(raw) != byte_count:
        raise ValueError("truncated VTK numeric block")
    values = list(struct.unpack(_fmt_count(fmt_char, count), raw))
    return values, offset + byte_count


def parse_legacy_vtk(path: Path) -> VtkPolyData:
    data = path.read_bytes()
    poly = VtkPolyData()
    offset = 0
    binary = False
    point_data_count = 0

    while offset < len(data):
        offset = _skip_ws(data, offset)
        line_start = offset
        line, offset = _read_line(data, offset)
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        key = parts[0].upper()

        if key == "BINARY":
            binary = True
        elif key == "ASCII":
            binary = False
        elif key == "POINTS":
            npoints = int(parts[1])
            dtype = parts[2]
            values, offset = _read_numeric_block(data, offset, npoints * 3, dtype, binary)
            poly.points = [
                (float(values[i]), float(values[i + 1]), float(values[i + 2]))
                for i in range(0, len(values), 3)
            ]
        elif key == "POLYGONS":
            npolys = int(parts[1])
            total_ints = int(parts[2])
            values, offset = _read_numeric_block(data, offset, total_ints, "int", binary)
            pos = 0
            polygons: list[tuple[int, int, int]] = []
            for _ in range(npolys):
                width = int(values[pos])
                ids = values[pos + 1 : pos + 1 + width]
                if width == 3:
                    polygons.append((int(ids[0]), int(ids[1]), int(ids[2])))
                pos += 1 + width
            poly.polygons = polygons
        elif key == "POINT_DATA":
            point_data_count = int(parts[1])
        elif key == "SCALARS":
            if point_data_count <= 0:
                continue
            name = parts[1]
            dtype = parts[2]
            components = int(parts[3]) if len(parts) > 3 else 1
            lookup, offset = _read_line(data, offset)
            if not lookup.upper().startswith("LOOKUP_TABLE"):
                offset = line_start
                continue
            values, offset = _read_numeric_block(
                data, offset, point_data_count * components, dtype, binary
            )
            if components == 1:
                poly.point_scalars[name] = values
            else:
                poly.point_scalars[name] = [
                    tuple(values[i : i + components])
                    for i in range(0, len(values), components)
                ]
        elif key == "VECTORS":
            if point_data_count <= 0:
                continue
            name = parts[1]
            dtype = parts[2]
            values, offset = _read_numeric_block(
                data, offset, point_data_count * 3, dtype, binary
            )
            poly.point_scalars[name] = [
                tuple(values[i : i + 3]) for i in range(0, len(values), 3)
            ]

    return poly


def _make_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
    material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.55
    material.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = color[3]
    material.blend_method = "BLEND"
    return material


def _parse_color(value: str) -> tuple[float, float, float, float]:
    """Parse '#RRGGBB[AA]' or comma-separated 0..1 RGBA values."""
    if value.startswith("#"):
        hex_value = value[1:]
        if len(hex_value) not in {6, 8}:
            raise argparse.ArgumentTypeError("hex colors must be #RRGGBB or #RRGGBBAA")
        channels = [
            int(hex_value[i : i + 2], 16) / 255.0
            for i in range(0, len(hex_value), 2)
        ]
        if len(channels) == 3:
            channels.append(1.0)
        return tuple(channels)  # type: ignore[return-value]

    try:
        channels = [float(part) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("colors must be #RRGGBB[AA] or r,g,b[,a]") from exc
    if len(channels) == 3:
        channels.append(1.0)
    if len(channels) != 4 or any(channel < 0.0 or channel > 1.0 for channel in channels):
        raise argparse.ArgumentTypeError("color channels must be three or four values in 0..1")
    return tuple(channels)  # type: ignore[return-value]


def _bounds(points: list[tuple[float, float, float]]) -> tuple[Vector, Vector]:
    mins = Vector((min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points)))
    maxs = Vector((max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points)))
    return mins, maxs


def _add_point_cloud(
    name: str,
    points: list[tuple[float, float, float]],
    material: bpy.types.Material,
    stride: int,
    particle_radius: float,
) -> bpy.types.Object:
    sampled = points[:: max(1, stride)]
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    marker = [
        (particle_radius, 0.0, 0.0),
        (-particle_radius, 0.0, 0.0),
        (0.0, particle_radius, 0.0),
        (0.0, -particle_radius, 0.0),
        (0.0, 0.0, particle_radius),
        (0.0, 0.0, -particle_radius),
    ]
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
    for point in sampled:
        base = len(verts)
        verts.extend(
            (point[0] + dx, point[1] + dy, point[2] + dz) for dx, dy, dz in marker
        )
        faces.extend((base + a, base + b, base + c) for a, b, c in marker_faces)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    obj["particle_radius_hint"] = particle_radius
    obj["sampled_points"] = len(sampled)
    return obj


def _add_surface(
    name: str,
    points: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    material: bpy.types.Material,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def _add_label(text: str, location: tuple[float, float, float]) -> None:
    font_curve = bpy.data.curves.new("label", "FONT")
    font_curve.body = text
    font_curve.size = 0.035
    font_curve.align_x = "LEFT"
    obj = bpy.data.objects.new("label", font_curve)
    obj.location = location
    bpy.context.collection.objects.link(obj)


def _parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--fluid", type=Path, required=True)
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--iso", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blend", type=Path)
    parser.add_argument("--fluid-stride", type=int, default=2)
    parser.add_argument("--boundary-stride", type=int, default=1)
    parser.add_argument("--marker-scale", type=float, default=1.0)
    parser.add_argument("--resolution", type=int, default=1200)
    parser.add_argument(
        "--camera-preset",
        choices=("isometric", "front", "side", "top", "close"),
        default="isometric",
    )
    parser.add_argument("--fluid-color", type=_parse_color, default=DEFAULT_FLUID_COLOR)
    parser.add_argument("--boundary-color", type=_parse_color, default=DEFAULT_BOUNDARY_COLOR)
    parser.add_argument("--iso-color", type=_parse_color, default=DEFAULT_ISO_COLOR)
    parser.add_argument("--background-color", type=_parse_color, default=DEFAULT_BACKGROUND_COLOR)
    parser.add_argument("--hide-iso", action="store_true")
    return parser.parse_args(argv)


def _camera_location(center: Vector, span: float, preset: str) -> tuple[float, float, float]:
    if preset == "front":
        return (center.x, center.y - span * 2.2, center.z + span * 0.2)
    if preset == "side":
        return (center.x + span * 2.0, center.y, center.z + span * 0.25)
    if preset == "top":
        return (center.x, center.y - span * 0.05, center.z + span * 2.4)
    if preset == "close":
        return (center.x + span * 0.55, center.y - span * 1.15, center.z + span * 0.5)
    return (center.x + span * 0.9, center.y - span * 1.7, center.z + span * 0.65)


def main() -> None:
    args = _parse_args()
    for path in [args.fluid, args.boundary, args.iso]:
        if path and not path.exists():
            raise SystemExit(f"ERROR: missing input VTK: {path}")

    print(f"BLENDER_VERSION={bpy.app.version_string}")
    print(f"FLUID_VTK={args.fluid}")
    fluid = parse_legacy_vtk(args.fluid)
    print(f"FLUID_POINTS={len(fluid.points)}")

    boundary = None
    if args.boundary:
        print(f"BOUNDARY_VTK={args.boundary}")
        boundary = parse_legacy_vtk(args.boundary)
        print(f"BOUNDARY_POINTS={len(boundary.points)}")

    iso = None
    if args.iso:
        print(f"ISO_VTK={args.iso}")
        iso = parse_legacy_vtk(args.iso)
        print(f"ISO_POINTS={len(iso.points)} ISO_POLYGONS={len(iso.polygons)}")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    fluid_mat = _make_material("fluid_water_blue", args.fluid_color)
    boundary_mat = _make_material("boundary_neutral", args.boundary_color)
    iso_mat = _make_material("surface_translucent", args.iso_color)

    all_points = list(fluid.points)
    if boundary:
        all_points.extend(boundary.points)
    if iso and iso.points:
        all_points.extend(iso.points)
    mins, maxs = _bounds(all_points)
    span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, 1e-6)
    center = (mins + maxs) * 0.5
    radius = span * 0.006 * args.marker_scale

    if iso and iso.polygons and not args.hide_iso:
        surface = _add_surface("dambreak_isosurface", iso.points, iso.polygons, iso_mat)
        surface.show_transparent = True

    _add_point_cloud(
        "dambreak_fluid_points",
        fluid.points,
        fluid_mat,
        args.fluid_stride,
        radius,
    )
    if boundary:
        _add_point_cloud(
            "dambreak_boundary_points",
            boundary.points,
            boundary_mat,
            args.boundary_stride,
            radius * 0.8,
        )

    _add_label("DualSPHysics dam-break VTK fallback", (mins.x, mins.y - span * 0.08, maxs.z))

    bpy.ops.object.light_add(type="AREA", location=(center.x, center.y - span, center.z + span))
    light = bpy.context.object
    light.name = "large_softbox"
    light.data.energy = 450
    light.data.size = span * 1.2

    bpy.ops.object.camera_add(location=_camera_location(center, span, args.camera_preset))
    camera = bpy.context.object
    direction = center - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 55
    bpy.context.scene.camera = camera

    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    bpy.context.scene.eevee.taa_render_samples = 32
    bpy.context.scene.render.resolution_x = args.resolution
    bpy.context.scene.render.resolution_y = int(args.resolution * 0.7)
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.world.color = args.background_color[:3]

    print(f"CAMERA_PRESET={args.camera_preset}")
    print(f"FLUID_STRIDE={args.fluid_stride}")
    print(f"BOUNDARY_STRIDE={args.boundary_stride}")
    print(f"MARKER_SCALE={args.marker_scale}")
    print(f"ISO_VISIBLE={bool(iso and iso.polygons and not args.hide_iso)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.blend:
        args.blend.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(args.blend))
        print(f"BLEND_PATH={args.blend}")

    bpy.context.scene.render.filepath = str(args.output)
    bpy.ops.render.render(write_still=True)
    print(f"PNG_PATH={args.output}")


if __name__ == "__main__":
    main()
