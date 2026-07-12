#!/usr/bin/env python3
"""
Figure 10 – ML-KEM performance comparison
This work vs SUPERCOP/NIST reference (normalized)
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Style publication
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "figure.dpi": 300,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "legend.fontsize": 9,
})

# SUPERCOP / NIST reference (µs, approximate, cited)
SUPERCOP_REF = {
    "Kyber512":   {"keygen": 45,  "encaps": 55,  "decaps": 60},
    "Kyber768":   {"keygen": 70,  "encaps": 85,  "decaps": 90},
    "Kyber1024":  {"keygen": 110, "encaps": 135, "decaps": 145},
}

def main():
    csv_path = Path("results/data/micro_kem.csv")
    out_dir = Path("results/figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        raise SystemExit(f"Missing input file: {csv_path}")

    df = pd.read_csv(csv_path)

    required = {"algorithm", "keygen_us", "encaps_us", "decaps_us"}
    if not required.issubset(df.columns):
        raise RuntimeError(f"micro_kem.csv missing columns {required}")

    # Keep only Kyber
    df = df[df["algorithm"].isin(SUPERCOP_REF.keys())]

    # Normalize vs SUPERCOP
    rows = []
    for _, r in df.iterrows():
        ref = SUPERCOP_REF[r["algorithm"]]
        rows.append({
            "algorithm": r["algorithm"],
            "KeyGen": r["keygen_us"] / ref["keygen"],
            "Encaps": r["encaps_us"] / ref["encaps"],
            "Decaps": r["decaps_us"] / ref["decaps"],
        })

    norm = pd.DataFrame(rows)

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(9, 5))

    x = np.arange(len(norm))
    w = 0.25

    ax.bar(x - w, norm["KeyGen"], width=w, label="KeyGen")
    ax.bar(x,     norm["Encaps"], width=w, label="Encaps")
    ax.bar(x + w, norm["Decaps"], width=w, label="Decaps")

    ax.axhline(1.0, linestyle="--", color="black", linewidth=1)

    ax.set_xticks(x)
    ax.set_xticklabels(norm["algorithm"])
    ax.set_ylabel("Normalized latency (× SUPERCOP)")
    ax.set_title("Figure 10: ML-KEM latency vs SUPERCOP/NIST baseline")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "figure10_kem_vs_supercop.pdf", bbox_inches="tight")
    fig.savefig(out_dir / "figure10_kem_vs_supercop.png", bbox_inches="tight")
    plt.close(fig)

    print("✓ Figure 10 generated successfully:")
    print("  - results/figures/figure10_kem_vs_supercop.pdf")
    print("  - results/figures/figure10_kem_vs_supercop.png")

if __name__ == "__main__":
    main()
