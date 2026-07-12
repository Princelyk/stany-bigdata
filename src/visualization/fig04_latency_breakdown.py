#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Figure 4 — Décomposition de la latence (barres empilées)
REAL DATA ONLY.

Inputs:
  - results/data/scalability.csv
  - results/data/micro_aes.csv
  - results/data/kem_samples_us.csv  (preferred) OR results/data/micro_kyber.csv

Output:
  - results/figures/fig04_latency_breakdown.pdf/.png/.svg

Method (honest & reproducible):
  total_latency_ms (from scalability) is decomposed as:
    total = compression_other + AES + KEM
  AES latency is estimated from micro_aes.csv by matching nearest plaintext_size.
  KEM latency is estimated from kem_samples_us.csv median(keygen+encaps+decaps) in ms.
  compression_other is residual (clamped at >=0).
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def _require(df: pd.DataFrame, cols: list[str], name: str) -> None:
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise RuntimeError(f"{name} missing columns: {miss}. Found: {list(df.columns)}")


def _load_scalability() -> pd.DataFrame:
    p = Path("results/data/scalability.csv")
    if not p.exists():
        raise SystemExit(f"Missing input: {p}")
    df = pd.read_csv(p)
    if df.empty:
        raise SystemExit(f"Empty input: {p}")
    _require(df, ["algorithm", "latency_ms"], "scalability.csv")
    df["latency_ms"] = pd.to_numeric(df["latency_ms"], errors="coerce")
    df = df.dropna(subset=["algorithm", "latency_ms"]).copy()
    df = df[df["latency_ms"] > 0].copy()
    return df


def _aes_latency_estimator():
    p = Path("results/data/micro_aes.csv")
    if not p.exists():
        raise SystemExit(f"Missing input: {p}")
    df = pd.read_csv(p)
    if df.empty:
        raise SystemExit(f"Empty input: {p}")
    # columns you showed: plaintext_size, enc_latency_ms, dec_latency_ms, enc_MBps, dec_MBps
    _require(df, ["plaintext_size", "enc_latency_ms", "dec_latency_ms"], "micro_aes.csv")

    df["plaintext_size"] = pd.to_numeric(df["plaintext_size"], errors="coerce")
    df["enc_latency_ms"] = pd.to_numeric(df["enc_latency_ms"], errors="coerce")
    df["dec_latency_ms"] = pd.to_numeric(df["dec_latency_ms"], errors="coerce")
    df = df.dropna(subset=["plaintext_size", "enc_latency_ms", "dec_latency_ms"]).copy()
    df = df.sort_values("plaintext_size")

    sizes = df["plaintext_size"].to_numpy(dtype=float)
    enc = df["enc_latency_ms"].to_numpy(dtype=float)
    dec = df["dec_latency_ms"].to_numpy(dtype=float)

    # Return a function mapping bytes -> AES enc+dec latency (ms)
    def est(n_bytes: float) -> float:
        if len(sizes) == 0:
            return float("nan")
        idx = int(np.argmin(np.abs(sizes - n_bytes)))
        return float(enc[idx] + dec[idx])

    return est


def _kem_latency_ms() -> float:
    # Prefer kem_samples_us.csv (has per-op samples)
    p = Path("results/data/kem_samples_us.csv")
    if p.exists():
        df = pd.read_csv(p)
        if not df.empty and all(c in df.columns for c in ["keygen_us", "encaps_us", "decaps_us"]):
            kg = pd.to_numeric(df["keygen_us"], errors="coerce").dropna().median()
            en = pd.to_numeric(df["encaps_us"], errors="coerce").dropna().median()
            de = pd.to_numeric(df["decaps_us"], errors="coerce").dropna().median()
            # total KEM roundtrip per message (ms)
            return float((kg + en + de) / 1000.0)

    # Fallback to micro_kyber.csv if present (may be summary)
    p2 = Path("results/data/micro_kyber.csv")
    if p2.exists():
        df = pd.read_csv(p2)
        if not df.empty:
            # try common columns
            candidates = [
                ("keygen_ms", "encaps_ms", "decaps_ms"),
                ("keygen_median_ms", "encaps_median_ms", "decaps_median_ms"),
                ("keygen_us", "encaps_us", "decaps_us"),
            ]
            for a, b, c in candidates:
                if a in df.columns and b in df.columns and c in df.columns:
                    x = pd.to_numeric(df[a], errors="coerce").dropna().median()
                    y = pd.to_numeric(df[b], errors="coerce").dropna().median()
                    z = pd.to_numeric(df[c], errors="coerce").dropna().median()
                    if "us" in a:
                        return float((x + y + z) / 1000.0)
                    return float(x + y + z)

    raise SystemExit(
        "Missing KEM timing inputs: expected results/data/kem_samples_us.csv "
        "or results/data/micro_kyber.csv with timing columns."
    )


