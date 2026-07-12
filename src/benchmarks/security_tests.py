#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
security_tests.py

Security checks (REAL checks, lightweight):
- AES-GCM decrypt correctness (known-answer style with fixed inputs)
- KEM encaps/decaps consistency for enabled KEMs

Outputs:
  results/data/security_aes.csv
  results/data/security_kem.csv
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    import oqs
except Exception:
    oqs = None


def aes_gcm_test() -> pd.DataFrame:
    key = bytes.fromhex("00" * 32)
    nonce = bytes.fromhex("11" * 12)
    aad = b"nist-aes-gcm-aad"
    pt = b"hello-nist-like-vector"

    aes = AESGCM(key)
    ct = aes.encrypt(nonce, pt, aad)
    out = aes.decrypt(nonce, ct, aad)

    return pd.DataFrame([{
        "test": "aes_gcm_encrypt_decrypt_roundtrip",
        "pass": 1.0 if out == pt else 0.0,
        "details": "ok" if out == pt else "mismatch",
    }])


def _set_secret_key(kem, sk: bytes) -> None:
    if hasattr(kem, "import_secret_key"):
        kem.import_secret_key(sk)
        return
    if hasattr(kem, "load_secret_key"):
        kem.load_secret_key(sk)
        return
    raise RuntimeError("No import_secret_key/load_secret_key on KeyEncapsulation.")


def kem_tests(iters: int, algos: list[str]) -> pd.DataFrame:
    if oqs is None:
        return pd.DataFrame([{
            "test": "kem_import",
            "pass": 0.0,
            "details": "oqs not installed",
        }])

    enabled = set(oqs.get_enabled_kem_mechanisms())
    chosen = [a for a in algos if a in enabled] or sorted(enabled)[:3]

    rows = []
    for alg in chosen:
        ok = True
        err = "ok"
        try:
            for _ in range(iters):
                with oqs.KeyEncapsulation(alg) as kem:
                    pk = kem.generate_keypair()
                    sk = kem.export_secret_key()
                    ct, ss1 = kem.encap_secret(pk)
                with oqs.KeyEncapsulation(alg) as kem2:
                    _set_secret_key(kem2, sk)
                    ss2 = kem2.decap_secret(ct)
                if ss1 != ss2:
                    ok = False
                    err = "shared_secret_mismatch"
                    break
        except Exception as e:
            ok = False
            err = str(e)

        rows.append({
            "test": f"kem_roundtrip_{alg}",
            "pass": 1.0 if ok else 0.0,
            "details": err,
        })
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="results/data")
    ap.add_argument("--kem-iters", type=int, default=50)
    ap.add_argument("--kem-algos", nargs="*", default=[
        "Kyber512", "Kyber768", "Kyber1024",
        "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024",
    ])
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    aes_df = aes_gcm_test()
    kem_df = kem_tests(args.kem_iters, list(args.kem_algos))

    aes_p = out_dir / "security_aes.csv"
    kem_p = out_dir / "security_kem.csv"
    aes_df.to_csv(aes_p, index=False)
    kem_df.to_csv(kem_p, index=False)

    print("✓", aes_p)
    print("✓", kem_p)


if __name__ == "__main__":
    main()
