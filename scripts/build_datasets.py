#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_datasets.py — assemble the scalability datasets D2 / D3.

Motivation
----------
The scalability protocol (see Scalability_Protocol_JISA_extracted.txt) calls for
two large heterogeneous datasets in addition to the local D1:

    D2  ~60 GB   40% images / 30% logs / 20% network / 10% tabular
    D3  ~100 GB  60% high-entropy binary / 20% network / 15% logs / 5% tabular

You do NOT need to own that much local data. This script builds each dataset to
the target size + composition by:

  1. GENERATING the free parts locally — high-entropy blobs (os.urandom),
     synthetic-but-realistic logs / CSV telemetry, and noise JPEG images. These
     require no download and reproduce the file-size distribution the benchmark
     is sensitive to (per-file KEM cost dominates throughput).

  2. INGESTING real public datasets you have staged, if any. Point --stage-dir at
     a folder with per-category subdirs (images/ text/ csv/ binary/); the script
     copies those real files first and tops up with generated data to reach the
     target. Recommended public, redistributable sources:
        images  -> MS-COCO         https://cocodataset.org
        logs    -> Loghub-2.0      https://github.com/logpai/loghub
        network -> MAWI traces     https://mawi.wide.ad.jp/mawi/
        tabular -> MIMIC-III Demo  https://physionet.org/content/mimiciii-demo/
     For reproducibility you publish only the SHA-256 manifest + these URLs, not
     the raw data.

The file loader classifies by extension (src/data/real_data_loader.py):
    images  = .jpg .jpeg .png .webp .bmp .tif .tiff
    csv     = .csv
    text    = .txt .log .json .xml .yaml .yml
    binaries= everything else (.bin .mp4 .pcap ...)
This script emits extensions that land in the intended bucket.

Examples
--------
  # Full 60 GB D2 (generate everything locally):
  python -m scripts.build_datasets --dataset D2

  # 1% smoke build to test the pipeline end-to-end quickly:
  python -m scripts.build_datasets --dataset D3 --scale 0.01

  # Use real files where available, generate the rest:
  python -m scripts.build_datasets --dataset D2 --stage-dir data/staging/D2

After building, create the manifest the benchmarks read:
  python -m src.data.real_data_loader --create-manifest --data-dir data/user_data/D2
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import string
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

GB = 1024 ** 3
MB = 1024 ** 2
CHUNK = 8 * MB  # streaming write size


# --------------------------------------------------------------------------- #
# Component specification
# --------------------------------------------------------------------------- #
@dataclass
class Component:
    """One category of a dataset: how much, what kind, what file sizes."""
    name: str                 # logical name (also the stage-dir subfolder + output subdir)
    kind: str                 # generator key: highentropy | binary | image | log | csv
    target_gb: float          # size target at scale 1.0
    min_mb: float             # per-file size range (drawn log-uniform)
    max_mb: float
    ext: str                  # output extension (drives loader classification)


@dataclass
class DatasetSpec:
    dataset_id: str
    components: List[Component] = field(default_factory=list)

    @property
    def total_gb(self) -> float:
        return sum(c.target_gb for c in self.components)


