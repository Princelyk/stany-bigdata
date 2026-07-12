#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


RATIO_FILE = Path("results/data/metrics_compression_ratios.csv")
QUALITY_FILE = Path("results/data/metrics_compression_quality.csv")
OUTDIR = Path("results/figures")


def normalize_algo(name: str) -> str:
    s = str(name).strip().lower()
    if "vae" in s:
        return "VAE"
    if "zstd" in s:
        return "Zstd"
    if "lz4" in s:
        return "LZ4"
    if "gzip" in s:
        return "Gzip"
    if "brotli" in s:
        return "Brotli"
    if "bz2" in s or "bzip" in s:
        return "Bzip2"
    return s.capitalize() if s else "Unknown"


def pick_ratio_col(df: pd.DataFrame) -> str:
    for c in ["compression_ratio_median", "compression_ratio_mean", "compression_ratio"]:
        if c in df.columns:
            return c
    raise RuntimeError(f"Missing compression ratio column. Found: {list(df.columns)}")


def pick_thr_col(df: pd.DataFrame) -> str:
    for c in ["throughput_MBps_median", "throughput_MBps_mean", "throughput_MBps"]:
        if c in df.columns:
            return c
    raise RuntimeError(f"Missing throughput column in ratios file. Found: {list(df.columns)}")


def main() -> None:
    if not RATIO_FILE.exists():
        raise SystemExit(f"Missing input: {RATIO_FILE}")
    if not QUALITY_FILE.exists():
        raise SystemExit(f"Missing input: {QUALITY_FILE}")

    ratios = pd.read_csv(RATIO_FILE)
    qual = pd.read_csv(QUALITY_FILE)

    if "algorithm" not in ratios.columns:
        raise RuntimeError(f"'algorithm' missing in {RATIO_FILE}. Found: {list(ratios.columns)}")
    if "algorithm" not in qual.columns:
        raise RuntimeError(f"'algorithm' missing in {QUALITY_FILE}. Found: {list(qual.columns)}")

    ratios = ratios.copy()
    qual = qual.copy()
    ratios["algorithm"] = ratios["algorithm"].apply(normalize_algo)
    qual["algorithm"] = qual["algorithm"].apply(normalize_algo)

    rcol = pick_ratio_col(ratios)
    tcol = pick_thr_col(ratios)

    if "psnr" not in qual.columns or "ssim" not in qual.columns:
        raise RuntimeError(f"{QUALITY_FILE} must contain psnr and ssim. Found: {list(qual.columns)}")

    ratios[rcol] = pd.to_numeric(ratios[rcol], errors="coerce")
    ratios[tcol] = pd.to_numeric(ratios[tcol], errors="coerce")
    qual["psnr"] = pd.to_numeric(qual["psnr"], errors="coerce")
    qual["ssim"] = pd.to_numeric(qual["ssim"], errors="coerce")

    # One row per algo: keep already-aggregated ratios
    rr = ratios.set_index("algorithm")[[rcol, tcol]].rename(columns={rcol: "ratio", tcol: "throughput"})
    qq = qual.groupby("algorithm")[["psnr", "ssim"]].mean()

    df = rr.join(qq, how="inner").dropna()

    OUTDIR.mkdir(parents=True, exist_ok=True)

    if df.empty:
        # Still generate an empty “info figure” instead of silently producing nothing
        fig, ax = plt.subplots(figsize=(8.4, 4.5))
        ax.axis("off")
        ax.text(
            0.01, 0.7,
            "Pareto frontier not generated: no common algorithms\n"
            "between metrics_compression_ratios.csv and metrics_compression_quality.csv.\n\n"
            "Fix:\n"
            "  1) Regenerate ratios including VAE:\n"
            "     python -m src.benchmarks.make_compression_ratios --data-dir data/user_data\n"
            "  2) Regenerate quality metrics for the same algorithms.\n",
            fontsize=10, family="monospace"
        )
        for ext in ("pdf", "png", "svg"):
            fig.savefig(OUTDIR / f"fig_pareto_frontier.{ext}", bbox_inches="tight", dpi=300)
        plt.close(fig)
        print("WROTE: fig_pareto_frontier as info-only (no intersection).")
        return

    # Publication style
    plt.rcParams.update({
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
    })

    fig, ax = plt.subplots(figsize=(8.4, 6.0))

    ssim = np.clip(df["ssim"].values, 0.0, 1.0)
    sizes = 120 + 480 * ssim

    sc = ax.scatter(
        df["throughput"].values,
        df["ratio"].values,
        c=df["psnr"].values,
        s=sizes,
        cmap="viridis",
        edgecolor="black",
        linewidth=0.6,
    )

    for algo, row in df.iterrows():
        ax.annotate(algo, (row["throughput"], row["ratio"]), textcoords="offset points", xytext=(6, 6), fontsize=9)

    cb = fig.colorbar(sc, ax=ax, pad=0.01)
    cb.set_label("PSNR (dB)")

    ax.set_xlabel("Throughput (MB/s)")
    ax.set_ylabel("Compression ratio (×)")
    ax.set_title("Pareto frontier: Compression ↔ Qualité ↔ Débit (données réelles)")
    ax.grid(True, alpha=0.25)

    handles = [
        plt.scatter([], [], s=120, edgecolor="black", facecolor="none", label="SSIM faible"),
        plt.scatter([], [], s=600, edgecolor="black", facecolor="none", label="SSIM élevé"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False)

    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUTDIR / f"fig_pareto_frontier.{ext}", bbox_inches="tight", dpi=300)
    plt.close(fig)

    print(f"OK: {OUTDIR}/fig_pareto_frontier.(pdf/png/svg)")


if __name__ == "__main__":
    main()

