#!/usr/bin/env python3
"""Analyze rectangular internal-nozzle calibration profile diagnostics.

Captured from:
/home/franco/stack-validation/20260620-basilisk-internal-nozzle-calibration/analysis/analyze_rectangular_nozzle_profile.py

This script compares calibration profile samples to a rectangular-duct
Poiseuille-series shape. It is a diagnostic tool, not validation evidence.
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import argparse


def read_csv(path: pathlib.Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def odd_series_shape(y: float, z: float, w: float, h: float, nmax: int = 51) -> float:
    # Convert centered coordinates to [0,W] x [0,H].
    yy = y + 0.5*w
    zz = z + 0.5*h
    if yy <= 0.0 or yy >= w or zz <= 0.0 or zz >= h:
        return 0.0
    total = 0.0
    for m in range(1, nmax + 1, 2):
        sm = math.sin(m*math.pi*yy/w)
        for n in range(1, nmax + 1, 2):
            denom = m*n*((m/w)**2 + (n/h)**2)
            total += sm*math.sin(n*math.pi*zz/h)/denom
    return total


def weighted_mean(vals, weights):
    sw = sum(weights)
    if sw <= 0:
        return 0.0
    return sum(v*w for v, w in zip(vals, weights))/sw


def nearest_value(samples, target_y, target_z, key):
    best = None
    bd = 1e99
    for row in samples:
        y = float(row["y"]); z = float(row["z"])
        d = (y - target_y)**2 + (z - target_z)**2
        if d < bd:
            bd = d
            best = float(row[key])
    return best if best is not None else 0.0


def symmetry_error(samples):
    # Coarse nearest-neighbor mirror comparison against (-y,z) and (y,-z).
    pts = [(float(r["y"]), float(r["z"]), float(r["ux"])) for r in samples]
    if len(pts) < 2:
        return None
    errs = []
    for y, z, u in pts:
        for ty, tz in [(-y, z), (y, -z)]:
            best = min(pts, key=lambda p: (p[0]-ty)**2 + (p[1]-tz)**2)
            if abs(u) + abs(best[2]) > 1e-14:
                errs.append(abs(u - best[2])/(0.5*(abs(u) + abs(best[2])) + 1e-14))
    return sum(errs)/len(errs) if errs else None


def write_svg(path: pathlib.Path, points, title: str, xlabel: str, ylabel: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not points:
        path.write_text("<svg xmlns='http://www.w3.org/2000/svg' width='700' height='420'><text x='20' y='40'>No points</text></svg>\n", encoding="utf-8")
        return
    xs = [p[0] for p in points]; ys = [p[1] for p in points]; ys2 = [p[2] for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys + ys2), max(ys + ys2)
    if xmax == xmin: xmax = xmin + 1.0
    if ymax == ymin: ymax = ymin + 1.0
    def sx(x): return 70 + 570*(x - xmin)/(xmax - xmin)
    def sy(y): return 350 - 270*(y - ymin)/(ymax - ymin)
    poly1 = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y, _ in points)
    poly2 = " ".join(f"{sx(x):.1f},{sy(y2):.1f}" for x, _, y2 in points)
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='700' height='420' viewBox='0 0 700 420'>
<rect width='700' height='420' fill='white'/>
<text x='70' y='35' font-family='sans-serif' font-size='18'>{title}</text>
<line x1='70' y1='350' x2='640' y2='350' stroke='black'/>
<line x1='70' y1='80' x2='70' y2='350' stroke='black'/>
<polyline points='{poly1}' fill='none' stroke='#0b5cad' stroke-width='2'/>
<polyline points='{poly2}' fill='none' stroke='#b83b3b' stroke-width='2' stroke-dasharray='6 4'/>
<text x='500' y='390' font-family='sans-serif' font-size='13'>{xlabel}</text>
<text x='15' y='95' font-family='sans-serif' font-size='13'>{ylabel}</text>
<text x='430' y='65' font-family='sans-serif' font-size='13' fill='#0b5cad'>numerical</text>
<text x='530' y='65' font-family='sans-serif' font-size='13' fill='#b83b3b'>analytic scaled</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def analyze_case(case_dir: pathlib.Path, metrics_dir: pathlib.Path, plots_dir: pathlib.Path):
    summary_rows = read_csv(case_dir / "nozzle_case_summary.csv")
    samples = read_csv(case_dir / "profile_samples.csv")
    if not summary_rows or not samples:
        raise RuntimeError(f"missing summary or samples in {case_dir}")
    s = summary_rows[0]
    w = float(s["width"]); h = float(s["height"])
    weights = [float(r["area_weight"]) for r in samples]
    u = [float(r["ux"]) for r in samples]
    mean_u = weighted_mean(u, weights)
    analytic_shape = [odd_series_shape(float(r["y"]), float(r["z"]), w, h) for r in samples]
    mean_shape = weighted_mean(analytic_shape, weights)
    scale = mean_u/mean_shape if abs(mean_shape) > 1e-14 else 0.0
    ua = [scale*a for a in analytic_shape]
    denom_l2 = math.sqrt(sum(weights[i]*ua[i]*ua[i] for i in range(len(u))) / max(sum(weights), 1e-30))
    l2 = math.sqrt(sum(weights[i]*(u[i]-ua[i])**2 for i in range(len(u))) / max(sum(weights), 1e-30))
    linf = max(abs(u[i]-ua[i]) for i in range(len(u))) if u else 0.0
    max_ua = max(abs(v) for v in ua) if ua else 0.0
    center_num = nearest_value(samples, 0.0, 0.0, "ux")
    center_ana = scale*odd_series_shape(0.0, 0.0, w, h)
    center_err = abs(center_num - center_ana)/max(abs(center_ana), 1e-14)
    mean_err = abs(mean_u - float(s["target_u"]))/max(abs(float(s["target_u"])), 1e-14)
    sym = symmetry_error(samples)
    result = {
        "case_id": s["case_id"],
        "case_dir": str(case_dir),
        "mean_velocity": mean_u,
        "target_mean_velocity": float(s["target_u"]),
        "mean_velocity_error": mean_err,
        "centerline_velocity": center_num,
        "analytic_centerline_scaled": center_ana,
        "centerline_error": center_err,
        "profile_l2_error": l2/max(denom_l2, 1e-14),
        "profile_linf_error": linf/max(max_ua, 1e-14),
        "mass_imbalance": float(s["mass_imbalance"]),
        "max_wall_speed": float(s["max_wall_speed"]),
        "sample_count": len(samples),
        "symmetry_error": sym,
        "stop_reason": s["stop_reason"],
    }
    # Cut plots near z=0 and y=0.
    ztol = max(float(r["Delta"]) for r in samples)*1.1
    ytol = ztol
    long_pts = []
    short_pts = []
    for r, aa in zip(samples, ua):
        y = float(r["y"]); z = float(r["z"])
        if abs(z) <= ztol:
            long_pts.append((y, float(r["ux"]), aa))
        if abs(y) <= ytol:
            short_pts.append((z, float(r["ux"]), aa))
    long_pts.sort(key=lambda p: p[0])
    short_pts.sort(key=lambda p: p[0])
    write_svg(plots_dir / f"{s['case_id']}_long_axis_profile.svg", long_pts, f"{s['case_id']} long-axis cut", "y", "u_x")
    write_svg(plots_dir / f"{s['case_id']}_short_axis_profile.svg", short_pts, f"{s['case_id']} short-axis cut", "z", "u_x")
    return result


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Analyze rectangular internal-nozzle calibration profile diagnostics. "
            "Outputs profile-comparison CSV/JSON and SVG cuts under OUTPUT_ROOT."
        )
    )
    parser.add_argument("output_root", type=pathlib.Path)
    parser.add_argument("case_dirs", nargs="*", type=pathlib.Path)
    args = parser.parse_args()

    root = args.output_root
    case_dirs = args.case_dirs
    if not case_dirs:
        case_dirs = sorted((root / "runs").glob("*"))
    metrics_dir = root / "metrics"; plots_dir = root / "plots"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    results = []
    errors = []
    for d in case_dirs:
        try:
            if (d / "nozzle_case_summary.csv").exists() and (d / "profile_samples.csv").exists():
                results.append(analyze_case(d, metrics_dir, plots_dir))
        except Exception as exc:
            errors.append({"case_dir": str(d), "error": str(exc)})
    with (metrics_dir / "profile_comparison.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "case_id", "case_dir", "mean_velocity", "target_mean_velocity", "mean_velocity_error",
            "centerline_velocity", "analytic_centerline_scaled", "centerline_error",
            "profile_l2_error", "profile_linf_error", "mass_imbalance", "max_wall_speed",
            "sample_count", "symmetry_error", "stop_reason",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in results:
            w.writerow(row)
    (metrics_dir / "profile_comparison.json").write_text(json.dumps({"results": results, "errors": errors}, indent=2), encoding="utf-8")
    print(json.dumps({"analyzed": len(results), "errors": errors, "profile_comparison": str(metrics_dir / "profile_comparison.csv")}, indent=2))
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
