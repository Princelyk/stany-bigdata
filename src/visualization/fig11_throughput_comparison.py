#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def main() -> None:
    inp = Path("results/data/scalability.csv")
    if not inp.exists():
        raise SystemExit("Missing input: results/data/scalability.csv (run: python -m src.benchmarks.scalability_bench)")

    df = pd.read_csv(inp)
    if df.empty:
        raise SystemExit("scalability.csv is empty")

    need = {"algorithm", "throughput_mbps"}
    if not need.issubset(set(df.columns)):
        raise SystemExit(f"scalability.csv missing columns. Found: {list(df.columns)}; need: {sorted(need)}")

    df["throughput_mbps"] = pd.to_numeric(df["throughput_mbps"], errors="coerce")
    df = df.dropna(subset=["algorithm", "throughput_mbps"]).copy()

    algos = sorted(df["algorithm"].astype(str).unique().tolist())
    data = [df[df["algorithm"] == a]["throughput_mbps"].values for a in algos]

    fig = plt.figure(figsize=(10.5, 4.8))
    ax = plt.gca()

    ax.boxplot(data, labels=algos, showfliers=False)
    ax.set_ylabel("Throughput (MB/s)")
    ax.set_title("Figure 11: Comparaison du débit (throughput) — données réelles (scalability.csv)")
    ax.grid(True, axis="y", alpha=0.3)
    plt.xticks(rotation=25, ha="right")

    out_dir = Path("results/figures")
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png", "svg"):
        fig.savefig(out_dir / f"figure11_throughput_comparison.{ext}", bbox_inches="tight", dpi=300)
    plt.close(fig)

    print("OK: results/figures/figure11_throughput_comparison.(pdf/png/svg)")


if __name__ == "__main__":
    main()

