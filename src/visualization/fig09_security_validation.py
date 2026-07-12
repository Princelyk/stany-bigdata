#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Figure 9 — Security validation (AES + ML-KEM)

Inputs:
    results/data/security_aes.csv
    results/data/security_kem.csv

Expected columns:
    test_name OR test
    pass OR success OR result
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def load_security_file(path):
    if not path.exists():
        return None

    df = pd.read_csv(path)

    # Normalize column names
    df.columns = [c.lower() for c in df.columns]

    # Detect test column
    if "test_name" in df.columns:
        test_col = "test_name"
    elif "test" in df.columns:
        test_col = "test"
    else:
        test_col = df.columns[0]

    # Detect result column
    if "pass" in df.columns:
        res_col = "pass"
    elif "success" in df.columns:
        res_col = "success"
    elif "result" in df.columns:
        res_col = "result"
    else:
        res_col = df.columns[-1]

    df = df[[test_col, res_col]].copy()
    df.columns = ["test", "result"]

    # Convert to numeric (1/0)
    df["result"] = pd.to_numeric(df["result"], errors="coerce")
    df = df.dropna()

    return df


def main():

    aes_path = Path("results/data/security_aes.csv")
    kem_path = Path("results/data/security_kem.csv")

    aes_df = load_security_file(aes_path)
    kem_df = load_security_file(kem_path)

    if aes_df is None and kem_df is None:
        raise SystemExit("No security CSV files found.")

    plt.rcParams["figure.dpi"] = 300

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # ===============================
    # AES panel
    # ===============================
    if aes_df is not None and not aes_df.empty:
        pass_rate = aes_df["result"].mean() * 100
        axes[0].bar(["AES-GCM"], [pass_rate])
        axes[0].set_ylim(0, 105)
        axes[0].set_ylabel("Taux de réussite (%)")
        axes[0].set_title("(a) Validation AES-GCM")

        axes[0].text(
            0, pass_rate + 1,
            f"{pass_rate:.1f}%",
            ha="center",
            fontweight="bold"
        )
        axes[0].grid(axis="y", alpha=0.3)
    else:
        axes[0].text(0.5, 0.5, "AES data missing", ha="center", transform=axes[0].transAxes)

    # ===============================
    # KEM panel
    # ===============================
    if kem_df is not None and not kem_df.empty:
        pass_rate = kem_df["result"].mean() * 100
        axes[1].bar(["ML-KEM"], [pass_rate])
        axes[1].set_ylim(0, 105)
        axes[1].set_ylabel("Taux de réussite (%)")
        axes[1].set_title("(b) Validation ML-KEM")

        axes[1].text(
            0, pass_rate + 1,
            f"{pass_rate:.1f}%",
            ha="center",
            fontweight="bold"
        )
        axes[1].grid(axis="y", alpha=0.3)
    else:
        axes[1].text(0.5, 0.5, "KEM data missing", ha="center", transform=axes[1].transAxes)

    fig.suptitle(
        "Figure 9: Validation cryptographique (vecteurs et cohérence)",
        fontsize=12
    )

    out_dir = Path("results/figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = out_dir / "fig09_security_validation"

    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(f"{stem}.png", bbox_inches="tight", dpi=300)
    fig.savefig(f"{stem}.svg", bbox_inches="tight")

    plt.close(fig)

    print("✓ Figure 9 générée:", stem)


if __name__ == "__main__":
    main()
