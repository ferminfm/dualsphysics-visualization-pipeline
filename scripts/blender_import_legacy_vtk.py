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


DEFAULT_FLUID_COLOR = (0.18, 0.58, 0.95, 0.82)
DEFAULT_BOUNDARY_COLOR = (0.72, 0.70, 0.66, 1.0)
DEFAULT_ISO_COLOR = (0.36, 0.78, 1.0, 0.34)
DEFAULT_BACKGROUND_COLOR = (0.018, 0.022, 0.028)
DEFAULT_CAPTION = "DualSPHysics dam-break VTK fallback"


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
        elif key == "FIELD":
            arrays = int(parts[2]) if len(parts) > 2 else 0
            for _ in range(arrays):
                field_line, offset = _read_line(data, offset)
                field_parts = field_line.split()
                if len(field_parts) < 4:
                    continue
                name = field_parts[0]
                components = int(field_parts[1])
                tuples = int(field_parts[2])
                dtype = field_parts[3]
                values, offset = _read_numeric_block(
                    data, offset, components * tuples, dtype, binary
                )
                if components == 1:
                    poly.point_scalars[name] = values
                else:
                    poly.point_scalars[name] = [
                        tuple(values[i : i + components])
                        for i in range(0, len(values), components)
                    ]

    return poly


def _set_socket(node: bpy.types.Node, names: tuple[str, ...], value: float) -> None:
    for name in names:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return


def _make_material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    roughness: float = 0.45,
    metallic: float = 0.0,
    specular: float = 0.5,
    transmission: float = 0.0,
    ior: float = 1.333,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Alpha"].default_value = color[3]
    _set_socket(shader, ("Roughness",), roughness)
    _set_socket(shader, ("Metallic",), metallic)
    _set_socket(shader, ("Specular IOR Level", "Specular"), specular)
    _set_socket(shader, ("Transmission Weight", "Transmission"), transmission)
    _set_socket(shader, ("IOR",), ior)
    material.blend_method = "BLEND"
    material.use_screen_refraction = True
    material.show_transparent_back = True
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


def _parse_vector3(value: str) -> tuple[float, float, float]:
    try:
        parts = [float(part) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("vectors must be x,y,z") from exc
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("vectors must contain exactly three values")
    return tuple(parts)  # type: ignore[return-value]


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
    marker_style: str,
) -> bpy.types.Object:
    sampled = points[:: max(1, stride)]
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    if marker_style == "icosahedron":
        phi = (1.0 + math.sqrt(5.0)) / 2.0
        raw_marker = [
            (-1.0, phi, 0.0),
            (1.0, phi, 0.0),
            (-1.0, -phi, 0.0),
            (1.0, -phi, 0.0),
            (0.0, -1.0, phi),
            (0.0, 1.0, phi),
            (0.0, -1.0, -phi),
            (0.0, 1.0, -phi),
            (phi, 0.0, -1.0),
            (phi, 0.0, 1.0),
            (-phi, 0.0, -1.0),
            (-phi, 0.0, 1.0),
        ]
        marker = [
            tuple((Vector(point).normalized() * particle_radius))
            for point in raw_marker
        ]
        marker_faces = [
            (0, 11, 5),
            (0, 5, 1),
            (0, 1, 7),
            (0, 7, 10),
            (0, 10, 11),
            (1, 5, 9),
            (5, 11, 4),
            (11, 10, 2),
            (10, 7, 6),
            (7, 1, 8),
            (3, 9, 4),
            (3, 4, 2),
            (3, 2, 6),
            (3, 6, 8),
            (3, 8, 9),
            (4, 9, 5),
            (2, 4, 11),
            (6, 2, 10),
            (8, 6, 7),
            (9, 8, 1),
        ]
    else:
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
    if marker_style == "icosahedron":
        for polygon in mesh.polygons:
            polygon.use_smooth = True
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    obj["particle_radius_hint"] = particle_radius
    obj["sampled_points"] = len(sampled)
    return obj


def _magnitude(value: float | int | tuple[float, ...]) -> float:
    if isinstance(value, tuple):
        return math.sqrt(sum(float(component) ** 2 for component in value))
    return float(value)


