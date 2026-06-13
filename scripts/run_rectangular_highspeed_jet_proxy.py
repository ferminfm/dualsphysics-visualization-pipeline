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
            ("gravity", (0.0, 0.0, -9.81)),
        ]:
            element = root.find(f"./casedef/constantsdef/{tag}")
            if element is not None:
                _set_vector_attrs(element, attrs)
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
            speed_mean = math.nan
            speed_std = math.nan
            if velocities:
                vx = [float(velocities[idx][0]) for idx in ids]
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
                speed_mean = _mean(speeds)
                speed_std = _std(speeds, speed_mean)
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
                    "speed_mean": speed_mean,
                    "speed_std": speed_std,
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
    resolution: int = 1280,
    samples: int = 48,
    camera_lens: float = 70.0,
    marker_scale: float = 1.15,
    marker_style: str = "octahedron",
    fluid_stride: int = 1,
    iso_color: str = "#5DD9FF66",
    fluid_color: str = "#5DD9FF66",
    background_color: str = "#071018FF",
    light_energy: float = 1200.0,
    light_size: float = 2.0,
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
        if mode == "velocity":
            command.extend(
                [
                    "--color-by",
                    "Vel",
                    "--color-bins",
                    "7",
                    "--color-min",
                    "0",
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
                ]
            )
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
    sequence_dir = paths.output_root / f"{output_name}_contact_inputs"
    sequence_dir.mkdir(parents=True, exist_ok=True)
    for stale in sequence_dir.glob("frame_*.png"):
        stale.unlink()
    for index, frame in enumerate(rendered):
        shutil.copy2(frame, sequence_dir / f"frame_{index:04d}.png")
    contact_sheet = paths.output_root / f"{output_name}.png"
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(sequence_dir / "frame_%04d.png"),
            "-vf",
            "scale=320:-1,tile=4x3",
            "-frames:v",
            "1",
            str(contact_sheet),
        ],
        paths.logs_dir / f"08_ffmpeg_{output_name}.log",
        300,
    )
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


def _assemble_titled_video(
    paths: Paths,
    rendered: list[Path],
    fps: int,
    stem: str,
    title: str,
    subtitle: str,
    particle_text: str,
    render_text: str,
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
            "Particle/velocity visualization and preliminary slice metrics",
            "--particle-text",
            particle_text,
            "--platform-text",
            "DualSPHysics v5.4 GPU | headless Blender | ffmpeg",
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
        choices=("coarse", "upgraded", "v2"),
        default="coarse",
        help=(
            "coarse reproduces the first proxy; upgraded stretches the domain; "
            "v2 uses a longer open-downstream box for accepted-quality renders"
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
        if args.upgrade_render_package or args.v2_render_package
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
    render_package: dict[str, str | int] = {}
    if not args.no_render:
        if args.v2_render_package:
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
