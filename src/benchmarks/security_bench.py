#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
security_bench.py

Security checks (NIST/SUPERCOP-style sanity):
- AES-256-GCM: deterministic roundtrip + tamper tests + randomized trials
- KEM (Kyber/ML-KEM): roundtrip consistency across iterations

Outputs:
  - results/data/metrics_security.csv   (for Figure 9)
  - results/data/security_aes_detail.csv
  - results/data/security_kem_detail.csv
"""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    import oqs
except Exception:
    oqs = None


def aes_tests(trials: int = 200) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    detail = []

    # 1) Deterministic “KAT-like” roundtrip
    key = b"\x00" * 32
    nonce = b"\x11" * 12
    aad = b"nist-like-aad"
    pt = b"hello-nist-like-vector"
    aes = AESGCM(key)

    ct = aes.encrypt(nonce, pt, aad)
    out = aes.decrypt(nonce, ct, aad)
    ok = (out == pt)
    detail.append({"test": "aes_roundtrip_deterministic", "pass": float(ok), "details": "ok" if ok else "mismatch"})

    # 2) Tamper tests: AAD / CT / nonce modifications must fail
    def must_fail(fn_name: str, mutate):
        try:
            ct2 = mutate(ct)
            aes.decrypt(nonce, ct2, aad)
            return False, f"{fn_name}: decrypt succeeded unexpectedly"
        except Exception:
            return True, "ok"

    ok1, d1 = must_fail("tamper_ciphertext", lambda x: x[:-1] + bytes([x[-1] ^ 0x01]))
    ok2, d2 = must_fail("tamper_tag", lambda x: x[:-16] + bytes([x[-16] ^ 0x01]) + x[-15:])
    try:
        aes.decrypt(nonce, ct, aad + b"x")
        ok3, d3 = False, "tamper_aad: decrypt succeeded unexpectedly"
    except Exception:
        ok3, d3 = True, "ok"
    try:
        aes.decrypt(b"\x22"*12, ct, aad)
        ok4, d4 = False, "tamper_nonce: decrypt succeeded unexpectedly"
    except Exception:
        ok4, d4 = True, "ok"

    detail.extend([
        {"test": "aes_tamper_ciphertext", "pass": float(ok1), "details": d1},
        {"test": "aes_tamper_tag", "pass": float(ok2), "details": d2},
        {"test": "aes_tamper_aad", "pass": float(ok3), "details": d3},
        {"test": "aes_tamper_nonce", "pass": float(ok4), "details": d4},
    ])

    # 3) Randomized trials
    passes = 0
    for i in range(trials):
        key = AESGCM.generate_key(bit_length=256)
        aes = AESGCM(key)
        nonce = secrets.token_bytes(12)
        aad = secrets.token_bytes(16)
        pt = secrets.token_bytes(1024)

        ct = aes.encrypt(nonce, pt, aad)
        out = aes.decrypt(nonce, ct, aad)
        ok = (out == pt)
        passes += int(ok)
        detail.append({"test": "aes_random_roundtrip", "pass": float(ok), "details": f"trial={i}"})

    rows.append({"test": "AES-GCM deterministic+tamper", "pass": float(all([ok, ok1, ok2, ok3, ok4]))})
    rows.append({"test": f"AES-GCM randomized ({trials})", "pass": float(passes == trials)})

    return pd.DataFrame(rows), pd.DataFrame(detail)


def kem_tests(iters: int = 200, algos: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if oqs is None:
        df = pd.DataFrame([{"test": "KEM import", "pass": 0.0}])
        det = pd.DataFrame([{"test": "KEM import", "pass": 0.0, "details": "oqs not installed"}])
        return df, det

    enabled = set(oqs.get_enabled_kem_mechanisms())
    requested = algos or ["Kyber512", "Kyber768", "Kyber1024", "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]
    chosen = [a for a in requested if a in enabled]
    if not chosen:
        chosen = sorted(enabled)[:3]

    summary_rows = []
    detail_rows = []

    for alg in chosen:
        ok_all = True
        for i in range(iters):
            with oqs.KeyEncapsulation(alg) as kem:
                pk = kem.generate_keypair()
                ct, ss1 = kem.encap_secret(pk)
                ss2 = kem.decap_secret(ct)
                ok = (ss1 == ss2)
                ok_all = ok_all and ok
                detail_rows.append({"test": f"kem_roundtrip_{alg}", "pass": float(ok), "details": f"iter={i}"})
                if not ok:
                    break
        summary_rows.append({"test": f"KEM roundtrip {alg} ({iters})", "pass": float(ok_all)})

    return pd.DataFrame(summary_rows), pd.DataFrame(detail_rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="results/data")
    ap.add_argument("--aes-trials", type=int, default=200)
    ap.add_argument("--kem-iters", type=int, default=200)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    aes_sum, aes_det = aes_tests(args.aes_trials)
    kem_sum, kem_det = kem_tests(args.kem_iters)

    # Combined for Figure 9 (expected columns: test, pass)
    all_sum = pd.concat([aes_sum, kem_sum], ignore_index=True)

    p_main = out_dir / "metrics_security.csv"
    p_aes = out_dir / "security_aes_detail.csv"
    p_kem = out_dir / "security_kem_detail.csv"

    all_sum.to_csv(p_main, index=False)
    aes_det.to_csv(p_aes, index=False)
    kem_det.to_csv(p_kem, index=False)

    print("✓", p_main)
    print("✓", p_aes)
    print("✓", p_kem)


if __name__ == "__main__":
    main()