def _heat_color(t: float) -> tuple[float, float, float, float]:
    stops = (
        (0.06, 0.16, 0.55),
        (0.00, 0.62, 0.95),
        (0.55, 0.92, 0.55),
        (1.00, 0.78, 0.18),
        (0.95, 0.20, 0.12),
    )
    t = min(1.0, max(0.0, t))
    scaled = t * (len(stops) - 1)
    low = min(len(stops) - 2, int(math.floor(scaled)))
    frac = scaled - low
    color = tuple(
        stops[low][i] * (1.0 - frac) + stops[low + 1][i] * frac
        for i in range(3)
    )
    return (color[0], color[1], color[2], 0.96)


def _add_colored_point_cloud(
    points: list[tuple[float, float, float]],
    values: list[float],
    stride: int,
    particle_radius: float,
    marker_style: str,
    bins: int,
    value_min: float | None = None,
    value_max: float | None = None,
) -> tuple[float, float]:
    sampled_points = points[:: max(1, stride)]
    sampled_values = values[:: max(1, stride)]
    if not sampled_points or not sampled_values:
        raise SystemExit("ERROR: no sampled points available for color mapping")
    vmin = min(sampled_values) if value_min is None else value_min
    vmax = max(sampled_values) if value_max is None else value_max
    if not math.isfinite(vmin) or not math.isfinite(vmax) or vmax <= vmin:
        raise SystemExit("ERROR: invalid color mapping range")

    bucket_count = max(2, bins)
    buckets: list[list[tuple[float, float, float]]] = [[] for _ in range(bucket_count)]
    for point, value in zip(sampled_points, sampled_values, strict=False):
        normalized = (value - vmin) / (vmax - vmin)
        index = min(bucket_count - 1, max(0, int(normalized * bucket_count)))
        buckets[index].append(point)

    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        material = _make_material(
            f"analysis_heat_bin_{index:02d}",
            _heat_color(index / max(1, bucket_count - 1)),
            roughness=0.22,
            specular=0.68,
        )
        _add_point_cloud(
            f"analysis_points_bin_{index:02d}",
            bucket,
            material,
            1,
            particle_radius,
            marker_style,
        )
    return vmin, vmax


def _add_surface(
    name: str,
    points: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    material: bpy.types.Material,
    *,
    smoothing: str = "none",
    smooth_factor: float = 0.25,
    smooth_iterations: int = 1,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], faces)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    if smoothing in {"smooth", "smooth-weighted"}:
        modifier = obj.modifiers.new("benchmark_surface_smooth", "SMOOTH")
        modifier.factor = smooth_factor
        modifier.iterations = max(1, smooth_iterations)
    if smoothing in {"weighted-normal", "smooth-weighted"}:
        obj.modifiers.new("benchmark_weighted_normals", "WEIGHTED_NORMAL")
    return obj