# Compositions follow the protocol's concrete recommended mix.
SPECS = {
    "D2": DatasetSpec("D2", [
        Component("images",  "image",       24.0, 0.10, 2.0, ".jpg"),
        Component("logs",    "log",         18.0, 5.0, 60.0, ".log"),
        Component("network", "binary",      12.0, 20.0, 200.0, ".pcap"),
        Component("tabular", "csv",          6.0, 1.0, 20.0, ".csv"),
    ]),
    "D3": DatasetSpec("D3", [
        Component("highentropy", "highentropy", 40.0, 50.0, 500.0, ".bin"),
        Component("video",       "highentropy", 20.0, 40.0, 300.0, ".mp4"),
        Component("network",     "binary",      20.0, 20.0, 200.0, ".pcap"),
        Component("logs",        "log",         15.0, 5.0, 60.0, ".log"),
        Component("tabular",     "csv",          5.0, 1.0, 20.0, ".csv"),
    ]),
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def draw_size(rng: random.Random, min_mb: float, max_mb: float) -> int:
    """Log-uniform draw in [min_mb, max_mb], returned in bytes (>=1)."""
    import math
    lo, hi = math.log(max(min_mb, 1e-3)), math.log(max(max_mb, 1e-3))
    val_mb = math.exp(rng.uniform(lo, hi))
    return max(1, int(val_mb * MB))


def write_random_bytes(path: Path, n: int) -> None:
    """Stream n bytes of os.urandom (true high-entropy) into path."""
    remaining = n
    with path.open("wb") as f:
        while remaining > 0:
            b = os.urandom(min(CHUNK, remaining))
            f.write(b)
            remaining -= len(b)


# --------------------------------------------------------------------------- #
# Generators — each fills `out_dir` until `target_bytes` is reached.
# Returns (num_files, bytes_written).
# --------------------------------------------------------------------------- #
def gen_highentropy(out_dir: Path, target_bytes: int, comp: Component,
                    rng: random.Random, start_idx: int) -> tuple[int, int]:
    written, n = 0, 0
    while written < target_bytes:
        size = min(draw_size(rng, comp.min_mb, comp.max_mb), target_bytes - written)
        p = out_dir / f"{comp.name}_{start_idx + n:06d}{comp.ext}"
        write_random_bytes(p, size)
        written += size
        n += 1
    return n, written


# Already-compressed media / archives are also ~incompressible high-entropy,
# so the binary generator reuses the high-entropy writer.
gen_binary = gen_highentropy


def gen_log(out_dir: Path, target_bytes: int, comp: Component,
            rng: random.Random, start_idx: int) -> tuple[int, int]:
    levels = ["INFO", "WARN", "ERROR", "DEBUG", "TRACE"]
    comps = ["auth", "kernel", "sshd", "nginx", "kafka", "scheduler", "gc"]
    hosts = [f"node-{i:02d}" for i in range(64)]
    written, n = 0, 0
    while written < target_bytes:
        size = min(draw_size(rng, comp.min_mb, comp.max_mb), target_bytes - written)
        p = out_dir / f"{comp.name}_{start_idx + n:06d}{comp.ext}"
        with p.open("w", encoding="utf-8", newline="\n") as f:
            fw = 0
            ts = 1_700_000_000 + rng.randint(0, 10_000_000)
            while fw < size:
                ts += rng.randint(0, 5)
                msg = "".join(rng.choice(string.ascii_letters + " ") for _ in range(rng.randint(20, 80)))
                line = (f"{ts} {rng.choice(hosts)} {rng.choice(comps)}[{rng.randint(100,99999)}] "
                        f"{rng.choice(levels)} req={rng.randint(0, 1<<20):x} {msg}\n")
                f.write(line)
                fw += len(line)
        written += p.stat().st_size
        n += 1
    return n, written


def gen_csv(out_dir: Path, target_bytes: int, comp: Component,
            rng: random.Random, start_idx: int) -> tuple[int, int]:
    header = "ts,sensor_id,metric,value,unit,status,site\n"
    units = ["C", "kPa", "rpm", "V", "A", "pct"]
    stats = ["ok", "warn", "fault"]
    written, n = 0, 0
    while written < target_bytes:
        size = min(draw_size(rng, comp.min_mb, comp.max_mb), target_bytes - written)
        p = out_dir / f"{comp.name}_{start_idx + n:06d}{comp.ext}"
        with p.open("w", encoding="utf-8", newline="\n") as f:
            f.write(header)
            fw = len(header)
            ts = 1_700_000_000 + rng.randint(0, 10_000_000)
            while fw < size:
                ts += 1
                row = (f"{ts},{rng.randint(0,4096)},m{rng.randint(0,32)},"
                       f"{rng.uniform(-50,500):.4f},{rng.choice(units)},"
                       f"{rng.choice(stats)},site-{rng.randint(0,8)}\n")
                f.write(row)
                fw += len(row)
        written += p.stat().st_size
        n += 1
    return n, written


def gen_image(out_dir: Path, target_bytes: int, comp: Component,
              rng: random.Random, start_idx: int) -> tuple[int, int]:
    try:
        import numpy as np
        from PIL import Image
    except Exception as exc:  # pragma: no cover
        raise SystemExit("ERROR: image generation needs Pillow + numpy (in requirements.txt). "
                         f"{exc}")
    written, n, safety = 0, 0, 0
    while written < target_bytes:
        # Mix smooth gradient (compressible) with noise so JPEG size varies
        # realistically and the compression benchmark has non-trivial content.
        dim = rng.randint(384, 1600)
        yy, xx = np.mgrid[0:dim, 0:dim]
        base = ((xx * rng.uniform(0.1, 0.9) + yy * rng.uniform(0.1, 0.9)) % 256).astype("uint8")
        noise = np.random.randint(0, 60, size=(dim, dim), dtype="uint8")
        # uint8 arithmetic wraps mod 256 automatically (numpy), giving varied channels.
        arr = np.stack([base + noise,
                        base * np.uint8(2) + noise,
                        base // np.uint8(2) + noise], axis=-1).astype("uint8")
        p = out_dir / f"{comp.name}_{start_idx + n:06d}{comp.ext}"
        Image.fromarray(arr, "RGB").save(p, quality=rng.randint(70, 92))
        written += p.stat().st_size
        n += 1
        safety += 1
        if safety > 5_000_000:  # pathological guard
            break
    return n, written


GENERATORS: dict[str, Callable[..., tuple[int, int]]] = {
    "highentropy": gen_highentropy,
    "binary": gen_binary,
    "log": gen_log,
    "csv": gen_csv,
    "image": gen_image,
}


# --------------------------------------------------------------------------- #
# Ingest staged real files
# --------------------------------------------------------------------------- #
def ingest_staged(stage_sub: Path, out_dir: Path, target_bytes: int) -> tuple[int, int]:
    """Copy real files from stage_sub into out_dir up to target_bytes."""
    if not stage_sub.is_dir():
        return 0, 0
    files = sorted(p for p in stage_sub.rglob("*") if p.is_file())
    written, n = 0, 0
    for src in files:
        if written >= target_bytes:
            break
        sz = src.stat().st_size
        if sz == 0:
            continue
        shutil.copy2(src, out_dir / f"real_{n:06d}{src.suffix.lower()}")
        written += sz
        n += 1
    return n, written


# --------------------------------------------------------------------------- #
# Main build
# --------------------------------------------------------------------------- #
def build(spec: DatasetSpec, out_root: Path, scale: float, seed: int,
          stage_dir: Optional[Path], only: Optional[str]) -> None:
    rng = random.Random(seed)
    dataset_root = out_root / spec.dataset_id
    dataset_root.mkdir(parents=True, exist_ok=True)

    target_total = int(spec.total_gb * scale * GB)
    free = shutil.disk_usage(dataset_root).free
    print(f"\n=== Building {spec.dataset_id} ===")
    print(f"scale={scale}  target~{target_total/GB:.2f} GB  free disk={free/GB:.1f} GB  seed={seed}")
    if free < target_total * 1.05:
        print(f"WARNING: only {free/GB:.1f} GB free for a {target_total/GB:.1f} GB build. "
              f"Reduce --scale or free space.", file=sys.stderr)

    grand_files, grand_bytes = 0, 0
    for comp in spec.components:
        if only and comp.name != only:
            continue
        comp_target = int(comp.target_gb * scale * GB)
        out_dir = dataset_root / comp.name
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[{comp.name}] target {comp_target/GB:.2f} GB  "
              f"({comp.kind}, {comp.min_mb}-{comp.max_mb} MB/file, {comp.ext})")

        got_files, got_bytes = 0, 0
        # 1) real staged files first
        if stage_dir is not None:
            f_i, b_i = ingest_staged(stage_dir / comp.name, out_dir, comp_target)
            if f_i:
                print(f"    ingested {f_i} real files ({b_i/GB:.2f} GB) from stage dir")
            got_files, got_bytes = f_i, b_i
        # 2) generate the remainder
        remaining = comp_target - got_bytes
        if remaining > 0:
            gen = GENERATORS[comp.kind]
            f_g, b_g = gen(out_dir, remaining, comp, rng, got_files)
            got_files += f_g
            got_bytes += b_g
            print(f"    generated {f_g} files ({b_g/GB:.2f} GB)")

        print(f"    -> {comp.name}: {got_files} files, {got_bytes/GB:.2f} GB")
        grand_files += got_files
        grand_bytes += got_bytes

    print(f"\n=== {spec.dataset_id} done: {grand_files} files, {grand_bytes/GB:.2f} GB "
          f"at {dataset_root} ===")
    print(f"Next: python -m src.data.real_data_loader --create-manifest "
          f"--data-dir {dataset_root.as_posix()}")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="python -m scripts.build_datasets",
        description="Assemble scalability datasets D2/D3 (generate locally + ingest staged real data).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--dataset", required=True, choices=sorted(SPECS.keys()),
                    help="Which dataset to build.")
    ap.add_argument("--out-root", default="data/user_data",
                    help="Root under which <DATASET_ID>/ is created.")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="Fraction of the full target size (e.g. 0.01 for a smoke build).")
    ap.add_argument("--seed", type=int, default=1234, help="RNG seed for reproducibility.")
    ap.add_argument("--stage-dir", default=None,
                    help="Optional dir with per-category subfolders of real files to ingest first "
                         "(images/ logs/ network/ tabular/ ...).")
    ap.add_argument("--only", default=None,
                    help="Build only this component (by name), e.g. --only highentropy.")
    args = ap.parse_args()

    spec = SPECS[args.dataset]
    stage = Path(args.stage_dir) if args.stage_dir else None
    build(spec, Path(args.out_root), args.scale, args.seed, stage, args.only)


if __name__ == "__main__":
    main()
