#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Micro-benchmark ML-KEM / Kyber (SUPERCOP-style, liboqs-python safe)

Generates: results/data/kem_samples_us.csv
For Figure 7 (latency boxplots)
"""

import os
import time
import csv
import argparse
import numpy as np
import oqs


def bench_one(algorithm: str, iterations: int):
    keygen_us = []
    encaps_us = []
    decaps_us = []

    for _ in range(iterations):
        with oqs.KeyEncapsulation(algorithm) as kem:
            # KeyGen
            t0 = time.perf_counter()
            pk = kem.generate_keypair()
            t1 = time.perf_counter()

            # Encapsulation
            ct, ss1 = kem.encap_secret(pk)
            t2 = time.perf_counter()

            # Decapsulation (same object, correct usage)
            ss2 = kem.decap_secret(ct)
            t3 = time.perf_counter()

            # Correctness check (valid here)
            if ss1 != ss2:
                raise RuntimeError(f"KEM failure for {algorithm}")

        keygen_us.append((t1 - t0) * 1e6)
        encaps_us.append((t2 - t1) * 1e6)
        decaps_us.append((t3 - t2) * 1e6)

    return keygen_us, encaps_us, decaps_us


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=300)
    ap.add_argument("--out", default="results/data/kem_samples_us.csv")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    algorithms = ["Kyber512", "Kyber768", "Kyber1024"]
    rows = []

    for alg in algorithms:
        print(f"[KEM] benchmarking {alg}")
        kg, en, de = bench_one(alg, args.iterations)
        for i in range(len(kg)):
            rows.append({
                "algorithm": alg,
                "keygen_us": kg[i],
                "encaps_us": en[i],
                "decaps_us": de[i],
            })

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"✓ KEM samples saved → {args.out}")


if __name__ == "__main__":
    main()

