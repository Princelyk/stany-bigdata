#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import psutil
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    import oqs
except Exception as exc:  # pragma: no cover - environment dependent
    raise SystemExit(
        "ERROR: oqs import failed. Install/use the configured environment first."
    ) from exc


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXT = {".txt", ".log", ".csv", ".json", ".xml", ".yaml", ".yml"}
BIN_EXT = {".bin", ".dat", ".raw", ".zip", ".gz", ".7z", ".tar", ".pdf", ".mp4"}


def list_files(data_dir: Path, max_files: int = 0) -> List[Path]:
    files: List[Path] = [p for p in data_dir.rglob("*") if p.is_file()]
    files.sort(key=lambda p: str(p))
    if max_files > 0:
        return files[:max_files]
    return files


def file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return "images"
    if ext in TEXT_EXT:
        return "text"
    if ext in BIN_EXT:
        return "binaries"
    return "other"


def bootstrap_ci(values: np.ndarray, n_boot: int = 10_000, alpha: float = 0.05) -> Tuple[float, float]:
    if values.size == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(42)
    means = np.empty(n_boot, dtype=np.float64)
    n = values.size
    for i in range(n_boot):
        sample = values[rng.integers(0, n, size=n)]
        means[i] = np.mean(sample)
    lo = float(np.percentile(means, 100 * (alpha / 2.0)))
    hi = float(np.percentile(means, 100 * (1.0 - alpha / 2.0)))
    return lo, hi


def iqr(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.percentile(values, 75) - np.percentile(values, 25))


def read_bytes(path: Path, max_bytes_per_file: int = 0) -> bytes:
    with path.open("rb") as f:
        if max_bytes_per_file > 0:
            return f.read(max_bytes_per_file)
        return f.read()


def run_one_file(path: Path, kem_alg: str, max_bytes_per_file: int, encrypted_out_dir: Path | None) -> Dict:
    result: Dict[str, float | int | str | bool] = {
        "path": str(path),
        "kind": file_kind(path),
        "size_bytes": int(path.stat().st_size),
    }

    io_start = time.perf_counter_ns()
    payload = read_bytes(path, max_bytes_per_file=max_bytes_per_file)
    io_read_ms = (time.perf_counter_ns() - io_start) / 1e6

    kem_start = time.perf_counter_ns()
    kem = oqs.KeyEncapsulation(kem_alg)
    pk = kem.generate_keypair()
    kem_ct, ss1 = kem.encap_secret(pk)
    ss2 = kem.decap_secret(kem_ct)
    kem_ms = (time.perf_counter_ns() - kem_start) / 1e6
    kem_ok = ss1 == ss2

    aes_start = time.perf_counter_ns()
    key = os.urandom(32)
    nonce = os.urandom(12)
    aad = b"scalability-protocol"
    aes = AESGCM(key)
    ciphertext = aes.encrypt(nonce, payload, aad)
    plaintext = aes.decrypt(nonce, ciphertext, aad)
    aes_ms = (time.perf_counter_ns() - aes_start) / 1e6
    aes_ok = plaintext == payload

    io_write_ms = 0.0
    if encrypted_out_dir is not None:
        encrypted_out_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{path.name}.enc"
        write_start = time.perf_counter_ns()
        (encrypted_out_dir / out_name).write_bytes(ciphertext)
        io_write_ms = (time.perf_counter_ns() - write_start) / 1e6

    total_ms = io_read_ms + kem_ms + aes_ms + io_write_ms

    result.update(
        {
            "payload_bytes_processed": int(len(payload)),
            "l_io_read_ms": float(io_read_ms),
            "l_io_write_ms": float(io_write_ms),
            "l_kem_ms": float(kem_ms),
            "l_aes_ms": float(aes_ms),
            "l_total_ms": float(total_ms),
            "kem_ok": bool(kem_ok),
            "aes_ok": bool(aes_ok),
            "kem_ciphertext_bytes": int(len(kem_ct)),
            "aes_ciphertext_bytes": int(len(ciphertext)),
        }
    )
    return result


