#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
micro_bench.py — micro-benchmarks AES-256-GCM + (ML-)KEM (Kyber/ML-KEM) via liboqs.

But: compatibilité avec run_full_pipeline.sh qui appelle:
  python -m src.benchmarks.micro_bench aes ...
  python -m src.benchmarks.micro_bench kyber ...

Sorties:
  - AES: CSV avec colonnes: plaintext_size, enc_latency_ms, dec_latency_ms, enc_MBps, dec_MBps
  - KEM: CSV summary (micro_kyber.csv) + samples (kem_samples_us.csv) dans le même dossier.
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    import oqs  # liboqs-python
    _OQS_OK = True
except Exception:
    _OQS_OK = False


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


# ----------------------------- AES-256-GCM ----------------------------- #

def bench_aes(iterations: int, sizes: List[int]) -> pd.DataFrame:
    key = os.urandom(32)
    aes = AESGCM(key)
    aad = b"hybrid-secure-bigdata"
    nonce = os.urandom(12)

    rows = []
    for sz in sizes:
        pt = os.urandom(sz)

        # Warm-up (petit)
        for _ in range(min(20, iterations // 10 or 1)):
            ct = aes.encrypt(nonce, pt, aad)
            _ = aes.decrypt(nonce, ct, aad)

        enc_ns = []
        dec_ns = []
        for _ in range(iterations):
            t0 = time.perf_counter_ns()
            ct = aes.encrypt(nonce, pt, aad)
            t1 = time.perf_counter_ns()
            _ = aes.decrypt(nonce, ct, aad)
            t2 = time.perf_counter_ns()
            enc_ns.append(t1 - t0)
            dec_ns.append(t2 - t1)

        enc_ms = float(np.mean(enc_ns) / 1e6)
        dec_ms = float(np.mean(dec_ns) / 1e6)

        enc_s = enc_ms / 1000.0
        dec_s = dec_ms / 1000.0
        enc_MBps = (sz / (1024.0 * 1024.0)) / max(enc_s, 1e-12)
        dec_MBps = (sz / (1024.0 * 1024.0)) / max(dec_s, 1e-12)

        rows.append({
            "plaintext_size": int(sz),
            "enc_latency_ms": enc_ms,
            "dec_latency_ms": dec_ms,
            "enc_MBps": float(enc_MBps),
            "dec_MBps": float(dec_MBps),
        })

    return pd.DataFrame(rows)


# ----------------------------- KEM (Kyber / ML-KEM) ----------------------------- #

@dataclass
class KemOne:
    algorithm: str
    keygen_us: float
    encaps_us: float
    decaps_us: float


def bench_kem(algorithms: List[str], iterations: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if not _OQS_OK:
        raise SystemExit("ERROR: liboqs-python (oqs) not installed or import failed.")

    enabled = set(oqs.get_enabled_kem_mechanisms())
    algos = [a for a in algorithms if a in enabled]
    if not algos:
        raise SystemExit(f"ERROR: none of these KEM mechanisms are enabled: {algorithms}")

    # IMPORTANT: on évite totalement load_secret_key/import_secret_key
    # (API variable selon versions). On garde le même objet kem pour keygen->decap.
    sample_rows = []
    summary_rows: List[KemOne] = []

    for alg in algos:
        kem = oqs.KeyEncapsulation(alg)

        kg_us = []
        en_us = []
        de_us = []

        # warm-up
        for _ in range(min(30, iterations // 10 or 1)):
            pk = kem.generate_keypair()
            ct, ss1 = kem.encap_secret(pk)
            ss2 = kem.decap_secret(ct)
            if ss1 != ss2:
                raise RuntimeError(f"KEM mismatch during warmup for {alg}")

        for _ in range(iterations):
            t0 = time.perf_counter_ns()
            pk = kem.generate_keypair()
            t1 = time.perf_counter_ns()
            ct, ss1 = kem.encap_secret(pk)
            t2 = time.perf_counter_ns()
            ss2 = kem.decap_secret(ct)
            t3 = time.perf_counter_ns()

            if ss1 != ss2:
                # Si ça arrive, c’est un problème sérieux (API/usage/bug)
                raise AssertionError(f"KEM shared secret mismatch for {alg}")

            kg = (t1 - t0) / 1e3
            en = (t2 - t1) / 1e3
            de = (t3 - t2) / 1e3
            kg_us.append(kg)
            en_us.append(en)
            de_us.append(de)

            sample_rows.append({
                "algorithm": alg,
                "keygen_us": float(kg),
                "encaps_us": float(en),
                "decaps_us": float(de),
            })

        # summary (médiane + p95 possible, mais on garde simple et stable)
        summary_rows.append(KemOne(
            algorithm=alg,
            keygen_us=float(np.median(kg_us)),
            encaps_us=float(np.median(en_us)),
            decaps_us=float(np.median(de_us)),
        ))

    df_samples = pd.DataFrame(sample_rows)
    df_summary = pd.DataFrame([s.__dict__ for s in summary_rows])
    return df_samples, df_summary


# ----------------------------- CLI ----------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)

    ap_aes = sub.add_parser("aes", help="AES-256-GCM microbench")
    ap_aes.add_argument("--iterations", type=int, default=1000)
    ap_aes.add_argument("--sizes", type=int, nargs="+",
                        default=[1024, 4096, 16384, 65536, 262144, 1048576])
    ap_aes.add_argument("--output", required=True, help="Path to CSV output (e.g., results/data/micro_aes.csv)")

    ap_kem = sub.add_parser("kyber", help="KEM microbench via liboqs (Kyber + ML-KEM)")
    ap_kem.add_argument("--iterations", type=int, default=500)
    ap_kem.add_argument("--algorithms", nargs="+",
                        default=["Kyber512", "Kyber768", "Kyber1024", "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"])
    ap_kem.add_argument("--output", required=True, help="Path to CSV summary output (e.g., results/data/micro_kyber.csv)")

    args = ap.parse_args()
    out = Path(args.output)
    _ensure_parent(out)

    if args.mode == "aes":
        df = bench_aes(args.iterations, args.sizes)
        df.to_csv(out, index=False)
        print(f"OK: wrote {out}")

    elif args.mode == "kyber":
        df_samples, df_summary = bench_kem(args.algorithms, args.iterations)
        df_summary.to_csv(out, index=False)
        # écrit aussi un fichier samples dans le même dossier (utile pour fig10/boxplots)
        samples_path = out.parent / "kem_samples_us.csv"
        df_samples.to_csv(samples_path, index=False)
        print(f"OK: wrote {out}")
        print(f"OK: wrote {samples_path}")


if __name__ == "__main__":
    main()
