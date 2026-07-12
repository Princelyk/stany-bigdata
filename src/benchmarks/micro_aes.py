#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Micro-benchmark AES-256-GCM
Produces metrics_micro_aes.csv for Figure 6
"""

import os
import time
import csv
import argparse
import secrets
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def benchmark_aes(payload_size: int, iterations: int):
    key = AESGCM.generate_key(bit_length=256)
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)
    aad = b"benchmark"

    enc_times = []
    dec_times = []

    for _ in range(iterations):
        data = secrets.token_bytes(payload_size)

        t0 = time.perf_counter()
        ct = aes.encrypt(nonce, data, aad)
        t1 = time.perf_counter()

        aes.decrypt(nonce, ct, aad)
        t2 = time.perf_counter()

        enc_times.append(t1 - t0)
        dec_times.append(t2 - t1)

    return {
        "payload_bytes": payload_size,
        "enc_MBps": (payload_size / 1e6) / np.mean(enc_times),
        "dec_MBps": (payload_size / 1e6) / np.mean(dec_times),
        "enc_p95_ms": np.percentile(enc_times, 95) * 1000,
        "dec_p95_ms": np.percentile(dec_times, 95) * 1000,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=1000)
    ap.add_argument("--out", default="results/data/metrics_micro_aes.csv")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    sizes = [1024, 4096, 16384, 65536, 262144, 1048576]
    rows = []

    for sz in sizes:
        print(f"[AES] benchmarking {sz} bytes")
        r = benchmark_aes(sz, args.iterations)
        rows.append(r)

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"✓ AES microbench saved → {args.out}")


if __name__ == "__main__":
    main()

