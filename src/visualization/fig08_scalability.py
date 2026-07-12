#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def read_csv_must(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing input: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise RuntimeError(f"Empty CSV: {path}")
    return df


def linreg(x: np.ndarray, y: np.ndarray):
    """
    Simple linear regression y = a*x + b, plus R².
    No sklearn dependency.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2:
        return 0.0, float(y.mean() if len(y) else 0.0), 0.0

    a, b = np.polyfit(x, y, 1)
    yhat = a * x + b
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2) + 1e-12
    r2 = 1.0 - (ss_res / ss_tot)
    return float(a), float(b), float(r2)


def save_all(fig, out_dir: Path, stem: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "pdf", "svg"]:
        fig.savefig(out_dir / f"{stem}.{ext}", bbox_inches="tight", dpi=300)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results", help="Results root (default: results)")
    ap.add_argument("--data-dir", default=None, help="Dataset dir (optional, only for labeling)")
    args = ap.parse_args()

    results = Path(args.results)
    data_csv = results / "data" / "scalability.csv"
    df = read_csv_must(data_csv)

    # aggregate across reps per point
    g = df.groupby(["point"], as_index=False).agg(
        size_gb=("size_gb", "median"),
        throughput_mbps=("throughput_mbps", "median"),
        latency_ms=("latency_ms", "median"),
        cpu_mean_percent=("cpu_mean_percent", "median"),
        rss_mean_mb=("rss_mean_mb", "median"),
        n_files=("n_files", "median"),
        total_dataset_gb=("total_dataset_gb", "max"),
    ).sort_values("size_gb")

    total_gb = float(g["total_dataset_gb"].max()) if "total_dataset_gb" in g.columns else float(g["size_gb"].max())

    x = g["size_gb"].to_numpy(dtype=float)
    thr = g["throughput_mbps"].to_numpy(dtype=float)
    lat = g["latency_ms"].to_numpy(dtype=float)

    a_thr, b_thr, r2_thr = linreg(x, thr)
    a_lat, b_lat, r2_lat = linreg(x, lat)

    # quantify "stable performance"
    # If |slope| is small relative to median (per GB)
    thr_med = float(np.median(thr)) if len(thr) else 0.0
    thr_slope_pct_per_gb = (a_thr / max(thr_med, 1e-12)) * 100.0

    stable_msg = f"Stabilité débit: pente={a_thr:+.3f} MB/s/GB (~{thr_slope_pct_per_gb:+.2f}%/GB), R²={r2_thr:.3f}"

    # Publication-ish style (IEEE/ACM): clean grid, good spacing
    plt.rcParams.update({
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "legend.fontsize": 9,
    })

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    ax1, ax2, ax3, ax4 = axes[0,0], axes[0,1], axes[1,0], axes[1,1]

    # (a) throughput
    ax1.plot(x, thr, marker="o", linewidth=1.8, label="Débit (médiane)")
    # dotted regression line (orange)
    xfit = np.linspace(x.min(), x.max(), 100) if len(x) >= 2 else x
    yfit = a_thr * xfit + b_thr
    ax1.plot(xfit, yfit, linestyle="--", linewidth=1.6, color="orange",
             label=f"Régression linéaire (pente={a_thr:+.2f}, R²={r2_thr:.2f})")
    ax1.set_title("(a) Débit vs taille")
    ax1.set_xlabel("Taille benchmarkée (GB)")
    ax1.set_ylabel("Throughput (MB/s)")
    ax1.grid(True, alpha=0.25)

    # (b) latency
    ax2.plot(x, lat, marker="s", linewidth=1.8, label="Latence (médiane)")
    yfit2 = a_lat * xfit + b_lat
    ax2.plot(xfit, yfit2, linestyle="--", linewidth=1.6, color="orange",
             label=f"Régression linéaire (pente={a_lat:+.2f}, R²={r2_lat:.2f})")
    ax2.set_title("(b) Latence vs taille")
    ax2.set_xlabel("Taille benchmarkée (GB)")
    ax2.set_ylabel("Latence (ms)")
    ax2.grid(True, alpha=0.25)

    # (c) CPU
    ax3.plot(x, g["cpu_mean_percent"].to_numpy(dtype=float), marker="^", linewidth=1.8, label="CPU (médiane)")
    ax3.set_title("(c) CPU vs taille")
    ax3.set_xlabel("Taille benchmarkée (GB)")
    ax3.set_ylabel("CPU (%)")
    ax3.grid(True, alpha=0.25)

    # (d) RSS
    ax4.plot(x, g["rss_mean_mb"].to_numpy(dtype=float), marker="d", linewidth=1.8, label="RSS (médiane)")
    ax4.set_title("(d) Mémoire RSS vs taille")
    ax4.set_xlabel("Taille benchmarkée (GB)")
    ax4.set_ylabel("RSS (MB)")
    ax4.grid(True, alpha=0.25)

    # One legend per row for IEEE cleanliness
    ax1.legend(loc="best", frameon=True)
    ax2.legend(loc="best", frameon=True)
    ax3.legend(loc="best", frameon=True)
    ax4.legend(loc="best", frameon=True)

    ds_label = f"Dataset total réel = {total_gb:.2f} GB"
    fig.suptitle(f"Figure 8 — Scalabilité (données réelles). {ds_label}\n{stable_msg}", y=1.02)

    plt.tight_layout()

    out_dir = results / "figures"
    save_all(fig, out_dir, "figure8_scalability")
    plt.close(fig)

    print(f"OK: wrote {out_dir}/figure8_scalability.(png|pdf|svg)")
    print("NOTE:", stable_msg)


if __name__ == "__main__":
    main()
