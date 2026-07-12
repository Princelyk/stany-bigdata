#!/usr/bin/env python3
"""
Figure 9 – Cryptographic security validation
AES-GCM + ML-KEM (functional correctness)
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Style publication
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman"],
    "figure.dpi": 300,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
})

def load_security_csv(path: Path, label_prefix: str):
    if not path.exists():
        raise SystemExit(f"Missing input file: {path}")

    df = pd.read_csv(path)

    if not {"test", "pass"}.issubset(df.columns):
        raise RuntimeError(
            f"{path.name} must contain columns ['test', 'pass'], got {list(df.columns)}"
        )

    df = df.copy()
    df["test"] = label_prefix + ": " + df["test"].astype(str)
    df["pass"] = df["pass"].astype(int)
    return df

def main():
    out_dir = Path("results/figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    aes_csv = Path("results/data/security_aes.csv")
    kem_csv = Path("results/data/security_kem.csv")

    # Charger données
    df_aes = load_security_csv(aes_csv, "AES")
    df_kem = load_security_csv(kem_csv, "KEM")

    df = pd.concat([df_aes, df_kem], ignore_index=True)

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(10, 5))

    x = range(len(df))
    bars = ax.bar(x, df["pass"], color="#4C72B0", edgecolor="black")

    # Annotations
    for i, val in enumerate(df["pass"]):
        label = "PASS" if val == 1 else "FAIL"
        ax.text(i, val + 0.02, label, ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Validation result")
    ax.set_xticks(x)
    ax.set_xticklabels(df["test"], rotation=30, ha="right")
    ax.set_title("Figure 9: Cryptographic security validation (AES-GCM + ML-KEM)")
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "figure09_security_checks.pdf", bbox_inches="tight")
    fig.savefig(out_dir / "figure09_security_checks.png", bbox_inches="tight")
    plt.close(fig)

    print("✓ Figure 9 generated successfully:")
    print("  - results/figures/figure09_security_checks.pdf")
    print("  - results/figures/figure09_security_checks.png")

if __name__ == "__main__":
    main()
