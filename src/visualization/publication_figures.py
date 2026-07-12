#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publication-ready figures for Hybrid Secure Big Data
Scalability analysis with REAL data + linear regression (OLS)

Compatible IEEE / ACM Q1 journals
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import linregress

# =========================
# Global publication style
# =========================
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
})

# =========================
# Utilities
# =========================
def save_figure(fig, output_dir: str, name: str):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(out / f"{name}.png", bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"✓ {name}.pdf / .png")

# =========================
# Figure 2 — VAE training
# =========================
def fig02_vae_training_history(history_csv: str, output_dir: str):
    df = pd.read_csv(history_csv)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    ax1.plot(df["epoch"], df["train_loss"], marker="o")
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Training loss")
    ax1.set_title("(a) VAE training loss")
    ax1.grid(True, alpha=0.3)

    if "psnr" in df.columns:
        ax2.plot(df["epoch"], df["psnr"], marker="s")
        ax2.set_xlabel("Epoch")
        ax2.set_ylabel("PSNR (dB)")
        ax2.set_title("(b) Reconstruction quality")
        ax2.grid(True, alpha=0.3)
    else:
        ax2.text(0.5, 0.5, "PSNR not available",
                 ha="center", va="center", transform=ax2.transAxes)

    plt.tight_layout()
    save_figure(fig, output_dir, "fig02_vae_training_history")

# =========================================
# Figure 8 — Scalability with regression
# =========================================
def fig08_scalability(csv_path: str, output_dir: str):
    """
    Scalability figure using REAL file sizes.
    Linear regression is added to show near-constant behavior.
    """
    df = pd.read_csv(csv_path)

    # Required columns check
    required = {
        "size_mb",
        "latency_ms",
        "throughput_mbps",
        "cpu_mean_percent",
        "rss_mean_mb",
    }
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Missing columns in scalability CSV: {missing}")

    # Normalized latency
    df["latency_ms_per_mb"] = df["latency_ms"] / df["size_mb"]

    df = df.sort_values("size_mb")
    x = df["size_mb"].values

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), sharex=True)

    def plot_with_regression(ax, y, ylabel, title):
        slope, intercept, r, _, _ = linregress(x, y)
        y_hat = intercept + slope * x

        ax.plot(x, y, "o", label="Measured")
        ax.plot(x, y_hat, "--", linewidth=2,
                label=f"OLS fit (R² = {r**2:.3f})")

        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend()

    # (a) Latency normalized
    plot_with_regression(
        axes[0, 0],
        df["latency_ms_per_mb"].values,
        "Latency / MB (ms)",
        "(a) Normalized latency"
    )

    # (b) Throughput
    plot_with_regression(
        axes[0, 1],
        df["throughput_mbps"].values,
        "Throughput (MB/s)",
        "(b) Throughput"
    )

    # (c) CPU
    plot_with_regression(
        axes[1, 0],
        df["cpu_mean_percent"].values,
        "CPU mean (%)",
        "(c) CPU usage"
    )
    axes[1, 0].set_xlabel("File size (MB)")

    # (d) Memory
    plot_with_regression(
        axes[1, 1],
        df["rss_mean_mb"].values,
        "RSS memory (MB)",
        "(d) Memory usage"
    )
    axes[1, 1].set_xlabel("File size (MB)")

    for ax in axes.flat:
        ax.set_xscale("log")

    fig.suptitle(
        "Figure 8: Scalability of the hybrid cryptographic pipeline\n"
        "Real file sizes — near-constant performance with increasing data volume",
        fontsize=14
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    save_figure(fig, output_dir, "fig08_scalability")

# =========================
# Entry point
# =========================
def main():
    results_dir = Path("results")
    figures_dir = results_dir / "figures"

    # Figure 2
    hist = results_dir / "data" / "vae_training_history.csv"
    if hist.exists():
        fig02_vae_training_history(hist, figures_dir)

    # Figure 8
    scal = results_dir / "data" / "scalability.csv"
    if scal.exists():
        fig08_scalability(scal, figures_dir)

    print("\n✓ Publication figures generated")

if __name__ == "__main__":
    main()

