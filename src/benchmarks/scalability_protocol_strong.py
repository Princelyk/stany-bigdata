#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def list_files(data_dir: Path, max_files: int = 0) -> List[Path]:
    files: List[Path] = [p for p in data_dir.rglob("*") if p.is_file()]
    files.sort(key=lambda p: str(p))
    if max_files > 0:
        return files[:max_files]
    return files


def read_payload(path: Path, max_bytes_per_file: int = 0) -> bytes:
    with path.open("rb") as f:
        if max_bytes_per_file > 0:
            return f.read(max_bytes_per_file)
        return f.read()


def aes_roundtrip(payload: bytes) -> int:
    key = os.urandom(32)
    nonce = os.urandom(12)
    aad = b"strong-scaling-aes"
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, payload, aad)
    pt = aes.decrypt(nonce, ct, aad)
    if pt != payload:
        raise RuntimeError("AES roundtrip mismatch")
    return len(payload)


def run_once(payloads: List[bytes], threads: int) -> tuple[float, int]:
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        sizes = list(pool.map(aes_roundtrip, payloads))
    wall_s = time.perf_counter() - t0
    return wall_s, int(sum(sizes))


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="python -m src.benchmarks.scalability_protocol_strong",
        description="Strong-scaling protocol for AES-GCM worker threads.",
    )
    ap.add_argument("--dataset-id", required=True, help="Dataset label, e.g. D2")
    ap.add_argument("--data-dir", required=True, help="Dataset root directory")
    ap.add_argument("--out", default="results/data/protocol", help="Output root")
    ap.add_argument("--run-id", default="", help="Optional run id")
    ap.add_argument(
        "--threads",
        default="1,2,4,8,16",
        help="Comma-separated worker counts, e.g. 1,2,4,8",
    )
    ap.add_argument("--repetitions", type=int, default=3, help="Repetitions per thread count")
    ap.add_argument("--max-files", type=int, default=0, help="Optional cap on file count")
    ap.add_argument(
        "--max-bytes-per-file",
        type=int,
        default=0,
        help="0 means full file; >0 reads only leading bytes",
    )
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        raise SystemExit(f"ERROR: data directory not found: {data_dir}")

    run_id = args.run_id.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(args.out)
    strong_dir = out_root / "strong" / args.dataset_id
    strong_dir.mkdir(parents=True, exist_ok=True)

    files = list_files(data_dir, max_files=args.max_files)
    if not files:
        raise SystemExit(f"ERROR: no files found in {data_dir}")

    payloads = [read_payload(p, max_bytes_per_file=args.max_bytes_per_file) for p in files]
    if any(len(p) == 0 for p in payloads):
        payloads = [p for p in payloads if len(p) > 0]
    if not payloads:
        raise SystemExit("ERROR: all sampled payloads are empty")

    thread_values = [int(x.strip()) for x in args.threads.split(",") if x.strip()]
    thread_values = sorted(set(t for t in thread_values if t > 0))
    if 1 not in thread_values:
        thread_values = [1] + thread_values

    rows = []
    baseline_throughput = None

    for threads in thread_values:
        run_throughputs = []
        for rep in range(args.repetitions):
            wall_s, total_bytes = run_once(payloads, threads=threads)
            throughput_mb_s = (total_bytes / (1024 ** 2)) / max(wall_s, 1e-9)
            run_throughputs.append(throughput_mb_s)
            rows.append(
                {
                    "dataset_id": args.dataset_id,
                    "run_id": run_id,
                    "threads": threads,
                    "rep": rep,
                    "n_files": len(payloads),
                    "bytes_processed": total_bytes,
                    "wall_s": wall_s,
                    "throughput_mb_s": throughput_mb_s,
                }
            )

        mean_t = float(np.mean(run_throughputs))
        if threads == 1:
            baseline_throughput = mean_t

        for row in rows:
            if row["threads"] == threads and row["run_id"] == run_id:
                if baseline_throughput is None:
                    row["parallel_efficiency"] = float("nan")
                else:
                    row["parallel_efficiency"] = row["throughput_mb_s"] / (
                        threads * max(baseline_throughput, 1e-12)
                    )

    df = pd.DataFrame(rows)
    out_csv = strong_dir / f"run_{run_id}_strong_scaling.csv"
    df.to_csv(out_csv, index=False)

    agg = (
        df.groupby("threads", as_index=False)
        .agg(
            throughput_mb_s_mean=("throughput_mb_s", "mean"),
            throughput_mb_s_std=("throughput_mb_s", "std"),
            parallel_efficiency_mean=("parallel_efficiency", "mean"),
            parallel_efficiency_std=("parallel_efficiency", "std"),
        )
        .sort_values("threads")
    )

    out_agg_csv = strong_dir / f"run_{run_id}_strong_scaling_agg.csv"
    agg.to_csv(out_agg_csv, index=False)

    all_csv = out_root / "strong_scaling_runs.csv"
    if all_csv.exists():
        prev = pd.read_csv(all_csv)
        merged = pd.concat([prev, df], ignore_index=True)
    else:
        merged = df
    merged.to_csv(all_csv, index=False)

    print(f"OK: wrote {out_csv}")
    print(f"OK: wrote {out_agg_csv}")
    print(f"OK: updated {all_csv}")


if __name__ == "__main__":
    main()