def _add_floor(
    center: Vector,
    span: float,
    z_value: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    size = span * 1.35
    y_size = span * 0.45
    verts = [
        (center.x - size * 0.55, center.y - y_size, z_value),
        (center.x + size * 0.55, center.y - y_size, z_value),
        (center.x + size * 0.55, center.y + y_size, z_value),
        (center.x - size * 0.55, center.y + y_size, z_value),
    ]
    mesh = bpy.data.meshes.new("studio_floor_mesh")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new("studio_floor", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def _add_box(
    name: str,
    min_corner: tuple[float, float, float],
    max_corner: tuple[float, float, float],
    material: bpy.types.Material,
) -> bpy.types.Object:
    x0, y0, z0 = min_corner
    x1, y1, z1 = max_corner
    verts = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def _add_floor_grid(
    center: Vector,
    span: float,
    mins: Vector,
    maxs: Vector,
    material: bpy.types.Material,
) -> None:
    z = mins.z - span * 0.044
    x0 = center.x - span * 0.62
    x1 = center.x + span * 0.62
    y0 = center.y - span * 0.30
    y1 = center.y + span * 0.30
    thickness = span * 0.0012
    divisions = 6
    for index in range(divisions + 1):
        t = index / divisions
        x = x0 + (x1 - x0) * t
        _add_box(
            f"floor_grid_x_{index:02d}",
            (x - thickness, y0, z),
            (x + thickness, y1, z + thickness),
            material,
        )
        y = y0 + (y1 - y0) * t
        _add_box(
            f"floor_grid_y_{index:02d}",
            (x0, y - thickness, z),
            (x1, y + thickness, z + thickness),
            material,
        )


def _add_nozzle_block(
    center: Vector,
    span: float,
    mins: Vector,
    maxs: Vector,
    material: bpy.types.Material,
) -> None:
    length = span * 0.08
    half_y = max((maxs.y - mins.y) * 0.10, span * 0.018)
    half_z = max((maxs.z - mins.z) * 0.10, span * 0.014)
    x1 = mins.x + span * 0.035
    x0 = x1 - length
    _add_box(
        "rectangular_nozzle_block",
        (x0, center.y - half_y, center.z - half_z),
        (x1, center.y + half_y, center.z + half_z),
        material,
    )
    lip = span * 0.008
    _add_box(
        "rectangular_nozzle_lip",
        (x1 - lip, center.y - half_y * 1.25, center.z - half_z * 1.25),
        (x1 + lip, center.y + half_y * 1.25, center.z + half_z * 1.25),
        material,
    )


def _add_studio_walls(
    center: Vector,
    span: float,
    mins: Vector,
    maxs: Vector,
    floor_material: bpy.types.Material,
    back_material: bpy.types.Material,
    side_material: bpy.types.Material,
) -> None:
    floor = _add_floor(center, span, mins.z - span * 0.045, floor_material)
    floor.name = "studio_floor"

    width = span * 1.25
    height = span * 0.55
    y_back = maxs.y + span * 0.18
    z0 = mins.z - span * 0.045
    z1 = z0 + height
    verts = [
        (center.x - width * 0.55, y_back, z0),
        (center.x + width * 0.55, y_back, z0),
        (center.x + width * 0.55, y_back, z1),
        (center.x - width * 0.55, y_back, z1),
    ]
    mesh = bpy.data.meshes.new("studio_back_wall_mesh")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    back = bpy.data.objects.new("studio_back_wall", mesh)
    bpy.context.collection.objects.link(back)
    back.data.materials.append(back_material)

    x_side = mins.x - span * 0.08
    y0 = center.y - span * 0.32
    y1 = maxs.y + span * 0.18
    verts = [
        (x_side, y0, z0),
        (x_side, y1, z0),
        (x_side, y1, z1),
        (x_side, y0, z1),
    ]
    mesh = bpy.data.meshes.new("studio_side_wall_mesh")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    side = bpy.data.objects.new("studio_side_wall", mesh)
    bpy.context.collection.objects.link(side)
    side.data.materials.append(side_material)


def _add_label(text: str, location: tuple[float, float, float], size: float) -> None:
    font_curve = bpy.data.curves.new("label", "FONT")
    font_curve.body = text
    font_curve.size = size
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
    parser.add_argument(
        "--marker-style",
        choices=("octahedron", "icosahedron"),
        default="octahedron",
        help="Particle marker mesh. Icosahedron is smoother but heavier.",
    )
    parser.add_argument("--resolution", type=int, default=1280)
    parser.add_argument(
        "--camera-preset",
        choices=("isometric", "front", "front-ortho", "side", "top", "close"),
        default="isometric",
    )
    parser.add_argument("--fluid-color", type=_parse_color, default=DEFAULT_FLUID_COLOR)
    parser.add_argument("--boundary-color", type=_parse_color, default=DEFAULT_BOUNDARY_COLOR)
    parser.add_argument("--iso-color", type=_parse_color, default=DEFAULT_ISO_COLOR)
    parser.add_argument("--background-color", type=_parse_color, default=DEFAULT_BACKGROUND_COLOR)
    parser.add_argument("--hide-fluid", action="store_true")
    parser.add_argument("--hide-iso", action="store_true")
    parser.add_argument(
        "--style-preset",
        choices=("standard", "polished"),
        default="polished",
        help="standard keeps a plain technical preview; polished adds glassier materials.",
    )
    parser.add_argument(
        "--surface-material",
        choices=(
            "cyan-glassy",
            "clear-water",
            "tinted-water",
            "review-water",
            "hero-water",
            "scientific-water",
            "opaque-control",
        ),
        default="cyan-glassy",
        help="Material preset used for the reconstructed IsoSurface.",
    )
    parser.add_argument(
        "--surface-smoothing",
        choices=("none", "weighted-normal", "smooth", "smooth-weighted"),
        default="none",
        help="Optional render-time surface smoothing modifiers for IsoSurface meshes.",
    )
    parser.add_argument("--surface-smooth-factor", type=float, default=0.25)
    parser.add_argument("--surface-smooth-iterations", type=int, default=1)
    parser.add_argument(
        "--render-engine",
        choices=("eevee", "cycles"),
        default="eevee",
        help="Use Eevee Next for speed or Cycles for transparent-water hero checks.",
    )
    parser.add_argument(
        "--add-floor",
        action="store_true",
        help="Add a neutral studio floor below the visible geometry for scale/refraction cues.",
    )
    parser.add_argument(
        "--add-studio-walls",
        action="store_true",
        help="Add distinct neutral floor/back/side walls for transparent-water readability.",
    )
    parser.add_argument("--floor-color", type=_parse_color, default=(0.84, 0.86, 0.85, 1.0))
    parser.add_argument("--back-wall-color", type=_parse_color, default=(0.91, 0.92, 0.90, 1.0))
    parser.add_argument("--side-wall-color", type=_parse_color, default=(0.73, 0.77, 0.78, 1.0))
    parser.add_argument("--add-nozzle-block", action="store_true")
    parser.add_argument("--add-floor-grid", action="store_true")
    parser.add_argument("--nozzle-color", type=_parse_color, default=(0.78, 0.78, 0.74, 1.0))
    parser.add_argument("--grid-color", type=_parse_color, default=(0.58, 0.62, 0.64, 1.0))
    parser.add_argument("--camera-lens", type=float, default=55.0)
    parser.add_argument("--ortho-scale", type=float)
    parser.add_argument("--camera-target-x-fraction", type=float)
    parser.add_argument("--camera-target-y-fraction", type=float)
    parser.add_argument("--camera-target-z-fraction", type=float)
    parser.add_argument("--camera-span-scale", type=float, default=1.0)
    parser.add_argument("--light-energy", type=float, default=700.0)
    parser.add_argument("--light-size", type=float, default=1.6)
    parser.add_argument("--light-offset", type=_parse_vector3, default=(0.15, -1.25, 1.35))
    parser.add_argument("--fill-light-energy", type=float, default=0.0)
    parser.add_argument("--fill-light-offset", type=_parse_vector3, default=(-0.8, 0.6, 0.55))
    parser.add_argument("--rim-light-energy", type=float, default=0.0)
    parser.add_argument("--rim-light-offset", type=_parse_vector3, default=(0.65, 0.8, 0.8))
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--view-transform", default="Filmic")
    parser.add_argument("--view-look", default="Medium High Contrast")
    parser.add_argument("--exposure", type=float, default=0.0)
    parser.add_argument("--gamma", type=float, default=1.0)
    parser.add_argument("--ambient-occlusion", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--contact-shadows", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--caption", default=DEFAULT_CAPTION)
    parser.add_argument("--caption-size", type=float, default=0.035)
    parser.add_argument("--no-caption", action="store_true")
    parser.add_argument(
        "--camera-reference",
        type=Path,
        help="Optional VTK file used only for stable camera bounds and marker scale.",
    )
    parser.add_argument("--color-by", help="Point FIELD/SCALAR name to color by, e.g. Vel or Press.")
    parser.add_argument("--color-bins", type=int, default=6)
    parser.add_argument("--color-min", type=float)
    parser.add_argument("--color-max", type=float)
    return parser.parse_args(argv)


def _camera_location(center: Vector, span: float, preset: str) -> tuple[float, float, float]:
    if preset == "front-ortho":
        return (center.x, center.y - span * 2.2, center.z)
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

    reference = None
    if args.camera_reference:
        if not args.camera_reference.exists():
            raise SystemExit(f"ERROR: missing camera reference VTK: {args.camera_reference}")
        print(f"CAMERA_REFERENCE_VTK={args.camera_reference}")
        reference = parse_legacy_vtk(args.camera_reference)
        print(f"CAMERA_REFERENCE_POINTS={len(reference.points)}")

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

    if args.style_preset == "polished":
        fluid_mat = _make_material(
            "fluid_water_blue",
            args.fluid_color,
            roughness=0.28,
            specular=0.75,
        )
        boundary_mat = _make_material(
            "boundary_warm_matte",
            args.boundary_color,
            roughness=0.68,
            specular=0.25,
        )
        if args.surface_material == "clear-water":
            iso_mat = _make_material(
                "clear_water_material",
                (0.92, 0.98, 1.0, max(0.18, min(args.iso_color[3], 0.32))),
                roughness=0.015,
                specular=1.0,
                transmission=0.88,
                ior=1.333,
            )
        elif args.surface_material == "tinted-water":
            iso_mat = _make_material(
                "transparent_water_material_light_tint",
                (0.76, 0.96, 0.98, max(0.46, min(args.iso_color[3], 0.68))),
                roughness=0.018,
                specular=1.0,
                transmission=0.48,
                ior=1.333,
            )
        elif args.surface_material == "review-water":
            iso_mat = _make_material(
                "public_review_clear_water_material",
                (0.90, 0.985, 1.0, max(0.54, min(args.iso_color[3], 0.72))),
                roughness=0.006,
                specular=1.0,
                transmission=0.42,
                ior=1.333,
            )
        elif args.surface_material == "hero-water":
            iso_mat = _make_material(
                "benchmark_hero_clear_water_material",
                (0.965, 0.995, 1.0, max(0.36, min(args.iso_color[3], 0.52))),
                roughness=0.002,
                specular=1.0,
                transmission=0.68,
                ior=1.333,
            )
        elif args.surface_material == "scientific-water":
            iso_mat = _make_material(
                "hero_scene_scientific_water_material",
                (0.72, 0.93, 0.96, max(0.62, min(args.iso_color[3], 0.82))),
                roughness=0.012,
                specular=1.0,
                transmission=0.28,
                ior=1.333,
            )
        elif args.surface_material == "opaque-control":
            iso_mat = _make_material(
                "opaque_pale_blue_control_material",
                (0.70, 0.90, 1.0, 1.0),
                roughness=0.18,
                specular=0.7,
                transmission=0.0,
                ior=1.333,
            )
        else:
            iso_mat = _make_material(
                "surface_glassy_cyan",
                args.iso_color,
                roughness=0.08,
                specular=0.9,
                transmission=0.35,
                ior=1.333,
            )
    else:
        fluid_mat = _make_material("fluid_water_blue", args.fluid_color)
        boundary_mat = _make_material("boundary_neutral", args.boundary_color)
        iso_mat = _make_material("surface_translucent", args.iso_color)
    floor_mat = _make_material(
        "studio_floor_matte",
        args.floor_color,
        roughness=0.72,
        specular=0.18,
    )
    back_wall_mat = _make_material(
        "studio_back_wall_warm_matte",
        args.back_wall_color,
        roughness=0.74,
        specular=0.16,
    )
    side_wall_mat = _make_material(
        "studio_side_wall_cool_matte",
        args.side_wall_color,
        roughness=0.78,
        specular=0.14,
    )
    nozzle_mat = _make_material(
        "test_rig_nozzle_block_matte",
        args.nozzle_color,
        roughness=0.55,
        specular=0.22,
    )
    grid_mat = _make_material(
        "floor_grid_scale_cues",
        args.grid_color,
        roughness=0.7,
        specular=0.1,
    )

    bounds_points = list(reference.points) if reference else list(fluid.points)
    if boundary and not reference:
        bounds_points.extend(boundary.points)
    if iso and iso.points and not reference:
        bounds_points.extend(iso.points)
    mins, maxs = _bounds(bounds_points)
    span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, 1e-6)
    center = (mins + maxs) * 0.5
    center = Vector(
        (
            mins.x + (maxs.x - mins.x) * args.camera_target_x_fraction
            if args.camera_target_x_fraction is not None
            else center.x,
            mins.y + (maxs.y - mins.y) * args.camera_target_y_fraction
            if args.camera_target_y_fraction is not None
            else center.y,
            mins.z + (maxs.z - mins.z) * args.camera_target_z_fraction
            if args.camera_target_z_fraction is not None
            else center.z,
        )
    )
    camera_span = span * max(0.05, args.camera_span_scale)
    radius = span * 0.006 * args.marker_scale

    if iso and iso.polygons and not args.hide_iso:
        surface = _add_surface(
            "dambreak_isosurface",
            iso.points,
            iso.polygons,
            iso_mat,
            smoothing=args.surface_smoothing,
            smooth_factor=args.surface_smooth_factor,
            smooth_iterations=args.surface_smooth_iterations,
        )
        surface.show_transparent = True

    if args.add_studio_walls:
        _add_studio_walls(center, span, mins, maxs, floor_mat, back_wall_mat, side_wall_mat)
    elif args.add_floor:
        _add_floor(center, span, mins.z - span * 0.045, floor_mat)
    if args.add_floor_grid:
        _add_floor_grid(center, span, mins, maxs, grid_mat)
    if args.add_nozzle_block:
        _add_nozzle_block(center, span, mins, maxs, nozzle_mat)

    if not args.hide_fluid and args.color_by:
        if args.color_by not in fluid.point_scalars:
            available = ", ".join(sorted(fluid.point_scalars))
            raise SystemExit(
                f"ERROR: --color-by {args.color_by!r} not found. Available: {available}"
            )
        values = [_magnitude(value) for value in fluid.point_scalars[args.color_by]]
        color_min, color_max = _add_colored_point_cloud(
            fluid.points,
            values,
            args.fluid_stride,
            radius,
            args.marker_style,
            args.color_bins,
            args.color_min,
            args.color_max,
        )
        print(f"COLOR_BY={args.color_by}")
        print(f"COLOR_MIN={color_min}")
        print(f"COLOR_MAX={color_max}")
        print(f"COLOR_BINS={args.color_bins}")
    elif not args.hide_fluid:
        _add_point_cloud(
            "dambreak_fluid_points",
            fluid.points,
            fluid_mat,
            args.fluid_stride,
            radius,
            args.marker_style,
        )
    if boundary:
        _add_point_cloud(
            "dambreak_boundary_points",
            boundary.points,
            boundary_mat,
            args.boundary_stride,
            radius * 0.8,
            args.marker_style,
        )

    if not args.no_caption and args.caption:
        _add_label(args.caption, (mins.x, mins.y - span * 0.08, maxs.z), args.caption_size)

    light_offset = Vector(args.light_offset) * span
    bpy.ops.object.light_add(type="AREA", location=center + light_offset)
    light = bpy.context.object
    light.name = "large_softbox"
    light.data.energy = args.light_energy
    light.data.size = span * args.light_size
    if hasattr(light.data, "use_shadow"):
        light.data.use_shadow = True
    if args.contact_shadows and hasattr(light.data, "use_contact_shadow"):
        light.data.use_contact_shadow = True
    if args.fill_light_energy > 0:
        bpy.ops.object.light_add(type="AREA", location=center + Vector(args.fill_light_offset) * span)
        fill = bpy.context.object
        fill.name = "soft_fill_light"
        fill.data.energy = args.fill_light_energy
        fill.data.size = span * max(0.1, args.light_size * 0.85)
    if args.rim_light_energy > 0:
        bpy.ops.object.light_add(type="AREA", location=center + Vector(args.rim_light_offset) * span)
        rim = bpy.context.object
        rim.name = "rim_highlight_light"
        rim.data.energy = args.rim_light_energy
        rim.data.size = span * max(0.1, args.light_size * 0.45)

    bpy.ops.object.camera_add(location=_camera_location(center, camera_span, args.camera_preset))
    camera = bpy.context.object
    direction = center - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    auto_ortho_scale = camera_span * 1.15 if args.camera_preset == "front-ortho" else None
    ortho_scale = args.ortho_scale or auto_ortho_scale
    if ortho_scale:
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = ortho_scale
    else:
        camera.data.lens = args.camera_lens
    bpy.context.scene.camera = camera

    if args.render_engine == "cycles":
        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.cycles.samples = args.samples
        bpy.context.scene.cycles.use_denoising = True
    else:
        bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
        bpy.context.scene.eevee.taa_render_samples = args.samples
        if args.ambient_occlusion and hasattr(bpy.context.scene.eevee, "use_gtao"):
            bpy.context.scene.eevee.use_gtao = True
            if hasattr(bpy.context.scene.eevee, "gtao_distance"):
                bpy.context.scene.eevee.gtao_distance = span * 0.35
            if hasattr(bpy.context.scene.eevee, "gtao_factor"):
                bpy.context.scene.eevee.gtao_factor = 0.9
    bpy.context.scene.render.resolution_x = args.resolution
    bpy.context.scene.render.resolution_y = int(args.resolution * 0.5625)  # 16:9 for video (1280x720)
    try:
        bpy.context.scene.view_settings.view_transform = args.view_transform
    except TypeError:
        print(f"WARNING: unsupported view transform {args.view_transform!r}; keeping default")
    try:
        bpy.context.scene.view_settings.look = args.view_look
    except TypeError:
        print(f"WARNING: unsupported view look {args.view_look!r}; keeping default")
    bpy.context.scene.view_settings.exposure = args.exposure
    bpy.context.scene.view_settings.gamma = args.gamma
    bpy.context.scene.world.color = args.background_color[:3]

    print(f"CAMERA_PRESET={args.camera_preset}")
    print(f"STYLE_PRESET={args.style_preset}")
    print(f"SURFACE_MATERIAL={args.surface_material}")
    print(f"SURFACE_SMOOTHING={args.surface_smoothing}")
    print(f"RENDER_ENGINE={args.render_engine}")
    print(f"CAMERA_LENS={args.camera_lens}")
    print(f"CAMERA_TARGET={tuple(center)}")
    print(f"CAMERA_SPAN_SCALE={args.camera_span_scale}")
    print(f"ORTHO_SCALE={ortho_scale}")
    print(f"LIGHT_ENERGY={args.light_energy}")
    print(f"LIGHT_SIZE={args.light_size}")
    print(f"LIGHT_OFFSET={args.light_offset}")
    print(f"FILL_LIGHT_ENERGY={args.fill_light_energy}")
    print(f"RIM_LIGHT_ENERGY={args.rim_light_energy}")
    print(f"VIEW_TRANSFORM={bpy.context.scene.view_settings.view_transform}")
    print(f"VIEW_LOOK={bpy.context.scene.view_settings.look}")
    print(f"EXPOSURE={bpy.context.scene.view_settings.exposure}")
    print(f"GAMMA={bpy.context.scene.view_settings.gamma}")
    print(f"AMBIENT_OCCLUSION={args.ambient_occlusion}")
    print(f"CONTACT_SHADOWS={args.contact_shadows}")
    print(f"FLUID_STRIDE={args.fluid_stride}")
    print(f"BOUNDARY_STRIDE={args.boundary_stride}")
    print(f"MARKER_SCALE={args.marker_scale}")
    print(f"MARKER_STYLE={args.marker_style}")
    print(f"FLUID_VISIBLE={not args.hide_fluid}")
    print(f"ISO_VISIBLE={bool(iso and iso.polygons and not args.hide_iso)}")
    print(f"STUDIO_FLOOR={args.add_floor}")
    print(f"STUDIO_WALLS={args.add_studio_walls}")
    print(f"FLOOR_GRID={args.add_floor_grid}")
    print(f"NOZZLE_BLOCK={args.add_nozzle_block}")

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
