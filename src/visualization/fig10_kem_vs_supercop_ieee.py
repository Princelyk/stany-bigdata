#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Figure 10 (IEEE/ACM-ready)
- 10a: KEM latencies (median + IQR) for KeyGen/Encaps/Decaps
      ours vs SUPERCOP (if available)
- 10b: KEM sizes (bytes) liboqs vs NIST KAT (if available)

Inputs (ours):
  - results/data/kem_samples_us.csv   (preferred)
    columns: algorithm, keygen_us, encaps_us, decaps_us
  - OR results/data/micro_kyber.csv   (fallback)

Optional:
  - data/SUPERCOP/**  (best-effort parsing)
  - data/nist_vectors/** or data/NIST_VECTORS/** (best-effort parsing)

Outputs:
  - results/figures/fig10a_kem_latency_vs_supercop.{pdf,png,svg}
  - results/figures/fig10b_kem_sizes_vs_nist.{pdf,png,svg}
"""

from __future__ import annotations

import re
import gzip
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    import psutil
except Exception:
    psutil = None

try:
    import oqs
except Exception:
    oqs = None


# ---------------------------
# Styling (IEEE-ish)
# ---------------------------
def set_ieee_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 300,
            "savefig.dpi": 300,
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
        }
    )


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def save3(fig, stem: Path) -> None:
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(stem.with_suffix(".png"), bbox_inches="tight", dpi=300)
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def _read_text(p: Path, max_bytes: int = 2_000_000) -> str:
    try:
        if p.suffix.lower() == ".gz":
            with gzip.open(p, "rt", errors="ignore") as f:
                return f.read(max_bytes)
        return p.read_text(errors="ignore")[:max_bytes]
    except Exception:
        return ""


def cpu_hz_estimate() -> float:
    # Only for converting ours -> cycles, if you decide to show that later
    if psutil is not None:
        f = psutil.cpu_freq()
        if f and f.current and f.current > 0:
            return float(f.current) * 1e6
    try:
        txt = Path("/proc/cpuinfo").read_text(errors="ignore")
        m = re.search(r"cpu MHz\s*:\s*([0-9.]+)", txt)
        if m:
            return float(m.group(1)) * 1e6
    except Exception:
        pass
    return 3.0e9


def algo_norm(x: str) -> str:
    s = str(x).lower().replace("_", "-").replace(" ", "")
    if "ml-kem-512" in s or "mlkem512" in s:
        return "Kyber512"
    if "ml-kem-768" in s or "mlkem768" in s:
        return "Kyber768"
    if "ml-kem-1024" in s or "mlkem1024" in s:
        return "Kyber1024"
    if "kyber512" in s:
        return "Kyber512"
    if "kyber768" in s:
        return "Kyber768"
    if "kyber1024" in s:
        return "Kyber1024"
    return str(x)


# ---------------------------
# OURS: load per-sample us if possible
# ---------------------------
def load_ours_samples_us() -> pd.DataFrame:
    p = Path("results/data/kem_samples_us.csv")
    if p.exists():
        df = pd.read_csv(p)
        df.columns = [c.lower() for c in df.columns]
        if "algorithm" not in df.columns:
            df["algorithm"] = "Kyber1024"
        df["algorithm"] = df["algorithm"].astype(str).map(algo_norm)
        for c in ["keygen_us", "encaps_us", "decaps_us"]:
            if c not in df.columns:
                raise RuntimeError(f"kem_samples_us.csv missing {c}. Found: {list(df.columns)}")
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["algorithm", "keygen_us", "encaps_us", "decaps_us"]).copy()
        return df

    # fallback: micro_kyber.csv (summary) -> expand as pseudo-samples (not ideal but OK)
    p2 = Path("results/data/micro_kyber.csv")
    if not p2.exists():
        raise SystemExit("Missing input: results/data/kem_samples_us.csv OR results/data/micro_kyber.csv")

    df = pd.read_csv(p2)
    if df.empty:
        raise SystemExit("micro_kyber.csv is empty")

    if "algorithm" not in df.columns:
        # try to find a plausible algo column
        for cand in ["alg", "kem", "name"]:
            if cand in df.columns:
                df["algorithm"] = df[cand]
                break
        if "algorithm" not in df.columns:
            df["algorithm"] = "Kyber1024"
    df["algorithm"] = df["algorithm"].astype(str).map(algo_norm)

    # find timing columns
    cols = set(df.columns)
    def pick(*names):
        for n in names:
            if n in cols:
                return n
        return None

    k_us = pick("keygen_us", "keypair_us")
    e_us = pick("encaps_us", "enc_us")
    d_us = pick("decaps_us", "dec_us")

    k_ms = pick("keygen_median_ms", "keypair_median_ms", "keygen_ms", "keypair_ms")
    e_ms = pick("encaps_median_ms", "encaps_ms", "enc_median_ms")
    d_ms = pick("decaps_median_ms", "decaps_ms", "dec_median_ms")

    out = pd.DataFrame({"algorithm": df["algorithm"]})
    if k_us and e_us and d_us:
        out["keygen_us"] = pd.to_numeric(df[k_us], errors="coerce")
        out["encaps_us"] = pd.to_numeric(df[e_us], errors="coerce")
        out["decaps_us"] = pd.to_numeric(df[d_us], errors="coerce")
    elif k_ms and e_ms and d_ms:
        out["keygen_us"] = pd.to_numeric(df[k_ms], errors="coerce") * 1000.0
        out["encaps_us"] = pd.to_numeric(df[e_ms], errors="coerce") * 1000.0
        out["decaps_us"] = pd.to_numeric(df[d_ms], errors="coerce") * 1000.0
    else:
        raise RuntimeError(f"Cannot infer timing columns in micro_kyber.csv. Columns={list(df.columns)}")

    # pseudo-samples: replicate each row 30x so boxplots show something
    out = out.dropna().copy()
    out = pd.concat([out] * 30, ignore_index=True)
    return out


# ---------------------------
# SUPERCOP cycles parsing -> convert to us (approx)
# ---------------------------
def parse_supercop_cycles(root: Path = Path("data/SUPERCOP")) -> pd.DataFrame:
    if not root.exists():
        return pd.DataFrame()

    files = [
        p for p in root.rglob("*")
        if p.is_file() and any(k in p.name.lower() for k in ["speed", "cycles", "cpucycles", "bench"])
    ]
    rows = []
    for p in files:
        txt = _read_text(p)
        if not txt:
            continue
        alg = algo_norm(str(p) + " " + txt[:8000])
        if alg not in {"Kyber512", "Kyber768", "Kyber1024"}:
            continue

        def find_one(keys):
            for key in keys:
                m = re.search(rf"{key}\s*[:=]\s*([0-9]+)", txt, flags=re.IGNORECASE)
                if m:
                    return float(m.group(1))
                m2 = re.search(rf"{key}.*?([0-9]+)\s*cycles", txt, flags=re.IGNORECASE)
                if m2:
                    return float(m2.group(1))
            return np.nan

        keygen = find_one(["keypair", "keygen"])
        encaps = find_one(["encaps", "enc"])
        decaps = find_one(["decaps", "dec"])

        if np.isnan(keygen) and np.isnan(encaps) and np.isnan(decaps):
            continue

        rows.append(
            {"algorithm": alg, "keygen_cycles": keygen, "encaps_cycles": encaps, "decaps_cycles": decaps}
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).groupby("algorithm", as_index=False).median(numeric_only=True)
    return df


def supercop_cycles_to_us(sup: pd.DataFrame, hz: float) -> pd.DataFrame:
    """
    Convert cycles -> microseconds, using an estimated CPU frequency.
    This is only to align units visually; in the paper you should disclose the conversion.
    """
    if sup is None or sup.empty:
        return pd.DataFrame()
    out = sup.copy()
    out["keygen_us"] = out["keygen_cycles"] / hz * 1e6
    out["encaps_us"] = out["encaps_cycles"] / hz * 1e6
    out["decaps_us"] = out["decaps_cycles"] / hz * 1e6
    out = out[["algorithm", "keygen_us", "encaps_us", "decaps_us"]].copy()
    return out


# ---------------------------
# NIST KAT size parsing (best effort)
# ---------------------------
def find_nist_root() -> Path | None:
    for cand in [Path("data/nist_vectors"), Path("data/NIST_VECTORS"), Path("data/nist"), Path("data/NIST")]:
        if cand.exists() and cand.is_dir():
            return cand
    return None


def parse_nist_sizes() -> pd.DataFrame:
    root = find_nist_root()
    if root is None:
        return pd.DataFrame()

    exts = {".rsp", ".txt", ".kat", ".req", ".out", ".log", ".dat"}
    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in exts or (suf == ".gz" and any(p.name.lower().endswith(e + ".gz") for e in exts)):
            files.append(p)

    if not files:
        return pd.DataFrame()

    pk_labels = ["pk", "public_key", "publickey", "public key"]
    ct_labels = ["ct", "ciphertext", "cipher_text", "cipher text"]
    ss_labels = ["ss", "shared_secret", "sharedsecret", "shared secret"]

    def extract_hex_bytes(txt: str, labels: list[str]) -> float:
        for lab in labels:
            m = re.search(rf"^\s*{re.escape(lab)}\s*[:=]\s*([0-9A-Fa-f]+)\s*$", txt, flags=re.MULTILINE)
            if m:
                h = m.group(1).strip()
                if len(h) >= 2:
                    return float(len(h) // 2)
        return float("nan")

    rows = []
    for p in files:
        txt = _read_text(p)
        if not txt:
            continue
        alg = algo_norm(str(p) + " " + txt[:8000])
        if alg not in {"Kyber512", "Kyber768", "Kyber1024"}:
            continue

        pk = extract_hex_bytes(txt, pk_labels)
        ct = extract_hex_bytes(txt, ct_labels)
        ss = extract_hex_bytes(txt, ss_labels)

        if np.isnan(pk) and np.isnan(ct) and np.isnan(ss):
            continue

        rows.append({"algorithm": alg, "nist_pk_bytes": pk, "nist_ct_bytes": ct, "nist_ss_bytes": ss})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).groupby("algorithm", as_index=False).median(numeric_only=True)
    return df


def liboqs_sizes() -> pd.DataFrame:
    if oqs is None:
        return pd.DataFrame()
    rows = []
    for alg in ["Kyber512", "Kyber768", "Kyber1024", "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]:
        try:
            kem = oqs.KeyEncapsulation(alg)
            det = kem.details
            rows.append(
                {
                    "algorithm": algo_norm(alg),
                    "oqs_pk_bytes": float(det.get("length_public_key", np.nan)),
                    "oqs_ct_bytes": float(det.get("length_ciphertext", np.nan)),
                    "oqs_ss_bytes": float(det.get("length_shared_secret", np.nan)),
                }
            )
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).groupby("algorithm", as_index=False).median(numeric_only=True)


# ---------------------------
# Plot builders
# ---------------------------
def fig10a_latency(ours_samples: pd.DataFrame, sup_us: pd.DataFrame, out_dir: Path) -> None:
    """
    Median + IQR errorbars per op; grouped by algorithm; series = ours vs supercop
    """
    set_ieee_style()

    ours_samples = ours_samples.copy()
    ours_samples["algorithm"] = ours_samples["algorithm"].map(algo_norm)

    def summarize_samples(df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for alg, g in df.groupby("algorithm"):
            for op in ["keygen_us", "encaps_us", "decaps_us"]:
                q1 = float(g[op].quantile(0.25))
                med = float(g[op].quantile(0.50))
                q3 = float(g[op].quantile(0.75))
                rows.append({"algorithm": alg, "op": op, "q1": q1, "med": med, "q3": q3})
        return pd.DataFrame(rows)

    ours_sum = summarize_samples(ours_samples)

    sup_sum = pd.DataFrame()
    if isinstance(sup_us, pd.DataFrame) and (not sup_us.empty) and ("algorithm" in sup_us.columns):
        # treat as "one sample" -> no IQR; use med only
        tmp = []
        for _, r in sup_us.iterrows():
            alg = algo_norm(r["algorithm"])
            tmp.append({"algorithm": alg, "op": "keygen_us", "q1": np.nan, "med": float(r["keygen_us"]), "q3": np.nan})
            tmp.append({"algorithm": alg, "op": "encaps_us", "q1": np.nan, "med": float(r["encaps_us"]), "q3": np.nan})
            tmp.append({"algorithm": alg, "op": "decaps_us", "q1": np.nan, "med": float(r["decaps_us"]), "q3": np.nan})
        sup_sum = pd.DataFrame(tmp)

    algos = sorted(set(ours_sum["algorithm"]) | (set(sup_sum["algorithm"]) if not sup_sum.empty else set()))
    ops = [("keygen_us", "KeyGen"), ("encaps_us", "Encaps"), ("decaps_us", "Decaps")]

    fig = plt.figure(figsize=(11.2, 4.3))
    ax = plt.gca()

    x = np.arange(len(algos))
    width = 0.22
    op_offsets = [-0.28, 0.00, 0.28]

    def get_row(df, alg, op):
        sub = df[(df["algorithm"] == alg) & (df["op"] == op)]
        if sub.empty:
            return None
        return sub.iloc[0]

    for j, (op, op_lab) in enumerate(ops):
        # ours
        meds = []
        yerr_lo = []
        yerr_hi = []
        for a in algos:
            r = get_row(ours_sum, a, op)
            if r is None:
                meds.append(np.nan); yerr_lo.append(0.0); yerr_hi.append(0.0)
            else:
                meds.append(float(r["med"]))
                yerr_lo.append(float(r["med"] - r["q1"]))
                yerr_hi.append(float(r["q3"] - r["med"]))
        meds = np.array(meds, dtype=float)
        ax.bar(x + op_offsets[j] - width/2, meds, width=width, label=f"{op_lab} — This work")
        ax.errorbar(
            x + op_offsets[j] - width/2, meds,
            yerr=np.vstack([yerr_lo, yerr_hi]),
            fmt="none", capsize=3, linewidth=1
        )

        # supercop (optional)
        if not sup_sum.empty:
            meds2 = []
            for a in algos:
                r2 = get_row(sup_sum, a, op)
                meds2.append(np.nan if r2 is None else float(r2["med"]))
            meds2 = np.array(meds2, dtype=float)
            ax.bar(x + op_offsets[j] + width/2, meds2, width=width, label=f"{op_lab} — SUPERCOP")

    ax.set_xticks(x)
    ax.set_xticklabels(algos, rotation=15, ha="right")
    ax.set_ylabel("Latency (µs), median (IQR)")
    title = "Figure 10a: ML-KEM/Kyber latency comparison (real measurements)"
    ax.set_title(title)
    ax.legend(ncol=3, frameon=False)
    ax.set_axisbelow(True)

    save3(fig, out_dir / "fig10a_kem_latency_vs_supercop")


def fig10b_sizes(oqs_df: pd.DataFrame, nist_df: pd.DataFrame, out_dir: Path) -> None:
    """
    Grouped bars: pk/ct/ss sizes, liboqs vs NIST(KAT) if available.
    """
    set_ieee_style()

    oqs_ok = isinstance(oqs_df, pd.DataFrame) and (not oqs_df.empty) and ("algorithm" in oqs_df.columns)
    nist_ok = isinstance(nist_df, pd.DataFrame) and (not nist_df.empty) and ("algorithm" in nist_df.columns)

    if not oqs_ok and not nist_ok:
        print("NOTE: No size data for Figure 10b; skipping.")
        return

    algos = sorted(
        (set(oqs_df["algorithm"].tolist()) if oqs_ok else set())
        | (set(nist_df["algorithm"].tolist()) if nist_ok else set())
    )
    if not algos:
        print("NOTE: No algorithms for Figure 10b; skipping.")
        return

    def get(df, alg, col):
        if df is None or df.empty or ("algorithm" not in df.columns) or (col not in df.columns):
            return np.nan
        sub = df[df["algorithm"] == alg]
        if sub.empty:
            return np.nan
        return float(pd.to_numeric(sub[col], errors="coerce").median())

    fields = [("pk", "Public key"), ("ct", "Ciphertext"), ("ss", "Shared secret")]
    fig = plt.figure(figsize=(11.2, 4.2))
    ax = plt.gca()

    x = np.arange(len(algos))
    width = 0.32
    group_offsets = [-0.45, 0.0, 0.45]

    for j, (short, lab) in enumerate(fields):
        base = group_offsets[j]
        oqs_vals = np.array([get(oqs_df, a, f"oqs_{short}_bytes") for a in algos], dtype=float)
        if oqs_ok and np.isfinite(oqs_vals).any():
            ax.bar(x + base - width/2, oqs_vals, width=width, label=f"{lab} — liboqs")

        nist_vals = np.array([get(nist_df, a, f"nist_{short}_bytes") for a in algos], dtype=float)
        if nist_ok and np.isfinite(nist_vals).any():
            ax.bar(x + base + width/2, nist_vals, width=width, label=f"{lab} — NIST KAT")

    ax.set_xticks(x)
    ax.set_xticklabels(algos, rotation=15, ha="right")
    ax.set_ylabel("Size (bytes)")
    ax.set_title("Figure 10b: Parameter sizes (bytes) — liboqs vs NIST KAT (if available)")
    ax.legend(ncol=3, frameon=False)
    ax.set_axisbelow(True)

    save3(fig, out_dir / "fig10b_kem_sizes_vs_nist")


def main() -> None:
    out_dir = Path("results/figures")
    ensure_dir(out_dir)

    ours = load_ours_samples_us()
    hz = cpu_hz_estimate()

    sup_cycles = parse_supercop_cycles(Path("data/SUPERCOP"))
    sup_us = supercop_cycles_to_us(sup_cycles, hz) if not sup_cycles.empty else pd.DataFrame()

    oqs_df = liboqs_sizes()
    nist_df = parse_nist_sizes()

    fig10a_latency(ours, sup_us, out_dir)
    fig10b_sizes(oqs_df if oqs_df is not None else pd.DataFrame(),
                 nist_df if nist_df is not None else pd.DataFrame(),
                 out_dir)

    print("OK: Figure 10 outputs written to results/figures/")
    if nist_df is None or nist_df.empty:
        root = find_nist_root()
        print(f"NOTE: NIST KAT sizes not parsed (root={root}). Figure 10b will show liboqs-only.")


if __name__ == "__main__":
    main()
