#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import io
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from PIL import Image

import zstandard as zstd
import lz4.frame
import brotli
import bz2
import gzip

import torch

# ---- VAE import (project-local) ----
from src.models.vae_model import VAE


IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def list_images(data_dir: Path) -> List[Path]:
    files = []
    for p in data_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            files.append(p)
    return files


def load_image_bytes(path: Path, image_size: int) -> bytes:
    """
    Convert image to RGB, resize to (image_size, image_size),
    and return RAW bytes (not PNG/JPEG compressed).
    This makes lossless compressors comparable and stable.
    """
    img = Image.open(path).convert("RGB")
    if image_size is not None:
        img = img.resize((image_size, image_size), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.uint8)  # H W 3
    return arr.tobytes()


def mbps(bytes_in: int, seconds: float) -> float:
    if seconds <= 1e-12:
        return 0.0
    return (bytes_in / (1024 * 1024)) / seconds


def compress_zstd(b: bytes, level: int = 3) -> bytes:
    c = zstd.ZstdCompressor(level=level)
    return c.compress(b)


def decompress_zstd(b: bytes) -> bytes:
    d = zstd.ZstdDecompressor()
    return d.decompress(b)


def compress_lz4(b: bytes) -> bytes:
    return lz4.frame.compress(b)


def decompress_lz4(b: bytes) -> bytes:
    return lz4.frame.decompress(b)


def compress_gzip(b: bytes, level: int = 6) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=level) as f:
        f.write(b)
    return out.getvalue()


def decompress_gzip(b: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(b), mode="rb") as f:
        return f.read()


def compress_bz2(b: bytes, level: int = 9) -> bytes:
    return bz2.compress(b, compresslevel=level)


def decompress_bz2(b: bytes) -> bytes:
    return bz2.decompress(b)


def compress_brotli(b: bytes, quality: int = 5) -> bytes:
    return brotli.compress(b, quality=quality)


def decompress_brotli(b: bytes) -> bytes:
    return brotli.decompress(b)


LOSSLESS_ALGOS = {
    "zstd": (compress_zstd, decompress_zstd),
    "lz4": (compress_lz4, decompress_lz4),
    "gzip": (compress_gzip, decompress_gzip),
    "bz2": (compress_bz2, decompress_bz2),
    "brotli": (compress_brotli, decompress_brotli),
}


def load_vae(vae_path: Path, device: torch.device, latent_dim: int, beta: float) -> VAE:
    """
    Loads either:
      - a full torch checkpoint dict
      - or a pure state_dict
    """
    m = VAE(latent_dim=latent_dim, beta=beta).to(device)
    ckpt = torch.load(str(vae_path), map_location=device)

    if isinstance(ckpt, dict) and "state_dict" in ckpt:
        sd = ckpt["state_dict"]
    elif isinstance(ckpt, dict) and "model_state" in ckpt:
        sd = ckpt["model_state"]
    elif isinstance(ckpt, dict) and any(k.startswith("encoder") or k.startswith("decoder") for k in ckpt.keys()):
        sd = ckpt
    else:
        # last try: assume direct state_dict
        sd = ckpt

    m.load_state_dict(sd, strict=False)
    m.eval()
    return m


@torch.no_grad()
def vae_latent_bytes(m: VAE, raw_rgb_bytes: bytes, image_size: int, device: torch.device) -> int:
    """
    Encode one image and estimate latent payload size (fp16).
    We use mu as latent representation.
    """
    # raw bytes -> tensor [1,3,H,W] float in [0,1]
    arr = np.frombuffer(raw_rgb_bytes, dtype=np.uint8).reshape((image_size, image_size, 3))
    x = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).float() / 255.0
    x = x.to(device)

    # Forward: VAE returns x_hat, mu, logvar
    xh, mu, logvar = m(x)

    # fp16 quant for payload estimate
    mu16 = mu.detach().cpu().numpy().astype(np.float16)
    payload = mu16.tobytes()
    # add tiny header for shape (simulate)
    header = 16
    return len(payload) + header


