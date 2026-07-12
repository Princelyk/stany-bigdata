#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Figure 6 — AES-256-GCM Microbenchmark

Inputs:
    results/data/micro_aes.csv

Columns expected:
    plaintext_size
    enc_latency_ms
    dec_latency_ms
    enc_MBps
    dec_MBps

Output:
    results/figures/fig06_aes_microbench.pdf/.png/.svg
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def main():

    input_path = Path("results/data/micro_aes.csv")
    if not input_path.exists():
        raise SystemExit("Missing input: results/data/micro_aes.csv")

    df = pd.read_csv(input_path)

    required = [
        "plaintext_size",
        "enc_latency_ms",
        "dec_latency_ms",
        "enc_MBps",
        "dec_MBps"
    ]

    for col in required:
        if col not in df.columns:
            raise RuntimeError(
                f"Column '{col}' missing in micro_aes.csv.\n"
                f"Found: {list(df.columns)}"
            )

    # Clean numeric
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna().sort_values("plaintext_size")

    df["size_kb"] = df["plaintext_size"] / 1024
    df["roundtrip_latency_ms"] = df["enc_latency_ms"] + df["dec_latency_ms"]

    # =============================
    # Plot
    # =============================

    plt.rcParams["figure.dpi"] = 300

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8))

    # ---- Throughput ----
    ax1.plot(df["size_kb"], df["enc_MBps"], marker="o", label="Encrypt")
    ax1.plot(df["size_kb"], df["dec_MBps"], marker="s", label="Decrypt")

    ax1.set_xlabel("Taille plaintext (KB)")
    ax1.set_ylabel("Débit (MB/s)")
    ax1.set_title("(a) Débit AES-256-GCM")
    ax1.grid(alpha=0.3)
    ax1.legend()

    # ---- Latency ----
    ax2.plot(df["size_kb"], df["roundtrip_latency_ms"], marker="d")

    ax2.set_xlabel("Taille plaintext (KB)")
    ax2.set_ylabel("Latence enc+dec (ms)")
    ax2.set_title("(b) Latence roundtrip")
    ax2.grid(alpha=0.3)

    fig.suptitle("Figure 6: Microbenchmark AES-256-GCM (mesures réelles)", fontsize=12)

    out_dir = Path("results/figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = out_dir / "fig06_aes_microbench"
    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(f"{stem}.png", bbox_inches="tight", dpi=300)
    fig.savefig(f"{stem}.svg", bbox_inches="tight")

    plt.close(fig)

    print("✓ Figure 6 générée:", stem)


if __name__ == "__main__":
    main()
