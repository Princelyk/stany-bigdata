#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import psutil


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXT  = {".txt", ".log", ".csv", ".json", ".xml", ".yaml", ".yml"}
BIN_EXT   = {".bin", ".dat", ".raw", ".zip", ".gz", ".7z", ".tar", ".pdf"}


def list_files(data_dir: Path) -> List[Path]:
    files = []
    for p in data_dir.rglob("*"):
        if p.is_file():
            files.append(p)
    # stable order for reproducibility
    files.sort(key=lambda x: str(x))
    return files


def file_kind(p: Path) -> str:
    ext = p.suffix.lower()
    if ext in IMAGE_EXT:
        return "images"
    if ext in TEXT_EXT:
        return "text"
    if ext in BIN_EXT:
        return "binaries"
    return "other"


def total_size_bytes(files: List[Path]) -> int:
    s = 0
    for f in files:
        try:
            s += f.stat().st_size
        except Exception:
            pass
    return int(s)


def pick_prefix_for_target(files: List[Path], target_bytes: int) -> List[Path]:
    """Return a prefix list of files whose cumulative size >= target_bytes."""
    out = []
    s = 0
    for f in files:
        try:
            sz = f.stat().st_size
        except Exception:
            continue
        out.append(f)
        s += sz
        if s >= target_bytes:
            break
    return out


def run_io_workload(files: List[Path], max_read_mb_per_file: int = 64) -> int:
    """
    Workload volontairement simple + stable:
    - lit chaque fichier (capé à max_read_mb_per_file) en chunks
    - cumule bytes lus
    """
    total = 0
    cap = max_read_mb_per_file * 1024 * 1024
    buf = 1024 * 1024  # 1MB chunks

    for f in files:
        try:
            with open(f, "rb") as fp:
                read = 0
                while True:
                    chunk = fp.read(buf)
                    if not chunk:
                        break
                    total += len(chunk)
                    read += len(chunk)
                    if read >= cap:
                        break
        except Exception:
            continue
    return total


def measure_once(files: List[Path], proc: psutil.Process, max_read_mb_per_file: int) -> Dict:
    # cpu_percent is meaningful after a small interval
    proc.cpu_percent(interval=None)

    rss_before = proc.memory_info().rss / (1024 * 1024)
    t0 = time.perf_counter()
    bytes_read = run_io_workload(files, max_read_mb_per_file=max_read_mb_per_file)
    wall = time.perf_counter() - t0
    cpu = proc.cpu_percent(interval=0.1)
    rss_after = proc.memory_info().rss / (1024 * 1024)

    mb = bytes_read / (1024 * 1024)
    throughput = mb / max(wall, 1e-9)

    return {
        "bytes_read": int(bytes_read),
        "size_mb": float(mb),
        "wall_s": float(wall),
        "latency_ms": float(wall * 1000.0),
        "throughput_mbps": float(throughput),
        "cpu_mean_percent": float(cpu),
        "rss_mean_mb": float(rss_after),
        "rss_before_mb": float(rss_before),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, help="Dataset directory (real data)")
    ap.add_argument("--out", default="results", help="Output root (default: results)")
    ap.add_argument("--repetitions", type=int, default=1, help="Repetitions per size point")
    ap.add_argument("--points", type=int, default=7, help="Number of size points across dataset (default 7)")
    ap.add_argument("--max-read-mb-per-file", type=int, default=64, help="Read cap per file (MB) to keep runtime bounded")
    ap.add_argument("--max-files", type=int, default=0, help="Optional cap on number of files (0 = no cap)")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_root = Path(args.out)
    out_data = out_root / "data"
    out_figs = out_root / "figures"
    out_data.mkdir(parents=True, exist_ok=True)
    out_figs.mkdir(parents=True, exist_ok=True)

    files = list_files(data_dir)
    if args.max_files and args.max_files > 0:
        files = files[: args.max_files]

    if not files:
        raise SystemExit(f"ERROR: no files found in {data_dir}")

    total_b = total_size_bytes(files)
    total_gb = total_b / (1024**3)

    # points as fractions of total size (real)
    points = max(3, int(args.points))
    fracs = np.linspace(0.15, 1.0, points)  # start at 15% to avoid tiny noise points
    targets = [int(total_b * f) for f in fracs]

    proc = psutil.Process(os.getpid())

    rows = []
    for i, target in enumerate(targets, start=1):
        subset = pick_prefix_for_target(files, target)
        subset_b = total_size_bytes(subset)
        subset_gb = subset_b / (1024**3)

        for r in range(args.repetitions):
            m = measure_once(subset, proc, max_read_mb_per_file=args.max_read_mb_per_file)
            rows.append({
                "rep": int(r),
                "point": int(i),
                "n_files": int(len(subset)),
                "size_bytes": int(subset_b),
                "size_gb": float(subset_gb),
                "total_dataset_gb": float(total_gb),
                **m,
            })
            print(f"[scalability] point {i}/{len(targets)} rep {r+1}/{args.repetitions} size={subset_gb:.2f}GB throughput={m['throughput_mbps']:.1f}MB/s")

    df = pd.DataFrame(rows)
    out_csv = out_data / "scalability.csv"
    df.to_csv(out_csv, index=False)
    print(f"OK: wrote {out_csv}")
    print("NEXT: python -u src/visualization/fig08_scalability.py --results results --data-dir <DATASET_DIR>")


if __name__ == "__main__":
    main()
