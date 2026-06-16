#!/usr/bin/env python3
"""Run a bounded rectangular high-speed inlet-jet proxy from Box4Inlet3D.

This script copies the official DualSPHysics `06_Box4Inlet3D` example into a
stable work directory, derives a single rectangular inlet variant, runs the
official Linux tools, and exports small visualization/metrics artifacts outside
Git.

The generated case is a geometry/visualization proxy. It is not a fully
atomized spray simulation, not validation, not production CFD, and not
experimental agreement.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


DEFAULT_OFFICIAL_ROOT = Path(
    "/home/franco/opt/dualsphysics-full-package-20260611/DualSPHysics_v5.4"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/home/franco/stack-validation/20260612-dualsphysics-rectangular-highspeed-jet"
)
DEFAULT_BLENDER = Path("/home/franco/bin/blender-portable")
CASE_NAME = "CaseRectangularHighspeedJetProxy"
BASE_CASE_NAME = "CaseBox4Inlet3D"
NOZZLE_AREA = 0.6 * 0.4


UPGRADE_DEFAULTS = {
    "dp": 0.03,
    "tank_point": (-1.5, -2.5, -2.5),
    "tank_size": (15.0, 5.0, 6.0),
    "inlet_point": (-1.5, -0.3, 2.2),
    "inlet_size": (0.0, 0.6, 0.4),
    "pointmin": (-2.5, -3.0, -3.0),
    "pointmax": (14.5, 3.0, 5.0),
    "sim_posmin": (-2.0, -3.0, -2.6),
    "sim_posmax": (14.0, 3.0, 3.8),
}


V2_DEFAULTS = {
    "dp": 0.025,
    "tank_point": (-1.5, -4.0, -4.5),
    "tank_size": (27.5, 8.0, 10.0),
    "tank_boxfill": "bottom | left | front | back",
    "inlet_point": (-1.5, -0.3, 3.8),
    "inlet_size": (0.0, 0.6, 0.4),
    "pointmin": (-2.5, -4.5, -5.0),
    "pointmax": (27.0, 4.5, 6.0),
    "sim_posmin": (-2.2, -4.5, -4.9),
    "sim_posmax": (26.5, 4.5, 5.9),
    "freecentre": (10.0, 0.0, 0.4),
    "gravity": (0.0, 0.0, -9.81),
    "axis_convention": "jet axis is +x; gravity is vertical -z",
}


V3_DEFAULTS = {
    "dp": 0.025,
    "tank_point": (-1.5, -5.0, -5.2),
    "tank_size": (42.0, 10.0, 10.4),
    "tank_boxfill": "bottom | left | front | back",
    "inlet_point": (-1.5, -0.3, 0.0),
    "inlet_size": (0.0, 0.6, 0.4),
    "pointmin": (-2.5, -5.6, -5.8),
    "pointmax": (42.5, 5.6, 5.8),
    "sim_posmin": (-2.2, -5.6, -5.7),
    "sim_posmax": (42.0, 5.6, 5.7),
    "freecentre": (18.0, 0.0, 0.0),
    "gravity": (9.81, 0.0, 0.0),
    "axis_convention": "jet axis is +x; gravity is streamwise +x",
}


V4_DEFAULTS = {
    "dp": 0.025,
    "tank_point": (-1.5, -6.0, -6.2),
    "tank_size": (86.0, 12.0, 12.4),
    "tank_boxfill": "bottom | left | front | back",
    "inlet_point": (-1.5, -0.3, 0.0),
    "inlet_size": (0.0, 0.6, 0.4),
    "pointmin": (-2.5, -6.6, -6.8),
    "pointmax": (86.5, 6.6, 6.8),
    "sim_posmin": (-2.2, -6.6, -6.7),
    "sim_posmax": (86.0, 6.6, 6.7),
    "freecentre": (36.0, 0.0, 0.0),
    "gravity": (9.81, 0.0, 0.0),
    "axis_convention": "jet axis is +x; gravity is streamwise +x",
}


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    official_root: Path
    output_root: Path
    blender: Path

    @property
    def bin_dir(self) -> Path:
        return self.official_root / "bin/linux"

    @property
    def base_case_dir(self) -> Path:
        return self.official_root / "examples/inletoutlet/06_Box4Inlet3D"

    @property
    def case_work(self) -> Path:
        return self.output_root / "case_work"

    @property
    def case_xml_def(self) -> Path:
        return self.case_work / f"{CASE_NAME}_Def.xml"

    @property
    def case_out(self) -> Path:
        return self.case_work / f"{CASE_NAME}_out"

    @property
    def case_xml_run(self) -> Path:
        return self.case_out / f"{CASE_NAME}.xml"

    @property
    def data_dir(self) -> Path:
        return self.case_out / "data"

    @property
    def particles_dir(self) -> Path:
        return self.case_out / "particles"

    @property
    def surface_dir(self) -> Path:
        return self.output_root / "surface_vtk"

    @property
    def render_dir(self) -> Path:
        return self.output_root / "render_frames"

    @property
    def metrics_dir(self) -> Path:
        return self.output_root / "metrics"

    @property
    def logs_dir(self) -> Path:
        return self.output_root / "logs"


@dataclass
class VtkParticles:
    points: list[tuple[float, float, float]]
    arrays: dict[str, list[float | int | tuple[float, ...]]]


@dataclass
class VtkSurface:
    points: list[tuple[float, float, float]]
    polygons: list[tuple[int, int, int]]
    arrays: dict[str, list[float | int | tuple[float, ...]]]


def _run(
    command: list[str],
    log_path: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        if cwd:
            log.write(f"$ cd {cwd}\n")
        log.write("$ " + " ".join(command) + "\n\n")
        log.flush()
        completed = subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
            cwd=str(cwd) if cwd else None,
        )
        elapsed = time.monotonic() - started
        log.write(f"\nEXIT_CODE={completed.returncode}\n")
        log.write(f"ELAPSED_SECONDS={elapsed:.3f}\n")
    if completed.returncode != 0:
        raise RuntimeError(f"command failed, see {log_path}")


def _require(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: missing {label}: {path}")


def _tool(paths: Paths, name: str) -> Path:
    path = paths.bin_dir / name
    _require(path, name)
    if not os.access(path, os.X_OK):
        raise SystemExit(f"ERROR: tool is not executable: {path}")
    return path


def _runtime_env(paths: Paths) -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("LD_LIBRARY_PATH", "")
    extra = [str(paths.bin_dir), "/usr/local/cuda-12.8/lib64"]
    env["LD_LIBRARY_PATH"] = ":".join([part for part in [current, *extra] if part])
    return env


def _indent_xml(tree: ET.ElementTree) -> None:
    try:
        ET.indent(tree, space="    ")
    except AttributeError:
        pass


def _set_vector_attrs(element: ET.Element, values: tuple[float, float, float]) -> None:
    for key, value in zip(("x", "y", "z"), values):
        element.set(key, f"{value:g}")


def _profile_defaults(profile: str) -> dict[str, object] | None:
    if profile == "upgraded":
        return UPGRADE_DEFAULTS
    if profile == "v2":
        return V2_DEFAULTS
    if profile == "v3":
        return V3_DEFAULTS
    if profile == "v4":
        return V4_DEFAULTS
    return None


def _copy_and_modify_case(
    paths: Paths,
    velocity: float,
    time_max: float,
    time_out: float,
    force: bool,
    profile: str,
    dp: float | None,
) -> None:
    _require(paths.base_case_dir, "official Box4Inlet3D case")
    paths.output_root.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    if paths.case_work.exists():
        if not force:
            raise SystemExit(
                f"ERROR: case work already exists: {paths.case_work}; "
                "rerun with --force to replace generated case work"
            )
        shutil.rmtree(paths.case_work)
    shutil.copytree(paths.base_case_dir, paths.case_work)

    base_xml = paths.case_work / f"{BASE_CASE_NAME}_Def.xml"
    _require(base_xml, "copied Box4Inlet3D XML")
    tree = ET.parse(base_xml)
    root = tree.getroot()

    profile_defaults = _profile_defaults(profile)
    if profile_defaults:
        definition = root.find("./casedef/geometry/definition")
        if definition is None:
            raise SystemExit("ERROR: missing geometry/definition in Box4Inlet3D XML")
        definition.set("dp", f"{(dp or profile_defaults['dp']):g}")
        pointmin = definition.find("pointmin")
        pointmax = definition.find("pointmax")
        if pointmin is None or pointmax is None:
            raise SystemExit("ERROR: missing pointmin/pointmax in geometry/definition")
        _set_vector_attrs(pointmin, profile_defaults["pointmin"])  # type: ignore[arg-type]
        _set_vector_attrs(pointmax, profile_defaults["pointmax"])  # type: ignore[arg-type]

        for tag, attrs in [
            ("gravity", profile_defaults.get("gravity", (0.0, 0.0, -9.81))),
        ]:
            element = root.find(f"./casedef/constantsdef/{tag}")
            if element is not None:
                _set_vector_attrs(element, attrs)  # type: ignore[arg-type]
        speedsystem = root.find("./casedef/constantsdef/speedsystem")
        if speedsystem is not None:
            speedsystem.set("value", f"{velocity:g}")
            speedsystem.set("auto", "false")

    # Keep the official tank and the first rectangular inlet seed. Remove the
    # other three seed blocks plus their in/out zones to avoid a four-jet demo.
    # In upgraded mode, also remove the central bottom void from the educational
    # four-inlet case and stretch the tank so downstream wall interaction is
    # outside the short showcase run.
    mainlist = root.find("./casedef/geometry/commands/mainlist")
    if mainlist is None:
        raise SystemExit("ERROR: missing geometry/mainlist in Box4Inlet3D XML")
    children = list(mainlist)
    keep: list[ET.Element] = []
    skip_next_drawbox = False
    for child in children:
        if skip_next_drawbox:
            skip_next_drawbox = False
            if child.tag == "drawbox":
                continue
        if profile_defaults and child.tag == "setmkvoid":
            skip_next_drawbox = True
            continue
        if child.tag == "setmkfluid" and child.attrib.get("mk") in {"1", "2", "3"}:
            skip_next_drawbox = True
            continue
        keep.append(child)
    mainlist[:] = keep

    if profile_defaults:
        drawboxes = mainlist.findall("drawbox")
        if len(drawboxes) < 2:
            raise SystemExit("ERROR: upgraded profile expected tank and inlet drawbox")
        tank = drawboxes[0]
        tank_boxfill = tank.find("boxfill")
        tank_point = tank.find("point")
        tank_size = tank.find("size")
        if tank_boxfill is not None:
            tank_boxfill.text = str(profile_defaults.get("tank_boxfill", "all^top"))
        if tank_point is not None:
            _set_vector_attrs(tank_point, profile_defaults["tank_point"])  # type: ignore[arg-type]
        if tank_size is not None:
            _set_vector_attrs(tank_size, profile_defaults["tank_size"])  # type: ignore[arg-type]
        inlet = drawboxes[1]
        inlet_point = inlet.find("point")
        inlet_size = inlet.find("size")
        if inlet_point is not None:
            _set_vector_attrs(inlet_point, profile_defaults["inlet_point"])  # type: ignore[arg-type]
        if inlet_size is not None:
            _set_vector_attrs(inlet_size, profile_defaults["inlet_size"])  # type: ignore[arg-type]

    inout = root.find("./execution/special/inout")
    if inout is None:
        raise SystemExit("ERROR: missing execution/special/inout in Box4Inlet3D XML")
    zones = [child for child in list(inout) if child.tag == "inoutzone"]
    if not zones:
        raise SystemExit("ERROR: Box4Inlet3D XML has no inoutzone")
    for zone in zones[1:]:
        inout.remove(zone)

    velocity_elem = zones[0].find("./imposevelocity/velocity")
    if velocity_elem is None:
        raise SystemExit("ERROR: first inoutzone has no fixed velocity")
    velocity_elem.set("v", f"{velocity:g}")
    velocity_elem.set("comment", "Uniform velocity for rectangular high-speed jet proxy")

    for parameter in root.findall("./execution/parameters/parameter"):
        key = parameter.attrib.get("key")
        if key == "TimeMax":
            parameter.set("value", f"{time_max:g}")
        elif key == "TimeOut":
            parameter.set("value", f"{time_out:g}")
    if profile_defaults:
        freecentre = root.find("./execution/special/inout/useboxlimit/freecentre")
        if freecentre is not None:
            _set_vector_attrs(freecentre, profile_defaults.get("freecentre", (5.0, 0.0, 0.5)))  # type: ignore[arg-type]
        sim_posmin = root.find("./execution/parameters/simulationdomain/posmin")
        sim_posmax = root.find("./execution/parameters/simulationdomain/posmax")
        if sim_posmin is not None:
            _set_vector_attrs(sim_posmin, profile_defaults["sim_posmin"])  # type: ignore[arg-type]
        if sim_posmax is not None:
            _set_vector_attrs(sim_posmax, profile_defaults["sim_posmax"])  # type: ignore[arg-type]

    _indent_xml(tree)
    tree.write(paths.case_xml_def, encoding="UTF-8", xml_declaration=True)
    (paths.case_work / "README_rectangular_highspeed_jet_proxy.txt").write_text(
        "\n".join(
            [
                "Generated modified case: rectangular_highspeed_jet_proxy",
                f"Base case: {paths.base_case_dir}",
                f"Profile: {profile}",
                "Modification: kept only mkfluid=0 rectangular inlet and first inoutzone.",
                f"Velocity: {velocity:g} m/s",
                f"TimeMax: {time_max:g} s",
                f"TimeOut: {time_out:g} s",
                f"dp: {(dp or profile_defaults['dp']) if profile_defaults else 'base'}",
                f"Gravity: {profile_defaults.get('gravity') if profile_defaults else 'base'}",
                f"Axis convention: {profile_defaults.get('axis_convention', 'base') if profile_defaults else 'base'}",
                "Caveat: modified DualSPHysics inlet-jet geometry proxy; not validation.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _run_dualsphysics(paths: Paths, solver_timeout: int, post_timeout: int) -> None:
    gencase = _tool(paths, "GenCase_linux64")
    solver = _tool(paths, "DualSPHysics5.4_linux64")
    partvtk = _tool(paths, "PartVTK_linux64")
    partvtkout = _tool(paths, "PartVTKOut_linux64")
    env = _runtime_env(paths)

    if paths.case_out.exists():
        shutil.rmtree(paths.case_out)
    _run(
        [
            str(gencase),
            f"{CASE_NAME}_Def",
            str(paths.case_out / CASE_NAME),
            "-save:all",
        ],
        paths.logs_dir / "01_gencase.log",
        180,
        env=env,
        cwd=paths.case_work,
    )
    _run(
        [
            str(solver),
            "-gpu",
            str(paths.case_out / CASE_NAME),
            str(paths.case_out),
        ],
        paths.logs_dir / "02_dualsphysics_gpu.log",
        solver_timeout,
        env=env,
    )
    paths.particles_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            str(partvtk),
            "-dirdata",
            str(paths.data_dir),
            "-savevtk",
            str(paths.particles_dir / "PartFluid"),
            "-onlytype:-all,fluid",
            "-vars:+idp,+vel,+rhop,+press,+vor",
        ],
        paths.logs_dir / "03_partvtk.log",
        post_timeout,
        env=env,
    )
    _run(
        [
            str(partvtkout),
            "-dirdata",
            str(paths.data_dir),
            "-savevtk",
            str(paths.particles_dir / "PartFluidOut"),
            "-SaveResume",
            str(paths.particles_dir / "_ResumeFluidOut"),
        ],
        paths.logs_dir / "04_partvtkout.log",
        post_timeout,
        env=env,
    )


def _frame_number(path: Path) -> int:
    stem = path.stem
    try:
        return int(stem.rsplit("_", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"cannot parse frame number from {path.name}") from exc


def _existing_particle_frames(paths: Paths) -> list[Path]:
    return sorted(paths.particles_dir.glob("PartFluid_*.vtk"), key=_frame_number)


def _selected_frame_numbers(frames: list[Path], max_frames: int) -> list[int]:
    numbers = [_frame_number(path) for path in frames]
    if len(numbers) <= max_frames:
        return numbers
    if max_frames <= 1:
        return [numbers[-1]]
    indices = [
        round(index * (len(numbers) - 1) / (max_frames - 1))
        for index in range(max_frames)
    ]
    selected: list[int] = []
    for index in indices:
        value = numbers[index]
        if not selected or selected[-1] != value:
            selected.append(value)
    if selected[-1] != numbers[-1]:
        selected[-1] = numbers[-1]
    return selected


def _run_isosurface(paths: Paths, frames: list[int], timeout_seconds: int) -> list[Path]:
    isosurface = _tool(paths, "IsoSurface_linux64")
    env = _runtime_env(paths)
    paths.surface_dir.mkdir(parents=True, exist_ok=True)
    surfaces: list[Path] = []
    for frame in frames:
        surface = paths.surface_dir / f"Surface_{frame:04d}.vtk"
        if surface.exists() and surface.stat().st_size > 0:
            surfaces.append(surface)
            continue
        _run(
            [
                str(isosurface),
                "-dirdata",
                str(paths.data_dir),
                "-filexml",
                str(paths.case_xml_run),
                f"-first:{frame}",
                f"-last:{frame}",
                "-saveiso",
                str(paths.surface_dir / "Surface"),
                "-vars:-all,+vel,+rhop,+press,+type",
            ],
            paths.logs_dir / f"05_isosurface_{frame:04d}.log",
            timeout_seconds,
            env=env,
        )
        if surface.exists() and surface.stat().st_size > 0:
            surfaces.append(surface)
    return surfaces


def _read_line(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\n", offset)
    if end < 0:
        return data[offset:].decode("ascii", errors="replace"), len(data)
    return data[offset:end].decode("ascii", errors="replace"), end + 1


def _skip_ws(data: bytes, offset: int) -> int:
    while offset < len(data) and chr(data[offset]).isspace():
        offset += 1
    return offset


def _vtk_type(type_name: str) -> tuple[str, int, type]:
    name = type_name.lower()
    if name in {"float", "float32"}:
        return "f", 4, float
    if name in {"double", "float64"}:
        return "d", 8, float
    if name in {"int", "unsigned_int"}:
        return ("i" if name == "int" else "I"), 4, int
    if name in {"short", "unsigned_short"}:
        return ("h" if name == "short" else "H"), 2, int
    if name in {"char", "unsigned_char"}:
        return ("b" if name == "char" else "B"), 1, int
    raise ValueError(f"unsupported VTK data type: {type_name}")


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
    return list(struct.unpack(f">{count}{fmt_char}", raw)), offset + byte_count


def _parse_vtk_particles(path: Path) -> VtkParticles:
    data = path.read_bytes()
    offset = 0
    binary = False
    point_count = 0
    points: list[tuple[float, float, float]] = []
    arrays: dict[str, list[float | int | tuple[float, ...]]] = {}
    while offset < len(data):
        offset = _skip_ws(data, offset)
        line, offset = _read_line(data, offset)
        parts = line.split()
        if not parts:
            continue
        key = parts[0].upper()
        if key == "BINARY":
            binary = True
        elif key == "ASCII":
            binary = False
        elif key == "POINTS":
            point_count = int(parts[1])
            values, offset = _read_numeric_block(data, offset, point_count * 3, parts[2], binary)
            points = [
                (float(values[i]), float(values[i + 1]), float(values[i + 2]))
                for i in range(0, len(values), 3)
            ]
        elif key == "POINT_DATA":
            point_count = int(parts[1])
        elif key == "SCALARS" and point_count > 0:
            name = parts[1]
            dtype = parts[2]
            components = int(parts[3]) if len(parts) > 3 else 1
            lookup, offset = _read_line(data, offset)
            if not lookup.upper().startswith("LOOKUP_TABLE"):
                continue
            values, offset = _read_numeric_block(data, offset, point_count * components, dtype, binary)
            if components == 1:
                arrays[name] = values
            else:
                arrays[name] = [
                    tuple(values[i : i + components])
                    for i in range(0, len(values), components)
                ]
        elif key == "VECTORS" and point_count > 0:
            name = parts[1]
            values, offset = _read_numeric_block(data, offset, point_count * 3, parts[2], binary)
            arrays[name] = [
                tuple(values[i : i + 3])
                for i in range(0, len(values), 3)
            ]
        elif key == "FIELD":
            arrays_count = int(parts[2]) if len(parts) > 2 else 0
            for _ in range(arrays_count):
                field_line, offset = _read_line(data, offset)
                field_parts = field_line.split()
                if len(field_parts) < 4:
                    continue
                name = field_parts[0]
                components = int(field_parts[1])
                tuples = int(field_parts[2])
                dtype = field_parts[3]
                values, offset = _read_numeric_block(data, offset, components * tuples, dtype, binary)
                if components == 1:
                    arrays[name] = values
                else:
                    arrays[name] = [
                        tuple(values[i : i + components])
                        for i in range(0, len(values), components)
                    ]
    return VtkParticles(points=points, arrays=arrays)


def _parse_vtk_surface(path: Path) -> VtkSurface:
    data = path.read_bytes()
    offset = 0
    binary = False
    point_count = 0
    points: list[tuple[float, float, float]] = []
    polygons: list[tuple[int, int, int]] = []
    arrays: dict[str, list[float | int | tuple[float, ...]]] = {}
    while offset < len(data):
        offset = _skip_ws(data, offset)
        line, offset = _read_line(data, offset)
        parts = line.split()
        if not parts:
            continue
        key = parts[0].upper()
        if key == "BINARY":
            binary = True
        elif key == "ASCII":
            binary = False
        elif key == "POINTS":
            point_count = int(parts[1])
            values, offset = _read_numeric_block(data, offset, point_count * 3, parts[2], binary)
            points = [
                (float(values[i]), float(values[i + 1]), float(values[i + 2]))
                for i in range(0, len(values), 3)
            ]
        elif key == "POLYGONS":
            poly_count = int(parts[1])
            total_ints = int(parts[2])
            values, offset = _read_numeric_block(data, offset, total_ints, "int", binary)
            cursor = 0
            for _ in range(poly_count):
                width = int(values[cursor])
                ids = values[cursor + 1 : cursor + 1 + width]
                if width == 3:
                    polygons.append((int(ids[0]), int(ids[1]), int(ids[2])))
                elif width > 3:
                    base = int(ids[0])
                    for local in range(1, width - 1):
                        polygons.append((base, int(ids[local]), int(ids[local + 1])))
                cursor += width + 1
        elif key == "POINT_DATA":
            point_count = int(parts[1])
        elif key == "SCALARS" and point_count > 0:
            name = parts[1]
            dtype = parts[2]
            components = int(parts[3]) if len(parts) > 3 else 1
            lookup, offset = _read_line(data, offset)
            if not lookup.upper().startswith("LOOKUP_TABLE"):
                continue
            values, offset = _read_numeric_block(data, offset, point_count * components, dtype, binary)
            if components == 1:
                arrays[name] = values
            else:
                arrays[name] = [
                    tuple(values[i : i + components])
                    for i in range(0, len(values), components)
                ]
        elif key == "VECTORS" and point_count > 0:
            name = parts[1]
            values, offset = _read_numeric_block(data, offset, point_count * 3, parts[2], binary)
            arrays[name] = [
                tuple(values[i : i + 3])
                for i in range(0, len(values), 3)
            ]
    return VtkSurface(points=points, polygons=polygons, arrays=arrays)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def _std(values: list[float], mean: float) -> float:
    if len(values) < 2 or not math.isfinite(mean):
        return 0.0
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _principal_metrics(y_values: list[float], z_values: list[float]) -> tuple[float, float]:
    if len(y_values) < 3:
        return math.nan, math.nan
    y_mean = _mean(y_values)
    z_mean = _mean(z_values)
    cov_yy = _mean([(y - y_mean) ** 2 for y in y_values])
    cov_zz = _mean([(z - z_mean) ** 2 for z in z_values])
    cov_yz = _mean([(y - y_mean) * (z - z_mean) for y, z in zip(y_values, z_values)])
    trace = cov_yy + cov_zz
    disc = max(0.0, (cov_yy - cov_zz) ** 2 + 4.0 * cov_yz * cov_yz)
    eig1 = 0.5 * (trace + math.sqrt(disc))
    eig2 = 0.5 * (trace - math.sqrt(disc))
    angle_deg = math.degrees(0.5 * math.atan2(2.0 * cov_yz, cov_yy - cov_zz))
    if eig2 <= 1.0e-14:
        aspect = math.inf if eig1 > 0 else math.nan
    else:
        aspect = math.sqrt(max(eig1, eig2) / min(eig1, eig2))
    return aspect, angle_deg


def _velocity_arrays(vtk: VtkParticles) -> list[tuple[float, float, float]] | None:
    for name in ("Vel", "vel", "Velocity", "velocity"):
        values = vtk.arrays.get(name)
        if values and isinstance(values[0], tuple):
            return values  # type: ignore[return-value]
    return None


def _scalar_array(vtk: VtkParticles, names: tuple[str, ...]) -> list[float] | None:
    for name in names:
        values = vtk.arrays.get(name)
        if values and not isinstance(values[0], tuple):
            return [float(value) for value in values]  # type: ignore[arg-type]
    return None


def _extract_metrics(paths: Paths, stations: int, min_particles: int) -> tuple[Path, Path, dict]:
    frames = _existing_particle_frames(paths)
    if not frames:
        raise RuntimeError("no PartFluid VTK frames available for metrics")
    parsed: list[tuple[Path, VtkParticles]] = [(path, _parse_vtk_particles(path)) for path in frames]
    all_x = [point[0] for _, vtk in parsed for point in vtk.points]
    x_min = min(all_x)
    x_max = max(all_x)
    if not math.isfinite(x_min) or not math.isfinite(x_max) or x_max <= x_min:
        raise RuntimeError("invalid axial coordinate range for metrics")
    dx = (x_max - x_min) / stations

    csv_path = paths.metrics_dir / "rectangular_highspeed_jet_slice_metrics.csv"
    json_path = paths.metrics_dir / "rectangular_highspeed_jet_metrics_summary.json"
    paths.metrics_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    frame_particle_counts: list[int] = []
    for path, vtk in parsed:
        frame = _frame_number(path)
        velocities = _velocity_arrays(vtk)
        pressure = _scalar_array(vtk, ("Press", "press", "Pressure", "pressure", "P", "p"))
        frame_particle_counts.append(len(vtk.points))
        for station_index in range(stations):
            lo = x_min + station_index * dx
            hi = x_min + (station_index + 1) * dx if station_index < stations - 1 else x_max + 1.0e-9
            ids = [idx for idx, point in enumerate(vtk.points) if lo <= point[0] < hi]
            if not ids:
                continue
            xs = [vtk.points[idx][0] for idx in ids]
            ys = [vtk.points[idx][1] for idx in ids]
            zs = [vtk.points[idx][2] for idx in ids]
            width_y = max(ys) - min(ys)
            width_z = max(zs) - min(zs)
            area_proxy = width_y * width_z
            aspect, orientation = _principal_metrics(ys, zs)
            quality_flags: list[str] = []
            if len(ids) < min_particles:
                quality_flags.append("sparse")
            if area_proxy <= 0:
                quality_flags.append("zero_area_proxy")
            if not math.isfinite(aspect):
                quality_flags.append("aspect_unstable")
            u_axial_mean = math.nan
            u_axial_std = math.nan
            u_y_mean = math.nan
            u_y_std = math.nan
            u_z_mean = math.nan
            u_z_std = math.nan
            speed_mean = math.nan
            speed_std = math.nan
            velocity_fluctuation_energy_proxy = math.nan
            if velocities:
                vx = [float(velocities[idx][0]) for idx in ids]
                vy = [float(velocities[idx][1]) for idx in ids]
                vz = [float(velocities[idx][2]) for idx in ids]
                speeds = [
                    math.sqrt(
                        float(velocities[idx][0]) ** 2
                        + float(velocities[idx][1]) ** 2
                        + float(velocities[idx][2]) ** 2
                    )
                    for idx in ids
                ]
                u_axial_mean = _mean(vx)
                u_axial_std = _std(vx, u_axial_mean)
                u_y_mean = _mean(vy)
                u_y_std = _std(vy, u_y_mean)
                u_z_mean = _mean(vz)
                u_z_std = _std(vz, u_z_mean)
                speed_mean = _mean(speeds)
                speed_std = _std(speeds, speed_mean)
                velocity_fluctuation_energy_proxy = 0.5 * (
                    u_axial_std * u_axial_std + u_y_std * u_y_std + u_z_std * u_z_std
                )
            pressure_mean = math.nan
            pressure_std = math.nan
            if pressure:
                pressures = [pressure[idx] for idx in ids]
                pressure_mean = _mean(pressures)
                pressure_std = _std(pressures, pressure_mean)
            rows.append(
                {
                    "source_type": "dualsphysics_particle_vtk",
                    "simulation_source": "modified_box4inlet3d_rectangular_highspeed_proxy",
                    "physical_validation": "false",
                    "frame": frame,
                    "z": _mean(xs),
                    "axial_coordinate": "x",
                    "station_index": station_index,
                    "slice_thickness_x": hi - lo,
                    "particle_count": len(ids),
                    "centroid_y": _mean(ys),
                    "centroid_z": _mean(zs),
                    "width_y": width_y,
                    "width_z": width_z,
                    "area_proxy": area_proxy,
                    "Ahat": area_proxy / NOZZLE_AREA if area_proxy > 0 else math.nan,
                    "aspect_ratio": aspect,
                    "orientation_deg_yz": orientation,
                    "u_axial_mean": u_axial_mean,
                    "u_axial_std": u_axial_std,
                    "u_y_mean": u_y_mean,
                    "u_y_std": u_y_std,
                    "u_z_mean": u_z_mean,
                    "u_z_std": u_z_std,
                    "speed_mean": speed_mean,
                    "speed_std": speed_std,
                    "velocity_fluctuation_energy_proxy": velocity_fluctuation_energy_proxy,
                    "pressure_mean": pressure_mean,
                    "pressure_std": pressure_std,
                    "quality_flags": ";".join(quality_flags) if quality_flags else "ok",
                }
            )
    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "status": "success",
        "frames": len(parsed),
        "metric_rows": len(rows),
        "particle_count_min": min(frame_particle_counts),
        "particle_count_max": max(frame_particle_counts),
        "x_range": [x_min, x_max],
        "stations": stations,
        "available_particle_arrays": sorted(parsed[-1][1].arrays.keys()),
        "pressure_available": any(
            name in parsed[-1][1].arrays for name in ("Press", "press", "Pressure", "pressure", "P", "p")
        ),
        "velocity_available": _velocity_arrays(parsed[-1][1]) is not None,
        "velocity_fluctuation_energy_proxy": (
            "Computed from exported particle velocity component standard deviations per slice; "
            "this is not a true turbulence quantity."
        ),
        "nozzle_area_proxy_reference": NOZZLE_AREA,
        "csv_path": str(csv_path),
        "physical_validation": False,
        "caveat": (
            "Modified DualSPHysics inlet-jet geometry proxy; not a fully "
            "atomized spray simulation, not validation, not production CFD, "
            "and not experimental agreement."
        ),
    }
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return csv_path, json_path, summary


def _render_frames(
    paths: Paths,
    frames: list[int],
    timeout_seconds: int,
    *,
    mode: str = "velocity",
    camera_preset: str = "isometric",
    output_prefix: str = "rectangular_highspeed_jet",
    color_max: float = 6.0,
    color_min: float = 0.0,
    color_by: str | None = None,
    resolution: int = 1280,
    samples: int = 48,
    camera_lens: float = 70.0,
    ortho_scale: float | None = None,
    camera_target_x_fraction: float | None = None,
    camera_target_y_fraction: float | None = None,
    camera_target_z_fraction: float | None = None,
    camera_span_scale: float | None = None,
    marker_scale: float = 1.15,
    marker_style: str = "octahedron",
    fluid_stride: int = 1,
    iso_color: str = "#5DD9FF66",
    fluid_color: str = "#5DD9FF66",
    surface_material: str = "cyan-glassy",
    render_engine: str = "eevee",
    add_floor: bool = False,
    add_studio_walls: bool = False,
    background_color: str = "#071018FF",
    light_energy: float = 1200.0,
    light_size: float = 2.0,
    light_offset: str | None = None,
    floor_color: str | None = None,
    back_wall_color: str | None = None,
    side_wall_color: str | None = None,
    view_transform: str | None = None,
    view_look: str | None = None,
    exposure: float | None = None,
    gamma: float | None = None,
) -> list[Path]:
    _require(paths.blender, "Blender executable")
    paths.render_dir.mkdir(parents=True, exist_ok=True)
    reference = paths.particles_dir / f"PartFluid_{frames[-1]:04d}.vtk"
    rendered: list[Path] = []
    for frame in frames:
        fluid = paths.particles_dir / f"PartFluid_{frame:04d}.vtk"
        surface = paths.surface_dir / f"Surface_{frame:04d}.vtk"
        if mode == "surface" and (not surface.exists() or surface.stat().st_size == 0):
            continue
        output = paths.render_dir / f"{output_prefix}_{frame:04d}.png"
        if output.exists() and output.stat().st_size > 0:
            rendered.append(output)
            continue
        command = [
            str(paths.blender),
            "--background",
            "--python",
            str(paths.repo_root / "scripts/blender_import_legacy_vtk.py"),
            "--",
            "--fluid",
            str(fluid),
            "--camera-reference",
            str(reference),
            "--output",
            str(output),
            "--resolution",
            str(resolution),
            "--camera-preset",
            camera_preset,
            "--camera-lens",
            f"{camera_lens:g}",
            "--style-preset",
            "polished",
            "--samples",
            str(samples),
            "--marker-scale",
            f"{marker_scale:g}",
            "--marker-style",
            marker_style,
            "--fluid-stride",
            str(fluid_stride),
            "--background-color",
            background_color,
            "--light-energy",
            f"{light_energy:g}",
            "--light-size",
            f"{light_size:g}",
            "--no-caption",
        ]
        if light_offset is not None:
            command.append(f"--light-offset={light_offset}")
        if floor_color is not None:
            command.extend(["--floor-color", floor_color])
        if back_wall_color is not None:
            command.extend(["--back-wall-color", back_wall_color])
        if side_wall_color is not None:
            command.extend(["--side-wall-color", side_wall_color])
        if view_transform is not None:
            command.extend(["--view-transform", view_transform])
        if view_look is not None:
            command.extend(["--view-look", view_look])
        if exposure is not None:
            command.extend(["--exposure", f"{exposure:g}"])
        if gamma is not None:
            command.extend(["--gamma", f"{gamma:g}"])
        if ortho_scale is not None:
            command.extend(["--ortho-scale", f"{ortho_scale:g}"])
        if camera_target_x_fraction is not None:
            command.extend(["--camera-target-x-fraction", f"{camera_target_x_fraction:g}"])
        if camera_target_y_fraction is not None:
            command.extend(["--camera-target-y-fraction", f"{camera_target_y_fraction:g}"])
        if camera_target_z_fraction is not None:
            command.extend(["--camera-target-z-fraction", f"{camera_target_z_fraction:g}"])
        if camera_span_scale is not None:
            command.extend(["--camera-span-scale", f"{camera_span_scale:g}"])
        if mode in {"velocity", "analysis"}:
            command.extend(
                [
                    "--color-by",
                    color_by or "Vel",
                    "--color-bins",
                    "7",
                    "--color-min",
                    f"{color_min:g}",
                    "--color-max",
                    f"{color_max:g}",
                ]
            )
        if mode == "surface":
            command.extend(
                [
                    "--hide-fluid",
                    "--iso",
                    str(surface),
                    "--iso-color",
                    iso_color,
                    "--fluid-color",
                    fluid_color,
                    "--surface-material",
                    surface_material,
                    "--render-engine",
                    render_engine,
                ]
            )
            if add_floor:
                command.append("--add-floor")
            if add_studio_walls:
                command.append("--add-studio-walls")
        elif surface.exists() and surface.stat().st_size > 0:
            command.extend(["--iso", str(surface), "--iso-color", iso_color])
        _run(command, paths.logs_dir / f"06_blender_{output_prefix}_{frame:04d}.log", timeout_seconds)
        rendered.append(output)
    return rendered


def _assemble_clean_video(
    paths: Paths,
    rendered: list[Path],
    fps: int,
    stem: str,
) -> Path:
    sequence_dir = paths.output_root / f"{stem}_frames_canonical"
    sequence_dir.mkdir(parents=True, exist_ok=True)
    for stale in sequence_dir.glob("frame_*.png"):
        stale.unlink()
    for index, frame in enumerate(rendered):
        shutil.copy2(frame, sequence_dir / f"frame_{index:04d}.png")
    clean_mp4 = paths.output_root / f"{stem}.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(sequence_dir / "frame_%04d.png"),
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(clean_mp4),
        ],
        paths.logs_dir / f"07_ffmpeg_{stem}.log",
        300,
    )
    return clean_mp4


def _make_contact_sheet(paths: Paths, rendered: list[Path], output_name: str) -> Path:
    from PIL import Image

    contact_sheet = paths.output_root / f"{output_name}.png"
    tile_columns = 5
    tile_rows = max(1, math.ceil(len(rendered) / tile_columns))
    thumb_w, thumb_h = 320, 180
    sheet = Image.new("RGB", (tile_columns * thumb_w, tile_rows * thumb_h), (0, 0, 0))
    for index, frame in enumerate(rendered):
        image = Image.open(frame).convert("RGB")
        image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (thumb_w, thumb_h), (0, 0, 0))
        left = (thumb_w - image.width) // 2
        top = (thumb_h - image.height) // 2
        tile.paste(image, (left, top))
        row, column = divmod(index, tile_columns)
        sheet.paste(tile, (column * thumb_w, row * thumb_h))
    contact_sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(contact_sheet)
    return contact_sheet


def _contact_sheet_samples(*segments: list[Path]) -> list[Path]:
    sampled: list[Path] = []
    for segment in segments:
        if not segment:
            continue
        picks = [0, len(segment) // 2, len(segment) - 1]
        for index in picks:
            path = segment[index]
            if path not in sampled:
                sampled.append(path)
    return sampled


def _float_value(row: dict[str, str], key: str, default: float = math.nan) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


def _velocity_proxy_color(value: float, vmax: float) -> tuple[int, int, int]:
    if not math.isfinite(value) or vmax <= 0:
        return (60, 120, 180)
    t = min(1.0, max(0.0, value / vmax))
    if t < 0.5:
        s = t / 0.5
        return (round(35 * (1 - s) + 35 * s), round(118 * (1 - s) + 190 * s), round(210 * (1 - s) + 120 * s))
    s = (t - 0.5) / 0.5
    return (round(35 * (1 - s) + 235 * s), round(190 * (1 - s) + 125 * s), round(120 * (1 - s) + 55 * s))


def _write_moving_slice_diagnostics(
    paths: Paths,
    metrics_csv: Path,
    fps: int,
    max_frames: int = 40,
    stem: str = "rectangular_jet_v3",
) -> dict[str, str | int]:
    from PIL import Image, ImageDraw, ImageFont

    rows: list[dict[str, str]] = []
    with metrics_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows.extend(reader)
    if not rows:
        raise RuntimeError("no metrics rows available for moving-slice diagnostics")

    grouped: dict[int, list[dict[str, str]]] = {}
    x_values = [_float_value(row, "z") for row in rows]
    x_values = [value for value in x_values if math.isfinite(value)]
    if not x_values:
        raise RuntimeError("metrics rows have no finite z/axial coordinates")
    x_min, x_max = min(x_values), max(x_values)
    for row in rows:
        try:
            frame = int(float(row["frame"]))
        except (KeyError, ValueError):
            continue
        grouped.setdefault(frame, []).append(row)

    frame_numbers = sorted(grouped)
    if len(frame_numbers) > max_frames:
        keep_indices = [
            round(index * (len(frame_numbers) - 1) / (max_frames - 1))
            for index in range(max_frames)
        ]
        frame_numbers = [frame_numbers[index] for index in keep_indices]

    selected: list[dict[str, str]] = []
    for index, frame in enumerate(frame_numbers):
        progress = index / max(1, len(frame_numbers) - 1)
        target_x = x_min + (0.08 + 0.84 * progress) * (x_max - x_min)
        candidates = grouped[frame]
        candidates = [
            row for row in candidates
            if _float_value(row, "particle_count", 0.0) > 0
            and "zero_area_proxy" not in row.get("quality_flags", "")
        ] or grouped[frame]
        selected.append(min(candidates, key=lambda row: abs(_float_value(row, "z") - target_x)))

    moving_csv = paths.metrics_dir / f"{stem}_moving_slice_diagnostics.csv"
    with moving_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0].keys()) + ["slice_path_note"])
        writer.writeheader()
        for row in selected:
            out = dict(row)
            out["slice_path_note"] = (
                "Moving diagnostic station selected from per-frame cross-section metrics; "
                "this is not material particle tagging."
            )
            writer.writerow(out)

    frames_dir = paths.output_root / "moving_slice_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in frames_dir.glob("frame_*.png"):
        stale.unlink()

    try:
        regular = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    except OSError:
        regular = small = bold = ImageFont.load_default()

    proxy_values = [
        _float_value(row, "velocity_fluctuation_energy_proxy", 0.0) for row in selected
    ]
    vmax = max([value for value in proxy_values if math.isfinite(value)] or [1.0])
    width_max = max(
        [
            max(_float_value(row, "width_y", 0.0), _float_value(row, "width_z", 0.0))
            for row in selected
        ]
        or [1.0]
    )
    x_range = max(1.0e-9, x_max - x_min)

    for index, row in enumerate(selected):
        image = Image.new("RGB", (1280, 720), (8, 14, 20))
        draw = ImageDraw.Draw(image, "RGBA")
        accent = (90, 205, 235, 255)
        draw.rectangle((0, 0, 1280, 86), fill=(12, 24, 34, 255))
        draw.text((52, 26), "Moving downstream cross-section diagnostic", font=bold, fill=(238, 248, 250))
        draw.text((52, 62), "Metric slice follows the streamwise development; not material particle tagging", font=small, fill=(190, 212, 220))

        x_value = _float_value(row, "z")
        frame = row.get("frame", "")
        particle_count = int(_float_value(row, "particle_count", 0.0))
        width_y = _float_value(row, "width_y", 0.0)
        width_z = _float_value(row, "width_z", 0.0)
        width_y = width_y if math.isfinite(width_y) and width_y > 0 else 0.0
        width_z = width_z if math.isfinite(width_z) and width_z > 0 else 0.0
        aspect = _float_value(row, "aspect_ratio")
        orientation = _float_value(row, "orientation_deg_yz")
        speed_mean = _float_value(row, "speed_mean")
        pressure_mean = _float_value(row, "pressure_mean")
        proxy = _float_value(row, "velocity_fluctuation_energy_proxy", 0.0)
        quality = row.get("quality_flags", "")

        axis_left, axis_right, axis_y = 90, 760, 610
        draw.line((axis_left, axis_y, axis_right, axis_y), fill=(110, 150, 165, 255), width=4)
        progress_x = axis_left + int((x_value - x_min) / x_range * (axis_right - axis_left))
        draw.ellipse((progress_x - 10, axis_y - 10, progress_x + 10, axis_y + 10), fill=accent)
        draw.text((axis_left, axis_y + 18), f"x={x_min:.2f} m", font=small, fill=(170, 190, 200))
        draw.text((axis_right - 90, axis_y + 18), f"x={x_max:.2f} m", font=small, fill=(170, 190, 200))

        panel = (815, 125, 1225, 575)
        draw.rounded_rectangle(panel, radius=14, fill=(18, 31, 42, 238), outline=(85, 135, 155, 200), width=2)
        draw.text((845, 150), "y-z section proxy", font=regular, fill=(230, 242, 246))
        cx, cy = 1020, 355
        scale = 245.0 / max(width_max, 1.0e-6)
        half_w = max(8, width_y * scale * 0.5)
        half_h = max(8, width_z * scale * 0.5)
        color = _velocity_proxy_color(proxy, vmax)
        rect_x0, rect_x1 = sorted((cx - half_w, cx + half_w))
        rect_y0, rect_y1 = sorted((cy - half_h, cy + half_h))
        rect_radius = min(10, max(0, int(min(rect_x1 - rect_x0, rect_y1 - rect_y0) * 0.25)))
        if rect_radius >= 2:
            draw.rounded_rectangle(
                (rect_x0, rect_y0, rect_x1, rect_y1),
                radius=rect_radius,
                fill=(*color, 125),
                outline=(232, 248, 252, 235),
                width=3,
            )
        else:
            draw.rectangle(
                (rect_x0, rect_y0, rect_x1, rect_y1),
                fill=(*color, 125),
                outline=(232, 248, 252, 235),
                width=3,
            )
        if math.isfinite(orientation):
            length = max(half_w, half_h) * 0.9
            theta = math.radians(orientation)
            draw.line(
                (
                    cx - length * math.cos(theta),
                    cy - length * math.sin(theta),
                    cx + length * math.cos(theta),
                    cy + length * math.sin(theta),
                ),
                fill=(255, 238, 150, 230),
                width=3,
            )
        draw.text((845, 520), "color: velocity-fluctuation energy proxy", font=small, fill=(190, 212, 220))

        text = [
            f"frame: {frame}",
            f"slice x: {x_value:.3f} m",
            f"particles in slice: {particle_count:,}",
            f"width_y x width_z: {width_y:.3f} x {width_z:.3f} m",
            f"aspect ratio: {aspect:.3f}" if math.isfinite(aspect) else "aspect ratio: n/a",
            f"orientation: {orientation:.1f} deg" if math.isfinite(orientation) else "orientation: n/a",
            f"speed mean: {speed_mean:.2f} m/s" if math.isfinite(speed_mean) else "speed mean: n/a",
            f"pressure mean: {pressure_mean:.1f}" if math.isfinite(pressure_mean) else "pressure mean: n/a",
            f"fluctuation proxy: {proxy:.3f}",
            f"quality: {quality}",
        ]
        for line_index, line in enumerate(text):
            draw.text((90, 130 + 42 * line_index), line, font=regular, fill=(228, 238, 242))

        image.save(frames_dir / f"frame_{index:04d}.png")

    moving_mp4 = paths.output_root / f"{stem}_moving_slice_cross_section.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%04d.png"),
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(moving_mp4),
        ],
        paths.logs_dir / "10_ffmpeg_moving_slice_diagnostics.log",
        300,
    )
    return {
        "moving_slice_csv": str(moving_csv),
        "moving_slice_mp4": str(moving_mp4),
        "moving_slice_png_frames": len(selected),
        "moving_slice_frame_dir": str(frames_dir),
    }


def _idp_array(vtk: VtkParticles) -> list[int] | None:
    for name in ("Idp", "idp", "IDP", "id"):
        values = vtk.arrays.get(name)
        if values and not isinstance(values[0], tuple):
            return [int(value) for value in values]  # type: ignore[arg-type]
    return None


def _surface_segments_at_x(surface: VtkSurface, x_plane: float) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    eps = 1.0e-8
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for tri in surface.polygons:
        pts = [surface.points[index] for index in tri]
        hits: list[tuple[float, float]] = []
        for first, second in ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0])):
            d0 = first[0] - x_plane
            d1 = second[0] - x_plane
            if abs(d0) <= eps and abs(d1) <= eps:
                hits.extend([(first[1], first[2]), (second[1], second[2])])
            elif abs(d0) <= eps:
                hits.append((first[1], first[2]))
            elif abs(d1) <= eps:
                hits.append((second[1], second[2]))
            elif d0 * d1 < 0.0:
                t = (x_plane - first[0]) / (second[0] - first[0])
                y = first[1] + t * (second[1] - first[1])
                z = first[2] + t * (second[2] - first[2])
                hits.append((y, z))
        unique: list[tuple[float, float]] = []
        seen: set[tuple[int, int]] = set()
        for hit in hits:
            key = (round(hit[0] * 1.0e7), round(hit[1] * 1.0e7))
            if key not in seen:
                seen.add(key)
                unique.append(hit)
        if len(unique) >= 2:
            segments.append((unique[0], unique[1]))
    return segments


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def cross(origin: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _polygon_area(points: list[tuple[float, float]]) -> float:
    hull = _convex_hull(points)
    if len(hull) < 3:
        return math.nan
    area = 0.0
    for index, point in enumerate(hull):
        next_point = hull[(index + 1) % len(hull)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(area) * 0.5


def _select_tracked_particle(
    paths: Paths,
    frame_numbers: list[int],
) -> tuple[int | None, dict[int, tuple[float, float, float]], dict[int, int], str]:
    maps: dict[int, dict[int, tuple[float, float, float]]] = {}
    counts: dict[int, int] = {}
    latest = frame_numbers[-1]
    latest_vtk = _parse_vtk_particles(paths.particles_dir / f"PartFluid_{latest:04d}.vtk")
    latest_ids = _idp_array(latest_vtk)
    if latest_ids is None:
        return None, {}, {}, "Idp not exported"

    for frame in frame_numbers:
        vtk = _parse_vtk_particles(paths.particles_dir / f"PartFluid_{frame:04d}.vtk")
        ids = _idp_array(vtk)
        if ids is None:
            continue
        frame_map = {pid: point for pid, point in zip(ids, vtk.points, strict=False)}
        maps[frame] = frame_map
        for pid in frame_map:
            counts[pid] = counts.get(pid, 0) + 1

    if not maps:
        return None, {}, {}, "no Idp maps could be built"

    xs = [point[0] for point in latest_vtk.points]
    x_min, x_max = min(xs), max(xs)
    y_mean = _mean([point[1] for point in latest_vtk.points])
    z_mean = _mean([point[2] for point in latest_vtk.points])
    candidates: list[tuple[tuple[float, float, float], int]] = []
    for pid, point in zip(latest_ids, latest_vtk.points, strict=False):
        if point[0] < x_min + 0.18 * (x_max - x_min):
            continue
        count = counts.get(pid, 0)
        if count < 2:
            continue
        trajectory = [maps[frame][pid] for frame in frame_numbers if pid in maps.get(frame, {})]
        span = max(p[0] for p in trajectory) - min(p[0] for p in trajectory)
        center_distance = math.hypot(point[1] - y_mean, point[2] - z_mean)
        candidates.append(((-count, -span, center_distance), pid))
    if not candidates:
        return None, {}, counts, "no centerline-like final-frame Idp survived multiple selected frames"
    _, chosen = min(candidates)
    trace = {
        frame: frame_map[chosen]
        for frame, frame_map in maps.items()
        if chosen in frame_map
    }
    return chosen, trace, counts, "tracked Idp selected from late-frame centerline candidates"


def _write_surface_cut_diagnostics(
    paths: Paths,
    frame_numbers: list[int],
    fps: int,
) -> dict[str, str | int | bool]:
    from PIL import Image, ImageDraw, ImageFont

    available_frames = [
        frame for frame in frame_numbers
        if (paths.surface_dir / f"Surface_{frame:04d}.vtk").exists()
        and (paths.particles_dir / f"PartFluid_{frame:04d}.vtk").exists()
    ]
    if not available_frames:
        raise RuntimeError("no matched particle/surface frames for surface cuts")

    tracked_id, trace, counts, particle_note = _select_tracked_particle(paths, available_frames)
    rows: list[dict[str, object]] = []
    render_items: list[tuple[int, list[tuple[tuple[float, float], tuple[float, float]]], dict[str, object]]] = []
    for frame in available_frames:
        quality: list[str] = []
        if tracked_id is None or frame not in trace:
            quality.append("tracked_particle_missing")
            continue
        particle = trace[frame]
        surface = _parse_vtk_surface(paths.surface_dir / f"Surface_{frame:04d}.vtk")
        segments = _surface_segments_at_x(surface, particle[0])
        cut_points = [point for segment in segments for point in segment]
        if len(cut_points) < 3:
            quality.append("sparse_or_open_surface_cut")
        ys = [point[0] for point in cut_points]
        zs = [point[1] for point in cut_points]
        width_y = max(ys) - min(ys) if ys else math.nan
        width_z = max(zs) - min(zs) if zs else math.nan
        area = _polygon_area(cut_points) if cut_points else math.nan
        aspect, orientation = _principal_metrics(ys, zs) if len(cut_points) >= 3 else (math.nan, math.nan)
        row = {
            "frame": frame,
            "particle_id": tracked_id,
            "particle_x": particle[0],
            "particle_y": particle[1],
            "particle_z": particle[2],
            "cut_station_x": particle[0],
            "surface_segments": len(segments),
            "cut_points": len(cut_points),
            "area_proxy": area,
            "Ahat": area / NOZZLE_AREA if math.isfinite(area) and area > 0 else math.nan,
            "width_y": width_y,
            "width_z": width_z,
            "aspect_ratio": aspect,
            "orientation_deg_yz": orientation,
            "quality_flags": ";".join(quality) if quality else "ok",
        }
        rows.append(row)
        render_items.append((frame, segments, row))

    csv_path = paths.metrics_dir / "rectangular_jet_v4_surface_cut_diagnostics.csv"
    json_path = paths.metrics_dir / "rectangular_jet_v4_surface_cut_diagnostics.json"
    paths.metrics_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "frame",
        "particle_id",
        "quality_flags",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    frame_dir = paths.output_root / "surface_cut_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for stale in frame_dir.glob("frame_*.png"):
        stale.unlink()
    try:
        regular = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 23)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    except OSError:
        regular = small = bold = ImageFont.load_default()

    all_cut_points = [
        point
        for _, segments, _ in render_items
        for segment in segments
        for point in segment
    ]
    y_values = [point[0] for point in all_cut_points] or [-1.0, 1.0]
    z_values = [point[1] for point in all_cut_points] or [-1.0, 1.0]
    y_min, y_max = min(y_values), max(y_values)
    z_min, z_max = min(z_values), max(z_values)
    span = max(y_max - y_min, z_max - z_min, 1.0e-6)
    pad = span * 0.18
    y_min -= pad
    y_max += pad
    z_min -= pad
    z_max += pad

    def project(point: tuple[float, float]) -> tuple[int, int]:
        y, z = point
        px = 720 + int((y - y_min) / max(1.0e-9, y_max - y_min) * 470)
        py = 575 - int((z - z_min) / max(1.0e-9, z_max - z_min) * 420)
        return px, py

    for index, (frame, segments, row) in enumerate(render_items):
        image = Image.new("RGB", (1280, 720), (8, 14, 20))
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle((0, 0, 1280, 92), fill=(12, 24, 34, 255))
        draw.text((52, 24), "Tracked-particle surface cut", font=bold, fill=(238, 248, 250))
        draw.text(
            (52, 62),
            "Plane normal to +x intersects the reconstructed IsoSurface at the tracked Idp station",
            font=small,
            fill=(190, 212, 220),
        )
        panel = (680, 130, 1225, 610)
        draw.rounded_rectangle(panel, radius=14, fill=(18, 31, 42, 238), outline=(85, 135, 155, 220), width=2)
        draw.text((706, 150), "actual y-z surface intersection", font=regular, fill=(230, 242, 246))
        draw.line((720, 575, 1190, 575), fill=(110, 150, 165, 180), width=2)
        draw.line((720, 575, 720, 155), fill=(110, 150, 165, 180), width=2)
        for first, second in segments:
            draw.line((*project(first), *project(second)), fill=(96, 220, 245, 235), width=3)

        text = [
            f"frame: {frame}",
            f"tracked particle id: {row['particle_id']}",
            f"particle x/y/z: {row['particle_x']:.3f}, {row['particle_y']:.3f}, {row['particle_z']:.3f}",
            f"surface segments: {row['surface_segments']}",
            f"cut points: {row['cut_points']}",
            f"area proxy: {row['area_proxy']:.5f}" if isinstance(row["area_proxy"], float) and math.isfinite(row["area_proxy"]) else "area proxy: n/a",
            f"Ahat: {row['Ahat']:.4f}" if isinstance(row["Ahat"], float) and math.isfinite(row["Ahat"]) else "Ahat: n/a",
            f"width_y x width_z: {row['width_y']:.4f} x {row['width_z']:.4f}",
            f"aspect ratio: {row['aspect_ratio']:.3f}" if isinstance(row["aspect_ratio"], float) and math.isfinite(row["aspect_ratio"]) else "aspect ratio: n/a",
            f"orientation: {row['orientation_deg_yz']:.1f} deg" if isinstance(row["orientation_deg_yz"], float) and math.isfinite(row["orientation_deg_yz"]) else "orientation: n/a",
            f"quality: {row['quality_flags']}",
        ]
        for line_index, line in enumerate(text):
            draw.text((70, 135 + line_index * 40), line, font=regular, fill=(228, 238, 242))
        image.save(frame_dir / f"frame_{index:04d}.png")

    mp4_path = paths.output_root / "rectangular_jet_v4_surface_cut_cross_sections.mp4"
    if render_items:
        _run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(frame_dir / "frame_%04d.png"),
                "-vf",
                "format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "20",
                "-movflags",
                "+faststart",
                str(mp4_path),
            ],
            paths.logs_dir / "11_ffmpeg_surface_cut_diagnostics.log",
            300,
        )
    summary = {
        "status": "success" if rows else "blocked",
        "tracked_particle_id": tracked_id,
        "particle_note": particle_note,
        "trace_frames": sorted(trace),
        "selected_surface_frames": available_frames,
        "cut_rows": len(rows),
        "true_surface_intersection": bool(rows),
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "mp4_path": str(mp4_path) if rows else "",
        "frame_dir": str(frame_dir),
        "idp_presence_counts_considered": len(counts),
        "caveat": "Surface cuts are plane/IsoSurface intersections driven by a traced Idp when available.",
    }
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def _assemble_titled_video(
    paths: Paths,
    rendered: list[Path],
    fps: int,
    stem: str,
    title: str,
    subtitle: str,
    particle_text: str,
    render_text: str,
    *,
    closing_title: str = "Particle/velocity visualization and preliminary slice metrics",
    closing_subtitle: str = "Geometry proxy and visualization workflow; not validation",
    platform_text: str = "DualSPHysics v5.4 GPU | headless Blender | ffmpeg",
) -> Path:
    source_dir = paths.output_root / f"{stem}_source_frames"
    source_dir.mkdir(parents=True, exist_ok=True)
    for stale in source_dir.glob("frame_*.png"):
        stale.unlink()
    for index, frame in enumerate(rendered):
        shutil.copy2(frame, source_dir / f"frame_{index:04d}.png")
    showcase_mp4 = paths.output_root / f"{stem}.mp4"
    _run(
        [
            "python3",
            str(paths.repo_root / "scripts/assemble_dambreak_video.py"),
            "--input-dir",
            str(source_dir),
            "--input-pattern",
            "frame_*.png",
            "--min-input-frames",
            str(len(rendered)),
            "--frames-dir",
            str(paths.output_root / f"{stem}_frames_titled"),
            "--output",
            str(showcase_mp4),
            "--fps",
            str(fps),
            "--width",
            "1280",
            "--height",
            "720",
            "--title",
            title,
            "--subtitle",
            subtitle,
            "--closing-title",
            closing_title,
            "--closing-subtitle",
            closing_subtitle,
            "--particle-text",
            particle_text,
            "--platform-text",
            platform_text,
            "--render-text",
            render_text,
            "--title-duration",
            "4",
            "--closing-duration",
            "4",
            "--sim-frame-duration",
            str(1.0 / fps),
        ],
        paths.logs_dir / f"09_assemble_{stem}.log",
        300,
    )
    return showcase_mp4


def _assemble_video(paths: Paths, rendered: list[Path], fps: int) -> tuple[Path, Path]:
    clean_mp4 = _assemble_clean_video(
        paths,
        rendered,
        fps,
        "rectangular_highspeed_jet_proxy_clean",
    )
    contact_sheet = _make_contact_sheet(
        paths,
        rendered,
        "rectangular_highspeed_jet_proxy_contact_sheet",
    )
    showcase_mp4 = _assemble_titled_video(
        paths,
        rendered,
        fps,
        "rectangular_highspeed_jet_proxy_showcase",
        "Rectangular High-Speed Inlet Jet Proxy",
        "Modified DualSPHysics Box4Inlet3D | geometry proxy, not validation",
        "Single rectangular inlet retained from Box4Inlet3D",
        "Velocity-colored particles; optional IsoSurface overlay",
    )
    return showcase_mp4, contact_sheet


def _render_upgrade_package(
    paths: Paths,
    frames: list[int],
    timeout_seconds: int,
    fps: int,
    color_max: float,
) -> dict[str, str | int]:
    particle_frames = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="particle",
        camera_preset="isometric",
        output_prefix="upgrade_particle_isometric",
        color_max=color_max,
        samples=64,
    )
    surface_frames = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="surface",
        camera_preset="close",
        output_prefix="upgrade_surface_close",
        color_max=color_max,
        samples=72,
    )
    velocity_frames = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="velocity",
        camera_preset="side",
        output_prefix="upgrade_velocity_side",
        color_max=color_max,
        samples=64,
    )
    particle_mp4 = _assemble_clean_video(
        paths,
        particle_frames,
        fps,
        "rectangular_jet_upgrade_particle_provenance_clean",
    )
    surface_mp4 = _assemble_clean_video(
        paths,
        surface_frames,
        fps,
        "rectangular_jet_upgrade_surface_hero_clean",
    )
    velocity_mp4 = _assemble_clean_video(
        paths,
        velocity_frames,
        fps,
        "rectangular_jet_upgrade_velocity_postprocess_clean",
    )
    combined = [*particle_frames, *surface_frames, *velocity_frames]
    contact_sheet = _make_contact_sheet(
        paths,
        combined,
        "rectangular_jet_upgrade_multiview_contact_sheet",
    )
    final_mp4 = _assemble_titled_video(
        paths,
        combined,
        fps,
        "rectangular_jet_upgrade_scientific_showcase",
        "Rectangular High-Speed Inlet Jet Proxy",
        "Long-domain DualSPHysics single-phase geometry proxy | not validation",
        "Particle provenance | surface reconstruction | velocity magnitude",
        "Fixed multiview render | IsoSurface and PartVTK post-processing",
    )
    return {
        "particle_clean_mp4": str(particle_mp4),
        "surface_hero_mp4": str(surface_mp4),
        "velocity_postprocess_mp4": str(velocity_mp4),
        "final_showcase_mp4": str(final_mp4),
        "contact_sheet": str(contact_sheet),
        "particle_frames": len(particle_frames),
        "surface_frames": len(surface_frames),
        "velocity_frames": len(velocity_frames),
    }


def _render_v2_package(
    paths: Paths,
    frames: list[int],
    timeout_seconds: int,
    fps: int,
    color_max: float,
) -> dict[str, str | int]:
    particle_wide = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="particle",
        camera_preset="front-ortho",
        output_prefix="v2_accept_particle_wide",
        color_max=color_max,
        samples=64,
        camera_lens=50,
        marker_scale=0.85,
        marker_style="icosahedron",
        fluid_stride=2,
        iso_color="#118BB855",
        background_color="#EEF4F8FF",
        light_energy=3200,
        light_size=2.4,
    )
    surface_wide = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="surface",
        camera_preset="isometric",
        output_prefix="v2_accept_surface_wide",
        color_max=color_max,
        samples=96,
        camera_lens=42,
        marker_scale=0.8,
        iso_color="#05AEEFFF",
        fluid_color="#66DFFFF0",
        background_color="#EEF4F8FF",
        light_energy=4200,
        light_size=2.6,
    )
    surface_close = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="surface",
        camera_preset="close",
        output_prefix="v2_accept_surface_hero",
        color_max=color_max,
        samples=96,
        camera_lens=36,
        marker_scale=0.8,
        iso_color="#00B8F4FF",
        fluid_color="#7FE8FFFF",
        background_color="#EEF4F8FF",
        light_energy=4600,
        light_size=2.8,
    )
    velocity_side = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="velocity",
        camera_preset="front-ortho",
        output_prefix="v2_accept_velocity_front",
        color_max=color_max,
        samples=64,
        camera_lens=48,
        marker_scale=0.95,
        marker_style="octahedron",
        fluid_stride=2,
        iso_color="#108ABF55",
        background_color="#EEF4F8FF",
        light_energy=3200,
        light_size=2.4,
    )
    if not surface_wide or not surface_close:
        raise RuntimeError("v2 render package requires successful IsoSurface frames")

    particle_mp4 = _assemble_clean_video(
        paths,
        particle_wide,
        fps,
        "rectangular_jet_v2_accepted_particle_provenance_clean",
    )
    surface_wide_mp4 = _assemble_clean_video(
        paths,
        surface_wide,
        fps,
        "rectangular_jet_v2_accepted_surface_wide_clean",
    )
    surface_close_mp4 = _assemble_clean_video(
        paths,
        surface_close,
        fps,
        "rectangular_jet_v2_accepted_surface_hero_clean",
    )
    velocity_mp4 = _assemble_clean_video(
        paths,
        velocity_side,
        fps,
        "rectangular_jet_v2_accepted_velocity_postprocess_clean",
    )
    combined = [*particle_wide, *surface_wide, *surface_close, *velocity_side]
    contact_sheet = _make_contact_sheet(
        paths,
        _contact_sheet_samples(particle_wide, surface_wide, surface_close, velocity_side),
        "rectangular_jet_v2_accepted_multiview_contact_sheet",
    )
    final_mp4 = _assemble_titled_video(
        paths,
        combined,
        fps,
        "rectangular_jet_v2_accepted_scientific_demonstration",
        "Rectangular Inlet Jet Geometry Proxy v2",
        "Long-domain single-phase DualSPHysics demonstration | not validation",
        "Particle provenance | IsoSurface hero | velocity magnitude",
        "Fixed multiview render | open downstream boundary in copied case",
    )
    return {
        "particle_clean_mp4": str(particle_mp4),
        "surface_wide_mp4": str(surface_wide_mp4),
        "surface_hero_mp4": str(surface_close_mp4),
        "velocity_postprocess_mp4": str(velocity_mp4),
        "final_showcase_mp4": str(final_mp4),
        "contact_sheet": str(contact_sheet),
        "particle_frames": len(particle_wide),
        "surface_wide_frames": len(surface_wide),
        "surface_hero_frames": len(surface_close),
        "velocity_frames": len(velocity_side),
        "total_source_frames": len(combined),
    }


def _render_v3_package(
    paths: Paths,
    frames: list[int],
    timeout_seconds: int,
    fps: int,
    color_max: float,
    pressure_color_max: float,
    metrics_csv: Path,
    cycles_surface: bool,
) -> dict[str, str | int | bool]:
    last_vtk = _parse_vtk_particles(paths.particles_dir / f"PartFluid_{frames[-1]:04d}.vtk")
    pressure_available = "Press" in last_vtk.arrays
    surface_engine = "cycles" if cycles_surface else "eevee"

    material_test_frames = [frames[0], frames[-1]] if len(frames) > 1 else [frames[0]]
    clear_tests = _render_frames(
        paths,
        material_test_frames,
        timeout_seconds,
        mode="surface",
        camera_preset="close",
        output_prefix="v3_material_test_clear_water_v2",
        samples=32 if cycles_surface else 96,
        camera_lens=34,
        iso_color="#F1FCFF40",
        fluid_color="#F1FCFF40",
        surface_material="clear-water",
        render_engine=surface_engine,
        add_floor=True,
        background_color="#F5F7F7FF",
        light_energy=5200,
        light_size=3.1,
    )
    tinted_tests = _render_frames(
        paths,
        material_test_frames,
        timeout_seconds,
        mode="surface",
        camera_preset="close",
        output_prefix="v3_material_test_light_tint_v2",
        samples=32 if cycles_surface else 96,
        camera_lens=34,
        iso_color="#B7EEF866",
        fluid_color="#B7EEF866",
        surface_material="tinted-water",
        render_engine=surface_engine,
        add_floor=True,
        background_color="#F5F7F7FF",
        light_energy=5200,
        light_size=3.1,
    )

    particle_wide = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="particle",
        camera_preset="front-ortho",
        output_prefix="v3_particle_provenance_wide",
        color_max=color_max,
        samples=72,
        camera_lens=48,
        marker_scale=0.78,
        marker_style="icosahedron",
        fluid_stride=2,
        iso_color="#2AA8CC40",
        background_color="#EEF3F5FF",
        light_energy=3600,
        light_size=2.5,
    )
    surface_wide = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="surface",
        camera_preset="front-ortho",
        output_prefix="v3_tinted_water_surface_wide",
        color_max=color_max,
        samples=48 if cycles_surface else 112,
        camera_lens=44,
        marker_scale=0.7,
        iso_color="#B7EEF878",
        fluid_color="#B7EEF878",
        surface_material="tinted-water",
        render_engine=surface_engine,
        add_floor=True,
        background_color="#F5F7F7FF",
        light_energy=5600,
        light_size=3.4,
    )
    surface_hero = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="surface",
        camera_preset="front-ortho",
        output_prefix="v3_tinted_water_surface_hero_zoom",
        color_max=color_max,
        samples=56 if cycles_surface else 128,
        camera_lens=42,
        ortho_scale=2.1,
        marker_scale=0.7,
        iso_color="#B7EEF878",
        fluid_color="#B7EEF878",
        surface_material="tinted-water",
        render_engine=surface_engine,
        add_floor=True,
        background_color="#F5F7F7FF",
        light_energy=6200,
        light_size=3.6,
    )
    velocity_view = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="velocity",
        camera_preset="front-ortho",
        output_prefix="v3_velocity_magnitude_front",
        color_max=color_max,
        samples=72,
        camera_lens=48,
        marker_scale=0.9,
        marker_style="octahedron",
        fluid_stride=2,
        iso_color="#AEEAF040",
        background_color="#EEF3F5FF",
        light_energy=3400,
        light_size=2.4,
    )
    pressure_view: list[Path] = []
    if pressure_available:
        pressure_view = _render_frames(
            paths,
            frames,
            timeout_seconds,
            mode="analysis",
            camera_preset="front-ortho",
            output_prefix="v3_pressure_front",
            color_by="Press",
            color_min=0.0,
            color_max=pressure_color_max,
            samples=72,
            camera_lens=48,
            marker_scale=0.9,
            marker_style="octahedron",
            fluid_stride=2,
            iso_color="#AEEAF040",
            background_color="#EEF3F5FF",
            light_energy=3400,
            light_size=2.4,
        )
    moving_slice = _write_moving_slice_diagnostics(paths, metrics_csv, fps)
    moving_slice_frames = sorted(
        Path(str(moving_slice["moving_slice_frame_dir"])).glob("frame_*.png")
    )

    if not surface_wide or not surface_hero:
        raise RuntimeError("v3 render package requires successful clear-water IsoSurface frames")

    particle_mp4 = _assemble_clean_video(
        paths,
        particle_wide,
        fps,
        "rectangular_jet_v3_particle_provenance_clean",
    )
    surface_wide_mp4 = _assemble_clean_video(
        paths,
        surface_wide,
        fps,
        "rectangular_jet_v3_tinted_water_surface_wide_clean",
    )
    surface_hero_mp4 = _assemble_clean_video(
        paths,
        surface_hero,
        fps,
        "rectangular_jet_v3_tinted_water_surface_hero_clean",
    )
    velocity_mp4 = _assemble_clean_video(
        paths,
        velocity_view,
        fps,
        "rectangular_jet_v3_velocity_magnitude_clean",
    )
    pressure_mp4 = ""
    if pressure_view:
        pressure_mp4 = str(
            _assemble_clean_video(
                paths,
                pressure_view,
                fps,
                "rectangular_jet_v3_pressure_clean",
            )
        )

    combined = [
        *particle_wide,
        *surface_wide,
        *surface_hero,
        *velocity_view,
        *pressure_view,
        *moving_slice_frames,
    ]
    contact_sheet = _make_contact_sheet(
        paths,
        _contact_sheet_samples(
            particle_wide,
            surface_wide,
            surface_hero,
            velocity_view,
            pressure_view,
            moving_slice_frames,
        ),
        "rectangular_jet_v3_multiview_contact_sheet",
    )
    final_mp4 = _assemble_titled_video(
        paths,
        combined,
        fps,
        "rectangular_jet_v3_streamwise_gravity_scientific_demonstration",
        "Rectangular Jet Proxy v3: Streamwise Gravity",
        (
            "Fermín Franco-Medrano, Ph.D. | UABC Ensenada Campus · IMI, Kyushu University | "
            "DualSPHysics v5.4 -> PartVTK/IsoSurface -> Blender -> ffmpeg"
        ),
        "U=20 m/s target | g=(+9.81,0,0) streamwise | particle, surface, analysis views",
        "Transparent-water IsoSurface hero | velocity, pressure, and moving-slice proxy diagnostics",
        closing_title="Case stats: streamwise gravity, pressure export, moving cross-section diagnostics",
        closing_subtitle=(
            "Single-phase rectangular jet geometry proxy and visualization workflow; not atomized spray, "
            "validation, production CFD, or experimental agreement"
        ),
        platform_text="DualSPHysics v5.4 GPU | Blender 4.5.10 LTS | ffmpeg | RTX 5070 Laptop GPU",
    )
    return {
        "particle_clean_mp4": str(particle_mp4),
        "surface_wide_mp4": str(surface_wide_mp4),
        "surface_hero_mp4": str(surface_hero_mp4),
        "velocity_postprocess_mp4": str(velocity_mp4),
        "pressure_postprocess_mp4": pressure_mp4,
        "moving_slice_mp4": str(moving_slice["moving_slice_mp4"]),
        "moving_slice_csv": str(moving_slice["moving_slice_csv"]),
        "final_showcase_mp4": str(final_mp4),
        "contact_sheet": str(contact_sheet),
        "particle_frames": len(particle_wide),
        "surface_wide_frames": len(surface_wide),
        "surface_hero_frames": len(surface_hero),
        "velocity_frames": len(velocity_view),
        "pressure_frames": len(pressure_view),
        "moving_slice_png_frames": int(moving_slice["moving_slice_png_frames"]),
        "total_source_frames": len(combined),
        "pressure_available": pressure_available,
        "surface_material_variants_tested": "clear-water,tinted-water",
        "selected_surface_material": "tinted-water",
        "transparent_water_material": True,
        "opaque_blue_surface_avoided": True,
        "cycles_attempted": cycles_surface,
        "cycles_limitation": "" if cycles_surface else "Eevee used unless --cycles-surface is enabled for bounded runtime.",
        "surface_render_engine": surface_engine,
        "clear_material_test_frames": len(clear_tests),
        "tinted_material_test_frames": len(tinted_tests),
    }


def _render_final_surface_inspection(
    paths: Paths,
    final_frame: int,
    timeout_seconds: int,
    fps: int,
    cycles_surface: bool,
) -> dict[str, str | int]:
    engine = "cycles" if cycles_surface else "eevee"
    steps = [
        ("v4_polished_inspection_00_full_surface", "front-ortho", 0.52, 0.52, 0.52, 0.82, 64),
        ("v4_polished_inspection_01_oblique_surface", "isometric", 0.55, 0.52, 0.52, 0.56, 52),
        ("v4_polished_inspection_02_probe_close", "close", 0.62, 0.50, 0.50, 0.34, 36),
        ("v4_polished_inspection_03_return_to_nozzle", "close", 0.12, 0.50, 0.50, 0.24, 32),
    ]
    inspection_frames: list[Path] = []
    for prefix, preset, tx, ty, tz, span_scale, lens in steps:
        frames = _render_frames(
            paths,
            [final_frame],
            timeout_seconds,
            mode="surface",
            camera_preset=preset,
            output_prefix=prefix,
            samples=64 if cycles_surface else 128,
            camera_lens=lens,
            camera_target_x_fraction=tx,
            camera_target_y_fraction=ty,
            camera_target_z_fraction=tz,
            camera_span_scale=span_scale,
            iso_color="#D6FFF0B0",
            fluid_color="#D6FFF0B0",
            surface_material="tinted-water",
            render_engine=engine,
            add_studio_walls=True,
            background_color="#F1F5F4FF",
            light_energy=11000,
            light_size=4.2,
        )
        inspection_frames.extend(frames)
    mp4 = _assemble_clean_video(
        paths,
        inspection_frames,
        max(1, min(fps, 4)),
        "rectangular_jet_v4_final_surface_inspection_clean",
    )
    return {
        "inspection_mp4": str(mp4),
        "inspection_frames": len(inspection_frames),
        "inspection_frame_dir": str(paths.output_root / "rectangular_jet_v4_final_surface_inspection_clean_frames_canonical"),
    }


def _render_v4_package(
    paths: Paths,
    frames: list[int],
    timeout_seconds: int,
    fps: int,
    color_max: float,
    pressure_color_max: float,
    metrics_csv: Path,
    cycles_surface: bool,
) -> dict[str, str | int | bool]:
    last_vtk = _parse_vtk_particles(paths.particles_dir / f"PartFluid_{frames[-1]:04d}.vtk")
    pressure_available = "Press" in last_vtk.arrays
    engine = "cycles" if cycles_surface else "eevee"

    material_test_frames = [frames[0], frames[-1]] if len(frames) > 1 else [frames[0]]
    clear_tests = _render_frames(
        paths,
        material_test_frames,
        timeout_seconds,
        mode="surface",
        camera_preset="close",
        output_prefix="v4_material_test_clear_water",
        samples=48 if cycles_surface else 128,
        camera_lens=34,
        camera_target_x_fraction=0.58,
        camera_span_scale=0.42,
        iso_color="#F2FCFF55",
        fluid_color="#F2FCFF55",
        surface_material="clear-water",
        render_engine=engine,
        add_studio_walls=True,
        background_color="#DDE4E6FF",
        light_energy=7600,
        light_size=3.8,
    )
    tinted_tests = _render_frames(
        paths,
        material_test_frames,
        timeout_seconds,
        mode="surface",
        camera_preset="close",
        output_prefix="v4_polished_material_test_tinted_water",
        samples=48 if cycles_surface else 128,
        camera_lens=34,
        camera_target_x_fraction=0.58,
        camera_span_scale=0.42,
        iso_color="#D6FFF0B0",
        fluid_color="#D6FFF0B0",
        surface_material="tinted-water",
        render_engine=engine,
        add_studio_walls=True,
        background_color="#F1F5F4FF",
        light_energy=11000,
        light_size=4.2,
    )

    particle_wide = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="particle",
        camera_preset="front-ortho",
        output_prefix="v4_particle_provenance_wide",
        color_max=color_max,
        samples=72,
        camera_lens=48,
        marker_scale=0.72,
        marker_style="icosahedron",
        fluid_stride=3,
        iso_color="#2AA8CC35",
        background_color="#EEF3F5FF",
        light_energy=3800,
        light_size=2.6,
    )
    surface_wide = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="surface",
        camera_preset="front-ortho",
        output_prefix="v4_polished_tinted_water_surface_wide",
        color_max=color_max,
        samples=64 if cycles_surface else 144,
        camera_lens=44,
        iso_color="#D6FFF0B0",
        fluid_color="#D6FFF0B0",
        surface_material="tinted-water",
        render_engine=engine,
        add_studio_walls=True,
        background_color="#F1F5F4FF",
        light_energy=11000,
        light_size=4.2,
    )
    surface_hero = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="surface",
        camera_preset="close",
        output_prefix="v4_polished_tinted_water_surface_hero",
        color_max=color_max,
        samples=72 if cycles_surface else 160,
        camera_lens=34,
        camera_target_x_fraction=0.58,
        camera_span_scale=0.42,
        iso_color="#D6FFF0B0",
        fluid_color="#D6FFF0B0",
        surface_material="tinted-water",
        render_engine=engine,
        add_studio_walls=True,
        background_color="#F1F5F4FF",
        light_energy=11800,
        light_size=4.4,
    )
    velocity_view = _render_frames(
        paths,
        frames,
        timeout_seconds,
        mode="velocity",
        camera_preset="front-ortho",
        output_prefix="v4_velocity_magnitude_front",
        color_max=color_max,
        samples=72,
        camera_lens=48,
        marker_scale=0.86,
        marker_style="octahedron",
        fluid_stride=3,
        iso_color="#AEEAF040",
        background_color="#EEF3F5FF",
        light_energy=3600,
        light_size=2.5,
    )
    pressure_view: list[Path] = []
    if pressure_available:
        pressure_view = _render_frames(
            paths,
            frames,
            timeout_seconds,
            mode="analysis",
            camera_preset="front-ortho",
            output_prefix="v4_pressure_front",
            color_by="Press",
            color_min=0.0,
            color_max=pressure_color_max,
            samples=72,
            camera_lens=48,
            marker_scale=0.86,
            marker_style="octahedron",
            fluid_stride=3,
            iso_color="#AEEAF040",
            background_color="#EEF3F5FF",
            light_energy=3600,
            light_size=2.5,
        )

    moving_slice = _write_moving_slice_diagnostics(
        paths,
        metrics_csv,
        fps,
        stem="rectangular_jet_v4",
    )
    proxy_frames = sorted(Path(str(moving_slice["moving_slice_frame_dir"])).glob("frame_*.png"))
    surface_cuts = _write_surface_cut_diagnostics(paths, frames, fps)
    cut_frames = sorted(Path(str(surface_cuts["frame_dir"])).glob("frame_*.png"))
    inspection = _render_final_surface_inspection(paths, frames[-1], timeout_seconds, fps, cycles_surface)
    inspection_frames = sorted(
        Path(str(inspection["inspection_frame_dir"])).glob("frame_*.png")
    )

    if not surface_wide or not surface_hero:
        raise RuntimeError("v4 render package requires successful transparent-water IsoSurface frames")

    particle_mp4 = _assemble_clean_video(
        paths,
        particle_wide,
        fps,
        "rectangular_jet_v4_particle_provenance_clean",
    )
    surface_wide_mp4 = _assemble_clean_video(
        paths,
        surface_wide,
        fps,
        "rectangular_jet_v4_transparent_water_surface_wide_clean",
    )
    surface_hero_mp4 = _assemble_clean_video(
        paths,
        surface_hero,
        fps,
        "rectangular_jet_v4_transparent_water_surface_hero_clean",
    )
    velocity_mp4 = _assemble_clean_video(
        paths,
        velocity_view,
        fps,
        "rectangular_jet_v4_velocity_magnitude_clean",
    )
    pressure_mp4 = ""
    if pressure_view:
        pressure_mp4 = str(
            _assemble_clean_video(
                paths,
                pressure_view,
                fps,
                "rectangular_jet_v4_pressure_clean",
            )
        )

    combined = [
        *particle_wide,
        *surface_wide,
        *surface_hero,
        *velocity_view,
        *pressure_view,
        *proxy_frames,
        *cut_frames,
        *inspection_frames,
    ]
    contact_sheet = _make_contact_sheet(
        paths,
        _contact_sheet_samples(
            particle_wide,
            surface_wide,
            surface_hero,
            velocity_view,
            pressure_view,
            proxy_frames,
            cut_frames,
            inspection_frames,
        ),
        "rectangular_jet_v4_multiview_contact_sheet",
    )
    final_mp4 = _assemble_titled_video(
        paths,
        combined,
        fps,
        "rectangular_jet_v4_extended_surface_scientific_demonstration",
        "Rectangular Jet Proxy v4: Extended Surface Inspection",
        (
            "Fermín Franco-Medrano, Ph.D. | UABC Ensenada Campus · IMI, Kyushu University | "
            "DualSPHysics v5.4 -> PartVTK/IsoSurface -> Blender -> ffmpeg"
        ),
        "U=20 m/s | g=(+9.81,0,0) streamwise | extended run, transparent surface, surface cuts",
        "Particle provenance | transparent IsoSurface | velocity/pressure/proxy diagnostics | tracked-Idp surface cuts",
        closing_title="Extended single-phase rectangular jet geometry proxy",
        closing_subtitle=(
            "Surface inspection and cross-section diagnostics; not atomized spray, validation, "
            "production CFD, or experimental agreement"
        ),
        platform_text="DualSPHysics v5.4 GPU | Blender 4.5.10 LTS | ffmpeg | RTX 5070 Laptop GPU",
    )
    return {
        "particle_clean_mp4": str(particle_mp4),
        "surface_wide_mp4": str(surface_wide_mp4),
        "surface_hero_mp4": str(surface_hero_mp4),
        "velocity_postprocess_mp4": str(velocity_mp4),
        "pressure_postprocess_mp4": pressure_mp4,
        "proxy_energy_mp4": str(moving_slice["moving_slice_mp4"]),
        "proxy_energy_csv": str(moving_slice["moving_slice_csv"]),
        "surface_cut_mp4": str(surface_cuts["mp4_path"]),
        "surface_cut_csv": str(surface_cuts["csv_path"]),
        "surface_cut_json": str(surface_cuts["json_path"]),
        "inspection_mp4": str(inspection["inspection_mp4"]),
        "final_showcase_mp4": str(final_mp4),
        "contact_sheet": str(contact_sheet),
        "particle_frames": len(particle_wide),
        "surface_wide_frames": len(surface_wide),
        "surface_hero_frames": len(surface_hero),
        "velocity_frames": len(velocity_view),
        "pressure_frames": len(pressure_view),
        "proxy_energy_png_frames": int(moving_slice["moving_slice_png_frames"]),
        "surface_cut_rows": int(surface_cuts["cut_rows"]),
        "surface_cut_true_intersection": bool(surface_cuts["true_surface_intersection"]),
        "tracked_particle_id": surface_cuts["tracked_particle_id"],
        "inspection_frames": int(inspection["inspection_frames"]),
        "total_source_frames": len(combined),
        "pressure_available": pressure_available,
        "surface_material_variants_tested": "clear-water,tinted-water",
        "selected_surface_material": "tinted-water",
        "transparent_water_material": True,
        "opaque_blue_surface_avoided": True,
        "cycles_attempted": cycles_surface,
        "cycles_limitation": "" if cycles_surface else "Eevee used unless --cycles-surface is enabled for bounded runtime.",
        "surface_render_engine": engine,
        "studio_walls_enabled": True,
        "clear_material_test_frames": len(clear_tests),
        "tinted_material_test_frames": len(tinted_tests),
    }


def _inventory(paths: Paths, summary: dict) -> None:
    lines = [
        "Rectangular high-speed jet proxy artifact manifest",
        f"Output root: {paths.output_root}",
        f"Case work: {paths.case_work}",
        f"Case output: {paths.case_out}",
        "",
    ]
    for directory in [paths.case_out, paths.particles_dir, paths.surface_dir, paths.render_dir, paths.metrics_dir, paths.logs_dir]:
        if directory.exists():
            lines.append(f"[{directory}]")
            for item in sorted(directory.glob("*")):
                if item.is_file():
                    lines.append(f"{item.stat().st_size:12d}  {item}")
            lines.append("")
    lines.append("Summary JSON:")
    lines.append(json.dumps(summary, indent=2))
    (paths.output_root / "artifact_manifest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-root", type=Path, default=DEFAULT_OFFICIAL_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument(
        "--profile",
        choices=("coarse", "upgraded", "v2", "v3", "v4"),
        default="coarse",
        help=(
            "coarse reproduces the first proxy; upgraded stretches the domain; "
            "v2 uses a longer open-downstream box for accepted-quality renders; "
            "v3 aligns gravity with the +x jet axis and extends the domain; "
            "v4 extends duration/domain and adds surface-cut diagnostics"
        ),
    )
    parser.add_argument("--dp", type=float, help="particle spacing for upgraded profile")
    parser.add_argument("--velocity", type=float, default=4.0)
    parser.add_argument("--time-max", type=float, default=0.8)
    parser.add_argument("--time-out", type=float, default=0.02)
    parser.add_argument("--solver-timeout", type=int, default=900)
    parser.add_argument("--post-timeout", type=int, default=300)
    parser.add_argument("--iso-timeout", type=int, default=180)
    parser.add_argument("--render-timeout", type=int, default=300)
    parser.add_argument("--max-render-frames", type=int, default=12)
    parser.add_argument("--max-surface-frames", type=int, default=8)
    parser.add_argument("--stations", type=int, default=12)
    parser.add_argument("--min-particles-per-slice", type=int, default=8)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument("--velocity-color-max", type=float, default=6.0)
    parser.add_argument("--pressure-color-max", type=float, default=8000.0)
    parser.add_argument(
        "--cycles-surface",
        action="store_true",
        help="attempt Cycles for the v3 transparent-water surface pass",
    )
    parser.add_argument(
        "--upgrade-render-package",
        action="store_true",
        help="render particle, surface, velocity, and combined multiview showcase outputs",
    )
    parser.add_argument(
        "--v2-render-package",
        action="store_true",
        help="render the stricter v2 particle, surface-wide, surface-hero, velocity, and stitched outputs",
    )
    parser.add_argument(
        "--v3-render-package",
        action="store_true",
        help="render v3 streamwise-gravity particle, clear-water surface, pressure, velocity, and moving-slice outputs",
    )
    parser.add_argument(
        "--v4-render-package",
        action="store_true",
        help="render v4 extended transparent-surface, pressure, proxy-energy, surface-cut, and inspection outputs",
    )
    parser.add_argument("--force", action="store_true", help="replace generated case_work if it exists")
    parser.add_argument(
        "--reuse-existing-run",
        action="store_true",
        help="reuse an existing case_work/case_out instead of regenerating or rerunning DualSPHysics",
    )
    parser.add_argument("--no-run", action="store_true", help="prepare the modified case but do not run tools")
    parser.add_argument("--no-surface", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()

    paths = Paths(
        repo_root=args.repo_root.resolve(),
        official_root=args.official_root,
        output_root=args.output_root,
        blender=args.blender,
    )
    _require(paths.official_root, "official DualSPHysics root")
    for tool in ["GenCase_linux64", "DualSPHysics5.4_linux64", "PartVTK_linux64", "PartVTKOut_linux64"]:
        _tool(paths, tool)
    if not args.no_surface:
        _tool(paths, "IsoSurface_linux64")

    if not args.reuse_existing_run:
        _copy_and_modify_case(
            paths,
            args.velocity,
            args.time_max,
            args.time_out,
            args.force,
            args.profile,
            args.dp,
        )
    if args.no_run:
        print(f"Prepared modified case: {paths.case_xml_def}")
        return 0

    if not args.reuse_existing_run:
        _run_dualsphysics(paths, args.solver_timeout, args.post_timeout)
    particle_frames = _existing_particle_frames(paths)
    if not particle_frames:
        raise RuntimeError("PartVTK completed but no PartFluid_*.vtk frames were found")

    selected_for_render = _selected_frame_numbers(particle_frames, args.max_render_frames)
    surface_frames: list[Path] = []
    selected_for_surface = (
        selected_for_render
        if args.upgrade_render_package or args.v2_render_package or args.v3_render_package or args.v4_render_package
        else _selected_frame_numbers(particle_frames, args.max_surface_frames)
    )
    if not args.no_surface:
        surface_frames = _run_isosurface(paths, selected_for_surface, args.iso_timeout)

    csv_path, json_path, metrics_summary = _extract_metrics(
        paths, args.stations, args.min_particles_per_slice
    )
    rendered: list[Path] = []
    showcase_mp4 = None
    contact_sheet = None
    render_package: dict[str, str | int | bool] = {}
    if not args.no_render:
        if args.v4_render_package:
            render_package = _render_v4_package(
                paths,
                selected_for_render,
                args.render_timeout,
                args.fps,
                args.velocity_color_max,
                args.pressure_color_max,
                csv_path,
                args.cycles_surface,
            )
            showcase_mp4 = Path(str(render_package["final_showcase_mp4"]))
            contact_sheet = Path(str(render_package["contact_sheet"]))
            rendered = sorted(paths.render_dir.glob("v4_*.png"))
        elif args.v3_render_package:
            render_package = _render_v3_package(
                paths,
                selected_for_render,
                args.render_timeout,
                args.fps,
                args.velocity_color_max,
                args.pressure_color_max,
                csv_path,
                args.cycles_surface,
            )
            showcase_mp4 = Path(str(render_package["final_showcase_mp4"]))
            contact_sheet = Path(str(render_package["contact_sheet"]))
            rendered = sorted(paths.render_dir.glob("v3_*.png"))
        elif args.v2_render_package:
            render_package = _render_v2_package(
                paths,
                selected_for_render,
                args.render_timeout,
                args.fps,
                args.velocity_color_max,
            )
            showcase_mp4 = Path(str(render_package["final_showcase_mp4"]))
            contact_sheet = Path(str(render_package["contact_sheet"]))
            rendered = sorted(paths.render_dir.glob("v2_accept_*.png"))
        elif args.upgrade_render_package:
            render_package = _render_upgrade_package(
                paths,
                selected_for_render,
                args.render_timeout,
                args.fps,
                args.velocity_color_max,
            )
            showcase_mp4 = Path(str(render_package["final_showcase_mp4"]))
            contact_sheet = Path(str(render_package["contact_sheet"]))
            rendered = sorted(paths.render_dir.glob("upgrade_*.png"))
        else:
            rendered = _render_frames(
                paths,
                selected_for_render,
                args.render_timeout,
                color_max=args.velocity_color_max,
            )
            showcase_mp4, contact_sheet = _assemble_video(paths, rendered, args.fps)

    summary = {
        "status": "success",
        "case_name": CASE_NAME,
        "base_case": "examples/inletoutlet/06_Box4Inlet3D",
        "profile": args.profile,
        "dp": args.dp if args.dp is not None else (_profile_defaults(args.profile) or {}).get("dp"),
        "velocity_m_per_s": args.velocity,
        "gravity_vector": (_profile_defaults(args.profile) or {}).get("gravity", "base"),
        "axis_convention": (_profile_defaults(args.profile) or {}).get("axis_convention", "base"),
        "time_max_seconds": args.time_max,
        "time_out_seconds": args.time_out,
        "particle_vtk_frames": len(particle_frames),
        "surface_vtk_frames": len(surface_frames),
        "rendered_png_frames": len(rendered),
        "metrics_csv": str(csv_path),
        "metrics_summary_json": str(json_path),
        "showcase_mp4": str(showcase_mp4) if showcase_mp4 else "",
        "contact_sheet": str(contact_sheet) if contact_sheet else "",
        "render_package": render_package,
        "physical_validation": False,
        "caveat": (
            "This is a modified DualSPHysics inlet-jet geometry proxy. It is not "
            "a fully atomized spray simulation, not validation, not production "
            "CFD, and not experimental agreement."
        ),
        "metrics_summary": metrics_summary,
    }
    summary_path = paths.output_root / "rectangular_highspeed_jet_proxy_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    _inventory(paths, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
