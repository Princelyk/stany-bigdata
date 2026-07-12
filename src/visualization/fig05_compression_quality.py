#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "figure.dpi": 300,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
})

def main():
    inp = Path("results/data/metrics_compression_quality.csv")
    out_dir = Path("results/figures"); out_dir.mkdir(parents=True, exist_ok=True)
    if not inp.exists():
        raise SystemExit(f"Missing input: {inp} (run make_missing_metrics)")

    df = pd.read_csv(inp).dropna(subset=["mse","psnr","ssim"]).copy()

    algos = sorted(df["algorithm"].unique())
    data_mse  = [df[df["algorithm"]==a]["mse"].values for a in algos]
    data_psnr = [df[df["algorithm"]==a]["psnr"].values for a in algos]
    data_ssim = [df[df["algorithm"]==a]["ssim"].values for a in algos]

    fig, axes = plt.subplots(1, 3, figsize=(13,4))

    axes[0].boxplot(data_mse, labels=algos, showfliers=False)
    axes[0].set_title("MSE")
    axes[0].set_yscale("log")
    axes[0].grid(axis="y", alpha=0.3)
    axes[0].tick_params(axis="x", rotation=30)

    axes[1].boxplot(data_psnr, labels=algos, showfliers=False)
    axes[1].set_title("PSNR (dB)")
    axes[1].grid(axis="y", alpha=0.3)
    axes[1].tick_params(axis="x", rotation=30)

    axes[2].boxplot(data_ssim, labels=algos, showfliers=False)
    axes[2].set_title("SSIM")
    axes[2].grid(axis="y", alpha=0.3)
    axes[2].tick_params(axis="x", rotation=30)

    fig.suptitle("Figure 5: Qualité de reconstruction (images) – données réelles", y=1.02)
    fig.tight_layout()
    fig.savefig(out_dir/"figure05_compression_quality.pdf", bbox_inches="tight")
    fig.savefig(out_dir/"figure05_compression_quality.png", bbox_inches="tight")
    plt.close(fig)
    print("OK: figure05_compression_quality.*")

if __name__ == "__main__":
    main()
