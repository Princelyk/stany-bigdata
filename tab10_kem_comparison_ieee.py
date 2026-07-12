#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Table 10 (IEEE/ACM-ready): KEM comparison (this work vs SUPERCOP vs NIST sizes)

Reads:
  - results/data/kem_samples_us.csv or results/data/micro_kyber.csv
  - data/SUPERCOP/** (optional)
  - data/nist_vectors/** or data/NIST_VECTORS/** (optional)

Writes:
  - results/tables/table10_kem_comparison.tex
  - results/tables/table10_kem_comparison.csv
"""

from __future__ import annotations

import re
import gzip
from pathlib import Path
import numpy as np
import pandas as pd

try:
    import psutil
except Exception:
    psutil = None

try:
    import oqs
except Exception:
    oqs = None


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


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


def cpu_hz_estimate() -> float:
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


def _read_text(p: Path, max_bytes: int = 2_000_000) -> str:
    try:
        if p.suffix.lower() == ".gz":
            with gzip.open(p, "rt", errors="ignore") as f:
                return f.read(max_bytes)
        return p.read_text(errors="ignore")[:max_bytes]
    except Exception:
        return ""


def load_ours_summary_us() -> pd.DataFrame:
    p = Path("results/data/kem_samples_us.csv")
    if p.exists():
        df = pd.read_csv(p)
        df.columns = [c.lower() for c in df.columns]
        if "algorithm" not in df.columns:
            df["algorithm"] = "Kyber1024"
        df["algorithm"] = df["algorithm"].astype(str).map(algo_norm)
        for c in ["keygen_us", "encaps_us", "decaps_us"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["algorithm", "keygen_us", "encaps_us", "decaps_us"]).copy()
        g = df.groupby("algorithm", as_index=False).median(numeric_only=True)
        return g[["algorithm", "keygen_us", "encaps_us", "decaps_us"]].copy()

    p2 = Path("results/data/micro_kyber.csv")
    if not p2.exists():
        raise SystemExit("Missing KEM data: results/data/kem_samples_us.csv OR results/data/micro_kyber.csv")

    df = pd.read_csv(p2)
    if "algorithm" not in df.columns:
        for cand in ["alg", "kem", "name"]:
            if cand in df.columns:
                df["algorithm"] = df[cand]
                break
        if "algorithm" not in df.columns:
            df["algorithm"] = "Kyber1024"
    df["algorithm"] = df["algorithm"].astype(str).map(algo_norm)

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

    out = out.dropna().groupby("algorithm", as_index=False).median(numeric_only=True)
    return out


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

        rows.append(
            {
                "algorithm": alg,
                "keygen_cycles": find_one(["keypair", "keygen"]),
                "encaps_cycles": find_one(["encaps", "enc"]),
                "decaps_cycles": find_one(["decaps", "dec"]),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.groupby("algorithm", as_index=False).median(numeric_only=True)


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

        rows.append(
            {
                "algorithm": alg,
                "nist_pk_bytes": extract_hex_bytes(txt, pk_labels),
                "nist_ct_bytes": extract_hex_bytes(txt, ct_labels),
                "nist_ss_bytes": extract_hex_bytes(txt, ss_labels),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.groupby("algorithm", as_index=False).median(numeric_only=True)


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
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.groupby("algorithm", as_index=False).median(numeric_only=True)


def to_latex_table(df: pd.DataFrame) -> str:
    # IEEE/ACM-safe LaTeX table (no vertical rules)
    cols = [
        "Algorithm",
        "KeyGen (µs)",
        "Encaps (µs)",
        "Decaps (µs)",
        "SUPERCOP KeyGen (cycles)",
        "SUPERCOP Encaps (cycles)",
        "SUPERCOP Decaps (cycles)",
        "Public key (bytes)",
        "Ciphertext (bytes)",
        "Shared secret (bytes)",
        "NIST pk/ct/ss (bytes)",
    ]

    def fmt(x):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "—"
        if isinstance(x, (int, np.integer)):
            return f"{int(x)}"
        if isinstance(x, (float, np.floating)):
            return f"{float(x):.2f}"
        return str(x)

    lines = []
    lines.append(r"\begin{table*}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{ML-KEM/Kyber comparison (this work vs SUPERCOP; sizes vs liboqs and NIST KAT when available).}")
    lines.append(r"\label{tab:kem_supercop_nist}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{lrrrrrrrccc l}")
    lines.append(r"\toprule")
    lines.append(" & ".join(cols) + r" \\")
    lines.append(r"\midrule")

    for _, r in df.iterrows():
        row = [
            r["algorithm"],
            fmt(r["keygen_us"]),
            fmt(r["encaps_us"]),
            fmt(r["decaps_us"]),
            fmt(r["supercop_keygen_cycles"]),
            fmt(r["supercop_encaps_cycles"]),
            fmt(r["supercop_decaps_cycles"]),
            fmt(r["oqs_pk_bytes"]),
            fmt(r["oqs_ct_bytes"]),
            fmt(r["oqs_ss_bytes"]),
            r["nist_sizes_str"],
        ]
        lines.append(" & ".join(row) + r" \\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table*}")
    return "\n".join(lines)


def main() -> None:
    out_dir = Path("results/tables")
    ensure_dir(out_dir)

    ours = load_ours_summary_us()
    sup = parse_supercop_cycles(Path("data/SUPERCOP"))
    nist = parse_nist_sizes()
    oqs_df = liboqs_sizes()

    df = ours.copy()
    df["algorithm"] = df["algorithm"].map(algo_norm)

    # merge supercop cycles
    if isinstance(sup, pd.DataFrame) and (not sup.empty) and ("algorithm" in sup.columns):
        sup = sup.copy()
        sup["algorithm"] = sup["algorithm"].map(algo_norm)
        sup = sup.rename(
            columns={
                "keygen_cycles": "supercop_keygen_cycles",
                "encaps_cycles": "supercop_encaps_cycles",
                "decaps_cycles": "supercop_decaps_cycles",
            }
        )
        df = df.merge(sup, on="algorithm", how="left")
    else:
        df["supercop_keygen_cycles"] = np.nan
        df["supercop_encaps_cycles"] = np.nan
        df["supercop_decaps_cycles"] = np.nan

    # merge liboqs sizes
    if isinstance(oqs_df, pd.DataFrame) and (not oqs_df.empty) and ("algorithm" in oqs_df.columns):
        oqs_df = oqs_df.copy()
        oqs_df["algorithm"] = oqs_df["algorithm"].map(algo_norm)
        df = df.merge(oqs_df, on="algorithm", how="left")
    else:
        df["oqs_pk_bytes"] = np.nan
        df["oqs_ct_bytes"] = np.nan
        df["oqs_ss_bytes"] = np.nan

    # merge NIST sizes (create a compact string)
    if isinstance(nist, pd.DataFrame) and (not nist.empty) and ("algorithm" in nist.columns):
        nist = nist.copy()
        nist["algorithm"] = nist["algorithm"].map(algo_norm)
        df = df.merge(nist, on="algorithm", how="left")
    else:
        df["nist_pk_bytes"] = np.nan
        df["nist_ct_bytes"] = np.nan
        df["nist_ss_bytes"] = np.nan

    def mk_nist_str(r):
        pk = r.get("nist_pk_bytes", np.nan)
        ct = r.get("nist_ct_bytes", np.nan)
        ss = r.get("nist_ss_bytes", np.nan)
        if (isinstance(pk, float) and np.isnan(pk)) and (isinstance(ct, float) and np.isnan(ct)) and (isinstance(ss, float) and np.isnan(ss)):
            return "—"
        def f(x):
            return "—" if (isinstance(x, float) and np.isnan(x)) else str(int(x)) if float(x).is_integer() else f"{float(x):.0f}"
        return f"{f(pk)}/{f(ct)}/{f(ss)}"

    df["nist_sizes_str"] = df.apply(mk_nist_str, axis=1)

    # tidy columns & order
    df = df.sort_values("algorithm").reset_index(drop=True)
    csv_path = out_dir / "table10_kem_comparison.csv"
    df.to_csv(csv_path, index=False)

    tex = to_latex_table(df)
    tex_path = out_dir / "table10_kem_comparison.tex"
    tex_path.write_text(tex, encoding="utf-8")

    print("OK:", str(csv_path))
    print("OK:", str(tex_path))


if __name__ == "__main__":
    main()
