#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


INPUT = Path("results/data/metrics_compression_ratios.csv")
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


def find_ratio_columns(df: pd.DataFrame) -> tuple[str, str | None]:
    """
    Prefer median for Q1-style robustness.
    Returns (ratio_col, err_col_or_None)
    """
    # Most robust: median + std
    if "compression_ratio_median" in df.columns:
        err = "compression_ratio_std" if "compression_ratio_std" in df.columns else None
        return "compression_ratio_median", err

    # Fallback: mean + std
    if "compression_ratio_mean" in df.columns:
        err = "compression_ratio_std" if "compression_ratio_std" in df.columns else None
        return "compression_ratio_mean", err

    # Other fallbacks
    for c in ["compression_ratio", "ratio", "cr", "comp_ratio"]:
        if c in df.columns:
            return c, None

    raise RuntimeError(
        "No usable compression ratio column found.\n"
        f"Found columns: {list(df.columns)}\n"
        "Expected one of: compression_ratio_median/mean or compression_ratio/ratio."
    )


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Missing input: {INPUT}")

    df = pd.read_csv(INPUT)
    if df.empty:
        raise SystemExit(f"{INPUT} is empty")

    if "algorithm" not in df.columns:
        raise RuntimeError(f"Missing 'algorithm'. Found: {list(df.columns)}")

    ratio_col, err_col = find_ratio_columns(df)

    df = df.copy()
    df["algorithm"] = df["algorithm"].apply(normalize_algo)
    df[ratio_col] = pd.to_numeric(df[ratio_col], errors="coerce")
    if err_col is not None:
        df[err_col] = pd.to_numeric(df[err_col], errors="coerce").fillna(0.0)

    df = df.dropna(subset=[ratio_col])
    df = df[df[ratio_col] > 1.0].copy()

    # Sort by ratio descending
    df = df.sort_values(ratio_col, ascending=False)

    # Publication style (simple + clean)
    plt.rcParams.update({
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
    })

    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    x = np.arange(len(df))
    vals = df[ratio_col].values
    yerr = df[err_col].values if err_col is not None else None

    bars = ax.bar(
        x, vals,
        yerr=yerr,
        capsize=4 if yerr is not None else 0,
        edgecolor="black",
        linewidth=0.6
    )

    # % compression shown: (1 - 1/ratio) * 100
    for i, (b, r) in enumerate(zip(bars, vals)):
        pct = (1.0 - 1.0 / float(r)) * 100.0
        extra = float(yerr[i]) if yerr is not None else 0.0
        ax.text(
            b.get_x() + b.get_width() / 2,
            b.get_height() + extra,
            f"{pct:.1f}%",
            ha="center", va="bottom",
            fontsize=9, fontweight="bold"
        )

    ax.set_xticks(x)
    ax.set_xticklabels(df["algorithm"].tolist(), rotation=20, ha="right")
    ax.set_ylabel("Compression ratio (×)")
    ax.set_title("Figure 3 — Ratios de compression (données réelles)")
    ax.grid(axis="y", linestyle="--", alpha=0.25)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUTDIR / f"fig03_compression_ratios.{ext}", bbox_inches="tight", dpi=300)
    plt.close(fig)

    print(f"OK: {OUTDIR}/fig03_compression_ratios.(pdf/png/svg)")


if __name__ == "__main__":
    main()

