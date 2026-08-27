#!/usr/bin/env python3
"""Build local-only review plots from existing extended-domain sparse exports."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def rows(path):
    with path.open() as f:
        yield from csv.DictReader(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("case_output", type=Path)
    args = ap.parse_args()
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=True)
    scalar = list(rows(args.case_output / "raw_frame_summary.csv"))
    scalar = [r for r in scalar if r["case_id"] == "l7_physical_l7_equivalent_extended_campaign"]
    factor = 8.078581178151573 / 1.125
    fig, ax = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    x = [float(r["t"])*factor for r in scalar]
    for axis, key, label in [(ax[0,0], "exit_flow", "exit flow"), (ax[0,1], "mean_exit_velocity", "mean exit velocity"), (ax[1,0], "active_front_Dh", "active front / Dh"), (ax[1,1], "interface_proxy", "interface proxy")]:
        axis.plot(x, [float(r[key]) for r in scalar], lw=1.4)
        axis.set(xlabel="t*", ylabel=label)
        axis.grid(alpha=.25)
    fig.suptitle("Extended-domain L7-equivalent campaign scalars")
    fig.savefig(root / "campaign_scalar_history.png", dpi=160)
    plt.close(fig)
    field_dir = args.case_output / "fields"
    chosen = sorted(field_dir.glob("*.csv"), key=lambda p: p.name)
    chosen = [chosen[0], chosen[len(chosen)//2], chosen[-1]]
    manifest = []
    for p in chosen:
        data = list(rows(p))
        liquid = [r for r in data if float(r["f"]) >= .5]
        if not liquid:
            continue
        t = float(liquid[0]["t"])*factor
        xs = [float(r["x"]) for r in liquid]
        ys = [float(r["y"]) for r in liquid]
        zs = [float(r["z"]) for r in liquid]
        fig, ax = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
        ax[0].scatter(xs, ys, s=.15, c=zs, cmap="coolwarm", rasterized=True)
        ax[0].set(xlabel="x", ylabel="y", title=f"liquid side view, t*={t:.3f}")
        ax[0].set_aspect("equal", adjustable="box")
        near = [r for r in liquid if abs(float(r["x"])) < .12]
        ax[1].scatter([float(r["y"]) for r in near], [float(r["z"]) for r in near], s=.4, c=[float(r["velocity_magnitude"]) for r in near], cmap="viridis", rasterized=True)
        ax[1].set(xlabel="y", ylabel="z", title="near-exit transverse liquid section")
        ax[1].set_aspect("equal", adjustable="box")
        name = f"liquid_views_tstar_{t:.3f}.png"
        fig.savefig(root / name, dpi=160)
        plt.close(fig)
        manifest.append((name, p.name, t, len(liquid)))
    with (root / "visual_manifest.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["review_file", "source_field_export", "t_star", "liquid_samples"]); w.writerows(manifest)
    with (root / "README_VISUAL_REVIEW.txt").open("w") as f:
        f.write("Extended-domain L7-equivalent local visual review.\n\nReview first:\n")
        f.write("- campaign_scalar_history.png: persistent exit-flow/velocity decline and active-front progression.\n")
        for name, _, t, _ in manifest:
            f.write(f"- {name}: liquid side and near-exit transverse view at t*={t:.3f}.\n")
        f.write("\nThese are sparse-export renderings, not atomization or physical-model validation.\n")


if __name__ == "__main__":
    main()