def bench_lossless_one(algo: str, raw: bytes) -> Tuple[int, float, float]:
    comp, decomp = LOSSLESS_ALGOS[algo]
    t0 = time.perf_counter()
    c = comp(raw)
    t1 = time.perf_counter()
    out = decomp(c)
    t2 = time.perf_counter()
    if out != raw:
        raise RuntimeError(f"{algo}: decompressed bytes mismatch (lossless integrity failed)")
    return len(c), (t1 - t0), (t2 - t1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/user_data")
    ap.add_argument("--out", default="results/data")
    ap.add_argument("--image-size", type=int, default=32)
    ap.add_argument("--max-images", type=int, default=200)
    ap.add_argument("--reps", type=int, default=1)

    # VAE options (only affects VAE row)
    ap.add_argument("--vae-model", default="results/models/vae_best.pt")
    ap.add_argument("--vae-latent-dim", type=int, default=128)
    ap.add_argument("--vae-beta", type=float, default=1.0)
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    imgs = list_images(data_dir)
    if not imgs:
        raise SystemExit(f"No images found in {data_dir} (needed for compression ratios incl. VAE).")

    imgs = imgs[: max(1, min(args.max_images, len(imgs)))]

    # Load image raw bytes once
    samples: List[Tuple[Path, bytes]] = []
    for p in imgs:
        try:
            b = load_image_bytes(p, args.image_size)
            samples.append((p, b))
        except Exception:
            continue
    if not samples:
        raise SystemExit("Could not load any images (decode/resize failed).")

    # Setup VAE (optional)
    device = torch.device("cuda" if args.device == "cuda" and torch.cuda.is_available() else "cpu")
    vae = None
    vae_path = Path(args.vae_model)
    if vae_path.exists():
        try:
            vae = load_vae(vae_path, device, args.vae_latent_dim, args.vae_beta)
        except Exception as e:
            print("NOTE: VAE model exists but failed to load -> VAE will be skipped.")
            print("      Load error:", str(e))

    rows = []

    # Lossless algos
    for algo in ["zstd", "lz4", "gzip", "bz2", "brotli"]:
        for (p, raw) in samples:
            for rep in range(args.reps):
                t0 = time.perf_counter()
                clen, t_comp, t_decomp = bench_lossless_one(algo, raw)
                t1 = time.perf_counter()

                ratio = len(raw) / max(clen, 1)
                rt_s = (t1 - t0)
                rows.append({
                    "file": str(p),
                    "algorithm": algo,
                    "raw_bytes": len(raw),
                    "compressed_bytes": clen,
                    "compression_ratio": float(ratio),
                    "throughput_MBps": float(mbps(len(raw), rt_s)),
                })

    # VAE (lossy) on images only
    if vae is not None:
        for (p, raw) in samples:
            for rep in range(args.reps):
                t0 = time.perf_counter()
                lat_bytes = vae_latent_bytes(vae, raw, args.image_size, device)
                t1 = time.perf_counter()

                ratio = len(raw) / max(lat_bytes, 1)
                rt_s = (t1 - t0)
                rows.append({
                    "file": str(p),
                    "algorithm": "vae",
                    "raw_bytes": len(raw),
                    "compressed_bytes": int(lat_bytes),
                    "compression_ratio": float(ratio),
                    "throughput_MBps": float(mbps(len(raw), rt_s)),
                })
    else:
        print("NOTE: VAE not included in ratios because model could not be loaded or not found.")

    detail = pd.DataFrame(rows)
    detail_path = out_dir / "compression_ratios_detail.csv"
    detail.to_csv(detail_path, index=False)
    print("OK:", detail_path)

    # Aggregate (median is Q1-friendly)
    agg = detail.groupby("algorithm").agg(
        count=("compression_ratio", "count"),
        compression_ratio_median=("compression_ratio", "median"),
        compression_ratio_mean=("compression_ratio", "mean"),
        compression_ratio_std=("compression_ratio", "std"),
        throughput_MBps_median=("throughput_MBps", "median"),
        throughput_MBps_mean=("throughput_MBps", "mean"),
        throughput_MBps_std=("throughput_MBps", "std"),
    ).reset_index()

    out_path = out_dir / "metrics_compression_ratios.csv"
    agg.to_csv(out_path, index=False)
    print("OK:", out_path)

    # quick sanity
    print("Algorithms in metrics:", agg["algorithm"].tolist())


if __name__ == "__main__":
    main()