def _total_dataset_gb(user_dir: Path) -> float:
    total = 0
    if not user_dir.exists():
        return float("nan")
    for p in user_dir.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total / (1024**3)


def main() -> None:
    out_dir = Path("results/figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    scal = _load_scalability()
    aes_est = _aes_latency_estimator()
    kem_ms = _kem_latency_ms()

    # Aggregate total latency per algorithm (median across files)
    g = (scal.groupby("algorithm", as_index=False)
             .agg(total_latency_ms=("latency_ms", "median"),
                  n=("latency_ms", "count")))

    # Need file sizes to estimate AES: use median size_mb if present, else a default 64KB
    if "size_mb" in scal.columns:
        scal["size_mb"] = pd.to_numeric(scal["size_mb"], errors="coerce")
        size_med = scal.groupby("algorithm")["size_mb"].median()
        g["size_mb_median"] = g["algorithm"].map(size_med)
        g["size_bytes_est"] = (g["size_mb_median"].fillna(0.0625) * 1024 * 1024)  # default ~64KB
    else:
        g["size_bytes_est"] = 65536.0

    # Estimate AES component (enc+dec) using nearest micro point
    g["aes_ms_est"] = g["size_bytes_est"].apply(lambda b: aes_est(float(b)))

    # KEM is per message; apply fixed median for now
    g["kem_ms_est"] = float(kem_ms)

    # Residual component
    g["compression_other_ms"] = g["total_latency_ms"] - g["aes_ms_est"] - g["kem_ms_est"]
    neg = (g["compression_other_ms"] < 0).sum()
    g.loc[g["compression_other_ms"] < 0, "compression_other_ms"] = 0.0

    # Sort by total latency
    g = g.sort_values("total_latency_ms", ascending=False)

    # Plot stacked bars
    plt.rcParams["figure.dpi"] = 300
    fig = plt.figure(figsize=(10.5, 5.5))
    ax = plt.gca()

    x = np.arange(len(g))
    comp = g["compression_other_ms"].to_numpy(dtype=float)
    aes = g["aes_ms_est"].to_numpy(dtype=float)
    kem = g["kem_ms_est"].to_numpy(dtype=float)

    ax.bar(x, comp, label="Compression/Autres")
    ax.bar(x, aes, bottom=comp, label="AES-256-GCM (enc+dec)")
    ax.bar(x, kem, bottom=comp + aes, label="KEM (keygen+encaps+decaps)")

    ax.set_xticks(x)
    ax.set_xticklabels(g["algorithm"].astype(str).tolist(), rotation=25, ha="right")
    ax.set_ylabel("Latence médiane (ms)")
    ax.set_title("Figure 4: Décomposition de la latence (données réelles)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()

    # subtitle with dataset size + notes
    total_gb = _total_dataset_gb(Path("data/user_data"))
    subtitle = f"Dataset utilisateur total: {total_gb:.2f} GB" if np.isfinite(total_gb) else ""
    note = ""
    if neg > 0:
        note = f" | note: {neg} résidu(s) négatif(s) clampés à 0"
    ax.text(0.99, 1.02, subtitle + note, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9)

    stem = out_dir / "fig04_latency_breakdown"
    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(f"{stem}.png", bbox_inches="tight", dpi=300)
    fig.savefig(f"{stem}.svg", bbox_inches="tight")
    plt.close(fig)

    print("OK:", f"{stem}.pdf/.png/.svg")
    print("KEM median ms used:", kem_ms)
    if neg > 0:
        print("WARNING: residual negative rows clamped:", int(neg))


if __name__ == "__main__":
    main()
