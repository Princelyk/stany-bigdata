#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Figure 10 — KEM vs SUPERCOP + NIST KAT sizes (publication-ready)

Inputs:
  - results/data/kem_samples_us.csv (preferred)
    columns: algorithm(optional), keygen_us, encaps_us, decaps_us
  - OR results/data/micro_kyber.csv (fallback)

Reference inputs (optional):
  - data/SUPERCOP/** (best-effort parsing of cycles)
  - data/nist_vectors/** or data/NIST_VECTORS/** (best-effort parsing of KAT sizes)

Outputs:
  - results/figures/fig10_kem_vs_supercop_cycles.{pdf,png,svg}
  - results/figures/fig10_kem_sizes_vs_nist.{pdf,png,svg}

Notes:
- SUPERCOP often reports cycles. We convert our µs to cycles using estimated CPU frequency.
- NIST KAT files come in many layouts. We scan many extensions and multiple label variants.
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


# -----------------------------
# Helpers
# -----------------------------
def cpu_hz_estimate() -> float:
    if psutil is not None:
        f = psutil.cpu_freq()
        if f and f.current and f.current > 0:
            return float(f.current) * 1e6  # MHz -> Hz
    try:
        txt = Path("/proc/cpuinfo").read_text(errors="ignore")
        m = re.search(r"cpu MHz\s*:\s*([0-9.]+)", txt)
        if m:
            return float(m.group(1)) * 1e6
    except Exception:
        pass
    return 3.0e9


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def save3(fig, stem: Path) -> None:
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(stem.with_suffix(".png"), bbox_inches="tight", dpi=300)
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def _algo_normalize(name: str) -> str:
    s = str(name).lower().replace("_", "-").replace(" ", "")

    # Normalize ML-KEM names into Kyber-style labels for comparison plots
    if "ml-kem-512" in s or "mlkem512" in s or ("mlkem" in s and "512" in s):
        return "Kyber512"
    if "ml-kem-768" in s or "mlkem768" in s or ("mlkem" in s and "768" in s):
        return "Kyber768"
    if "ml-kem-1024" in s or "mlkem1024" in s or ("mlkem" in s and "1024" in s):
        return "Kyber1024"

    if "kyber512" in s or ("kyber" in s and "512" in s):
        return "Kyber512"
    if "kyber768" in s or ("kyber" in s and "768" in s):
        return "Kyber768"
    if "kyber1024" in s or ("kyber" in s and "1024" in s):
        return "Kyber1024"

    return str(name)


def _read_text_best_effort(p: Path, max_bytes: int = 2_000_000) -> str:
    """
    Read text file best-effort, supports .gz.
    """
    try:
        if p.suffix.lower() == ".gz":
            with gzip.open(p, "rt", errors="ignore") as f:
                return f.read(max_bytes)
        return p.read_text(errors="ignore")[:max_bytes]
    except Exception:
        return ""


# -----------------------------
# Our microbench (us)
# -----------------------------
def load_our_kem_us() -> pd.DataFrame:
    p = Path("results/data/kem_samples_us.csv")
    if p.exists():
        df = pd.read_csv(p)
        df.columns = [c.lower() for c in df.columns]

        for c in ["keygen_us", "encaps_us", "decaps_us"]:
            if c not in df.columns:
                raise RuntimeError(f"kem_samples_us.csv missing {c}. Found: {list(df.columns)}")

        if "algorithm" not in df.columns:
            df["algorithm"] = "Kyber1024"

        df["algorithm"] = df["algorithm"].astype(str).map(_algo_normalize)

        for c in ["keygen_us", "encaps_us", "decaps_us"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=["keygen_us", "encaps_us", "decaps_us", "algorithm"]).copy()

        g = (
            df.groupby("algorithm", as_index=False)
            .agg(
                keygen_us=("keygen_us", "median"),
                encaps_us=("encaps_us", "median"),
                decaps_us=("decaps_us", "median"),
            )
        )
        return g

    p2 = Path("results/data/micro_kyber.csv")
    if not p2.exists():
        raise SystemExit("Missing KEM microbench: results/data/kem_samples_us.csv OR results/data/micro_kyber.csv")

    df = pd.read_csv(p2)
    if df.empty:
        raise SystemExit("micro_kyber.csv is empty")

    cols = list(df.columns)
    lower = {c: c.lower() for c in cols}

    def find_col(cands):
        for c in cols:
            if lower[c] in cands:
                return c
        return None

    alg_col = find_col({"algorithm", "alg", "kem"})
    if alg_col is None:
        df["algorithm"] = "Kyber1024"
        alg_col = "algorithm"

    k_us = find_col({"keygen_us", "keypair_us"})
    e_us = find_col({"encaps_us", "enc_us"})
    d_us = find_col({"decaps_us", "dec_us"})

    k_ms = find_col({"keygen_ms", "keypair_ms", "keygen_median_ms", "keypair_median_ms"})
    e_ms = find_col({"encaps_ms", "enc_median_ms"})
    d_ms = find_col({"decaps_ms", "dec_median_ms"})

    out = pd.DataFrame()
    out["algorithm"] = df[alg_col].astype(str).map(_algo_normalize)

    if k_us and e_us and d_us:
        out["keygen_us"] = pd.to_numeric(df[k_us], errors="coerce")
        out["encaps_us"] = pd.to_numeric(df[e_us], errors="coerce")
        out["decaps_us"] = pd.to_numeric(df[d_us], errors="coerce")
    elif k_ms and e_ms and d_ms:
        out["keygen_us"] = pd.to_numeric(df[k_ms], errors="coerce") * 1000.0
        out["encaps_us"] = pd.to_numeric(df[e_ms], errors="coerce") * 1000.0
        out["decaps_us"] = pd.to_numeric(df[d_ms], errors="coerce") * 1000.0
    else:
        raise RuntimeError(f"Could not infer timing columns from micro_kyber.csv. Columns: {cols}")

    out = out.dropna().copy()
    g = (
        out.groupby("algorithm", as_index=False)
        .agg(
            keygen_us=("keygen_us", "median"),
            encaps_us=("encaps_us", "median"),
            decaps_us=("decaps_us", "median"),
        )
    )
    return g


# -----------------------------
# SUPERCOP cycles parsing — best effort
# -----------------------------
def parse_supercop_cycles(root: Path = Path("data/SUPERCOP")) -> pd.DataFrame:
    if not root.exists():
        return pd.DataFrame()

    speed_files = [
        p
        for p in root.rglob("*")
        if p.is_file()
        and (
            "speed" in p.name.lower()
            or "bench" in p.name.lower()
            or "cpucycles" in p.name.lower()
            or "cycles" in p.name.lower()
        )
    ]
    if not speed_files:
        return pd.DataFrame()

    rows = []
    for p in speed_files:
        txt = _read_text_best_effort(p)
        if not txt:
            continue

        guess = _algo_normalize(str(p) + " " + txt[:5000])
        if "Kyber" not in guess:
            continue

        def find_cycles(keys):
            for key in keys:
                m = re.search(rf"{key}\s*[:=]\s*([0-9]+)", txt, flags=re.IGNORECASE)
                if m:
                    return float(m.group(1))
                m2 = re.search(rf"{key}.*?([0-9]+)\s*cycles", txt, flags=re.IGNORECASE)
                if m2:
                    return float(m2.group(1))
            return np.nan

        keygen = find_cycles(["keypair", "keygen"])
        encaps = find_cycles(["encaps", "enc"])
        decaps = find_cycles(["decaps", "dec"])

        if np.isnan(keygen) and np.isnan(encaps) and np.isnan(decaps):
            continue

        rows.append(
            {
                "algorithm": guess,
                "keygen_cycles": keygen,
                "encaps_cycles": encaps,
                "decaps_cycles": decaps,
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    g = (
        df.groupby("algorithm", as_index=False)
        .agg(
            keygen_cycles=("keygen_cycles", "median"),
            encaps_cycles=("encaps_cycles", "median"),
            decaps_cycles=("decaps_cycles", "median"),
        )
    )
    return g


# -----------------------------
# NIST KAT size parsing (real structure robust)
# -----------------------------
def _find_nist_root() -> Path | None:
    # prefer your real folder name
    for cand in [Path("data/nist_vectors"), Path("data/NIST_VECTORS"), Path("data/nist"), Path("data/NIST")]:
        if cand.exists() and cand.is_dir():
            return cand
    return None


def _infer_algo_from_path_or_text(path: Path, txt: str) -> str | None:
    blob = f"{str(path)} {txt[:8000]}"
    alg = _algo_normalize(blob)
    if alg in {"Kyber512", "Kyber768", "Kyber1024"}:
        return alg
    return None


def _extract_first_hex_len(txt: str, labels: list[str]) -> float:
    """
    Find first occurrence of a hex value for any label variant.
    Return bytes length (hex_len/2), or NaN.
    Handles formats like:
      pk = A1B2...
      pk: A1B2...
      public_key = ...
    """
    for lab in labels:
        # multiline robust: label then = or : then hex
        pat = rf"^\s*{re.escape(lab)}\s*[:=]\s*([0-9A-Fa-f]+)\s*$"
        m = re.search(pat, txt, flags=re.MULTILINE)
        if m:
            hexs = m.group(1).strip()
            if len(hexs) >= 2:
                return float(len(hexs) // 2)
    return float("nan")


def parse_nist_kat_sizes() -> pd.DataFrame:
    root = _find_nist_root()
    if root is None:
        return pd.DataFrame()

    # NIST KAT files vary; scan common text-ish extensions + gz
    exts = {".rsp", ".txt", ".kat", ".req", ".out", ".log", ".md", ".csv", ".dat"}
    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in exts or (suf == ".gz" and p.name.lower().endswith(tuple([e + ".gz" for e in exts]))):
            files.append(p)

    if not files:
        return pd.DataFrame()

    # label variants
    pk_labels = ["pk", "publickey", "public_key", "public key"]
    sk_labels = ["sk", "secretkey", "secret_key", "secret key", "privatekey", "private_key"]
    ct_labels = ["ct", "ciphertext", "cipher_text", "cipher text"]
    ss_labels = ["ss", "sharedsecret", "shared_secret", "shared secret", "k", "key"]

    rows = []
    for p in files:
        txt = _read_text_best_effort(p)
        if not txt:
            continue

        alg = _infer_algo_from_path_or_text(p, txt)
        if alg is None:
            continue

        pk = _extract_first_hex_len(txt, pk_labels)
        sk = _extract_first_hex_len(txt, sk_labels)
        ct = _extract_first_hex_len(txt, ct_labels)
        ss = _extract_first_hex_len(txt, ss_labels)

        # accept partial
        if np.isnan(pk) and np.isnan(sk) and np.isnan(ct) and np.isnan(ss):
            continue

        rows.append(
            {
                "algorithm": alg,
                "nist_pk_bytes": pk,
                "nist_sk_bytes": sk,
                "nist_ct_bytes": ct,
                "nist_ss_bytes": ss,
                "source_file": str(p),
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    g = (
        df.groupby("algorithm", as_index=False)
        .agg(
            nist_pk_bytes=("nist_pk_bytes", "median"),
            nist_sk_bytes=("nist_sk_bytes", "median"),
            nist_ct_bytes=("nist_ct_bytes", "median"),
            nist_ss_bytes=("nist_ss_bytes", "median"),
        )
    )
    return g


def liboqs_sizes(algorithms: list[str]) -> pd.DataFrame:
    if oqs is None:
        return pd.DataFrame()

    rows = []
    for alg in algorithms:
        try:
            kem = oqs.KeyEncapsulation(alg)
            det = kem.details
            rows.append(
                {
                    "algorithm": _algo_normalize(alg),
                    "oqs_pk_bytes": float(det.get("length_public_key", np.nan)),
                    "oqs_sk_bytes": float(det.get("length_secret_key", np.nan)),
                    "oqs_ct_bytes": float(det.get("length_ciphertext", np.nan)),
                    "oqs_ss_bytes": float(det.get("length_shared_secret", np.nan)),
                }
            )
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).groupby("algorithm", as_index=False).median(numeric_only=True)
    return df


# -----------------------------
# Plots
# -----------------------------
def plot_cycles(our_us: pd.DataFrame, supercop: pd.DataFrame, out_dir: Path) -> None:
    hz = cpu_hz_estimate()

    if our_us is None or our_us.empty:
        raise SystemExit("No KEM microbench data found to plot (our_us is empty).")

    ours = our_us.copy()
    if "algorithm" not in ours.columns:
        ours["algorithm"] = "Kyber1024"

    for c in ["keygen_us", "encaps_us", "decaps_us"]:
        if c not in ours.columns:
            raise RuntimeError(f"Missing column in our KEM data: {c}. Found: {list(ours.columns)}")
        ours[c] = pd.to_numeric(ours[c], errors="coerce")

    ours = ours.dropna(subset=["algorithm", "keygen_us", "encaps_us", "decaps_us"]).copy()
    ours["algorithm"] = ours["algorithm"].astype(str).map(_algo_normalize)

    ours["keygen_cycles"] = ours["keygen_us"] * 1e-6 * hz
    ours["encaps_cycles"] = ours["encaps_us"] * 1e-6 * hz
    ours["decaps_cycles"] = ours["decaps_us"] * 1e-6 * hz

    sup = supercop.copy() if isinstance(supercop, pd.DataFrame) else pd.DataFrame()
    if not sup.empty:
        if "algorithm" not in sup.columns:
            sup = pd.DataFrame()
        else:
            sup["algorithm"] = sup["algorithm"].astype(str).map(_algo_normalize)

    algos = sorted(set(ours["algorithm"].tolist()) | (set(sup["algorithm"].tolist()) if not sup.empty else set()))
    if not algos:
        raise SystemExit("No Kyber/ML-KEM algorithms found to plot in Figure 10a.")

    def get(df, alg, col):
        sub = df[df["algorithm"] == alg]
        if sub.empty or col not in df.columns:
            return np.nan
        return float(pd.to_numeric(sub[col], errors="coerce").median())

    ops = [("keygen_cycles", "KeyGen"), ("encaps_cycles", "Encaps"), ("decaps_cycles", "Decaps")]
    width = 0.36

    plt.rcParams["figure.dpi"] = 300
    fig = plt.figure(figsize=(11.5, 5.3))
    ax = plt.gca()

    x = np.arange(len(algos))
    for j, (col, lab) in enumerate(ops):
        offset = (j - 1) * 1.15
        ours_vals = np.array([get(ours, a, col) for a in algos], dtype=float)
        ax.bar(x + offset - width / 2, ours_vals, width=width, label=f"{lab} — This work")

        if not sup.empty:
            sup_vals = np.array([get(sup, a, col) for a in algos], dtype=float)
            if np.isfinite(sup_vals).any():
                ax.bar(x + offset + width / 2, sup_vals, width=width, label=f"{lab} — SUPERCOP")

    ax.set_xticks(x)
    ax.set_xticklabels(algos, rotation=20, ha="right")
    ax.set_ylabel("Cycles (median)")
    title = "Figure 10a: ML-KEM/Kyber — cycles (median)"
    title += " vs SUPERCOP" if not sup.empty else " [SUPERCOP not found]"
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)

    ax.text(
        0.99, 1.02, f"Cycles computed with CPU freq ≈ {hz/1e9:.2f} GHz",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=9
    )
    ax.legend(ncol=3, fontsize=8)

    save3(fig, out_dir / "fig10_kem_vs_supercop_cycles")


def plot_sizes(oqs_df: pd.DataFrame, nist_df: pd.DataFrame, out_dir: Path) -> None:
    oqs_ok = isinstance(oqs_df, pd.DataFrame) and (not oqs_df.empty) and ("algorithm" in oqs_df.columns)
    nist_ok = isinstance(nist_df, pd.DataFrame) and (not nist_df.empty) and ("algorithm" in nist_df.columns)

    if not oqs_ok and not nist_ok:
        print("NOTE: No size data (liboqs or NIST KAT) found; skipping Figure 10b.")
        return

    algos = sorted(
        (set(oqs_df["algorithm"].tolist()) if oqs_ok else set())
        | (set(nist_df["algorithm"].tolist()) if nist_ok else set())
    )
    if not algos:
        print("NOTE: Empty algorithm set for size plotting; skipping Figure 10b.")
        return

    def get(df, alg, col):
        if df is None or df.empty or ("algorithm" not in df.columns) or (col not in df.columns):
            return np.nan
        sub = df[df["algorithm"] == alg]
        if sub.empty:
            return np.nan
        return float(pd.to_numeric(sub[col], errors="coerce").median())

    fields = [("pk", "Public key"), ("ct", "Ciphertext"), ("ss", "Shared secret")]

    plt.rcParams["figure.dpi"] = 300
    fig = plt.figure(figsize=(11.5, 5.3))
    ax = plt.gca()

    width = 0.35
    x = np.arange(len(algos))

    for j, (short, lab) in enumerate(fields):
        base = (j - 1) * 1.25
        oqs_vals = np.array([get(oqs_df, a, f"oqs_{short}_bytes") for a in algos], dtype=float)
        nist_vals = np.array([get(nist_df, a, f"nist_{short}_bytes") for a in algos], dtype=float)

        if oqs_ok and np.isfinite(oqs_vals).any():
            ax.bar(x + base - width / 2, oqs_vals, width=width, label=f"{lab} — liboqs")
        if nist_ok and np.isfinite(nist_vals).any():
            ax.bar(x + base + width / 2, nist_vals, width=width, label=f"{lab} — NIST KAT")

    ax.set_xticks(x)
    ax.set_xticklabels(algos, rotation=20, ha="right")
    ax.set_ylabel("Bytes")

    title = "Figure 10b: Tailles (bytes)"
    if oqs_ok and nist_ok:
        title += " — liboqs vs NIST KAT (median)"
    elif oqs_ok:
        title += " — liboqs only (NIST KAT not parsed)"
    else:
        title += " — NIST KAT only (liboqs sizes unavailable)"
    ax.set_title(title)

    ax.grid(axis="y", alpha=0.3)
    ax.legend(ncol=3, fontsize=8)

    save3(fig, out_dir / "fig10_kem_sizes_vs_nist")


def main() -> None:
    out_dir = Path("results/figures")
    ensure_dir(out_dir)

    our_us = load_our_kem_us()
    supercop = parse_supercop_cycles(Path("data/SUPERCOP"))

    # NEW: robust discovery based on your real folder name
    nist = parse_nist_kat_sizes()

    algs = ["Kyber512", "Kyber768", "Kyber1024", "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]
    oqs_df = liboqs_sizes(algs)

    plot_cycles(our_us, supercop, out_dir)
    plot_sizes(oqs_df if not oqs_df.empty else pd.DataFrame(), nist if isinstance(nist, pd.DataFrame) else pd.DataFrame(), out_dir)

    print("OK: Figure 10 generated in results/figures/")
    if nist is None or nist.empty:
        root = _find_nist_root()
        print(f"NOTE: NIST KAT not parsed (root={root}). Figure 10b may be 'liboqs only'.")


if __name__ == "__main__":
    main()