def summarize_by_size_bucket(df: pd.DataFrame, n_buckets: int = 5) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    bins = pd.qcut(df["payload_bytes_processed"], q=min(n_buckets, len(df)), duplicates="drop")
    out = (
        df.assign(size_bucket=bins.astype(str))
        .groupby("size_bucket", as_index=False)
        .agg(
            n_files=("path", "count"),
            payload_mb=("payload_bytes_processed", lambda s: float(np.sum(s) / (1024 ** 2))),
            l_io_read_median_ms=("l_io_read_ms", "median"),
            l_io_read_iqr_ms=("l_io_read_ms", lambda s: iqr(s.to_numpy())),
            l_kem_median_ms=("l_kem_ms", "median"),
            l_kem_iqr_ms=("l_kem_ms", lambda s: iqr(s.to_numpy())),
            l_aes_median_ms=("l_aes_ms", "median"),
            l_aes_iqr_ms=("l_aes_ms", lambda s: iqr(s.to_numpy())),
            l_total_median_ms=("l_total_ms", "median"),
            l_total_iqr_ms=("l_total_ms", lambda s: iqr(s.to_numpy())),
        )
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="python -m src.benchmarks.scalability_protocol_run",
        description="Run one weak-scaling protocol replicate for a dataset.",
    )
    ap.add_argument("--dataset-id", required=True, help="Dataset label, e.g. D1, D2, D3")
    ap.add_argument("--data-dir", required=True, help="Dataset root directory")
    ap.add_argument("--out", default="results/data/protocol", help="Output root")
    ap.add_argument("--run-id", default="", help="Optional run id; default timestamp")
    ap.add_argument("--max-files", type=int, default=0, help="Optional cap for dry-runs")
    ap.add_argument(
        "--max-bytes-per-file",
        type=int,
        default=0,
        help="0 means full file; >0 reads only leading bytes per file",
    )
    ap.add_argument("--kem-alg", default="ML-KEM-1024", help="KEM mechanism name from oqs")
    ap.add_argument("--seed", type=int, default=42, help="Sampling seed")
    ap.add_argument(
        "--correctness-samples",
        type=int,
        default=100,
        help="Number of random rows to include in correctness summary",
    )
    ap.add_argument(
        "--write-encrypted",
        action="store_true",
        help="If set, writes encrypted payloads to disk and measures write latency",
    )
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        raise SystemExit(f"ERROR: data directory not found: {data_dir}")

    run_id = args.run_id.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    random.seed(args.seed)
    np.random.seed(args.seed)

    out_root = Path(args.out)
    weak_dir = out_root / "weak" / args.dataset_id
    weak_dir.mkdir(parents=True, exist_ok=True)
    encrypted_out_dir = weak_dir / f"encrypted_{run_id}" if args.write_encrypted else None

    files = list_files(data_dir, max_files=args.max_files)
    if not files:
        raise SystemExit(f"ERROR: no files found in {data_dir}")

    proc = psutil.Process(os.getpid())
    n_cores = psutil.cpu_count(logical=True) or 1
    cpu_t0 = proc.cpu_times()
    rss_peak_mb = proc.memory_info().rss / (1024 ** 2)

    t0 = time.perf_counter()
    rows: List[Dict] = []
    for idx, path in enumerate(files, start=1):
        row = run_one_file(
            path=path,
            kem_alg=args.kem_alg,
            max_bytes_per_file=args.max_bytes_per_file,
            encrypted_out_dir=encrypted_out_dir,
        )
        row["dataset_id"] = args.dataset_id
        row["run_id"] = run_id
        row["file_index"] = idx
        rows.append(row)
        rss_peak_mb = max(rss_peak_mb, proc.memory_info().rss / (1024 ** 2))

    wall_s = time.perf_counter() - t0
    cpu_t1 = proc.cpu_times()
    cpu_seconds = (cpu_t1.user + cpu_t1.system) - (cpu_t0.user + cpu_t0.system)
    u_cpu = (cpu_seconds / max(wall_s * n_cores, 1e-9)) * 100.0

    df = pd.DataFrame(rows)
    per_file_csv = weak_dir / f"run_{run_id}_per_file.csv"
    df.to_csv(per_file_csv, index=False)

    per_bucket = summarize_by_size_bucket(df)
    bucket_csv = weak_dir / f"run_{run_id}_size_buckets.csv"
    per_bucket.to_csv(bucket_csv, index=False)

    payload_bytes = int(df["payload_bytes_processed"].sum())
    total_bytes = int(df["size_bytes"].sum())
    t_bytes_mb_s = (payload_bytes / (1024 ** 2)) / max(wall_s, 1e-9)
    t_files_s = len(df) / max(wall_s, 1e-9)

    ci_lo, ci_hi = bootstrap_ci(df["l_total_ms"].to_numpy())

    sample_n = min(args.correctness_samples, len(df))
    sampled = df.sample(n=sample_n, random_state=args.seed) if sample_n > 0 else df.iloc[0:0]

    summary = {
        "dataset_id": args.dataset_id,
        "run_id": run_id,
        "data_dir": str(data_dir),
        "n_files": int(len(df)),
        "bytes_total_on_disk": total_bytes,
        "bytes_processed": payload_bytes,
        "processed_gb": payload_bytes / (1024 ** 3),
        "wall_s": wall_s,
        "t_bytes_mb_s": t_bytes_mb_s,
        "t_files_s": t_files_s,
        "latency_p50_ms": float(np.percentile(df["l_total_ms"], 50)),
        "latency_p95_ms": float(np.percentile(df["l_total_ms"], 95)),
        "latency_p99_ms": float(np.percentile(df["l_total_ms"], 99)),
        "latency_mean_ms": float(df["l_total_ms"].mean()),
        "latency_mean_ci95_lo_ms": ci_lo,
        "latency_mean_ci95_hi_ms": ci_hi,
        "cpu_utilization_percent": u_cpu,
        "rss_peak_mb": float(rss_peak_mb),
        "kem_failures": int((~df["kem_ok"]).sum()),
        "aes_failures": int((~df["aes_ok"]).sum()),
        "correctness_sample_n": int(sample_n),
        "correctness_sample_kem_failures": int((~sampled["kem_ok"]).sum()) if sample_n > 0 else 0,
        "correctness_sample_aes_failures": int((~sampled["aes_ok"]).sum()) if sample_n > 0 else 0,
        "max_bytes_per_file": int(args.max_bytes_per_file),
        "kem_alg": args.kem_alg,
    }

    for kind, group in df.groupby("kind"):
        summary[f"kind_{kind}_files"] = int(len(group))
        summary[f"kind_{kind}_bytes"] = int(group["payload_bytes_processed"].sum())
        summary[f"kind_{kind}_throughput_mb_s"] = (
            (group["payload_bytes_processed"].sum() / (1024 ** 2))
            / max(group["l_total_ms"].sum() / 1000.0, 1e-9)
        )

    summary_json = weak_dir / f"run_{run_id}_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    summary_csv = out_root / "weak_scaling_runs.csv"
    one = pd.DataFrame([summary])
    if summary_csv.exists():
        prev = pd.read_csv(summary_csv)
        all_df = pd.concat([prev, one], ignore_index=True)
    else:
        all_df = one
    all_df.to_csv(summary_csv, index=False)

    print(f"OK: wrote {per_file_csv}")
    print(f"OK: wrote {bucket_csv}")
    print(f"OK: wrote {summary_json}")
    print(f"OK: updated {summary_csv}")


if __name__ == "__main__":
    main()
