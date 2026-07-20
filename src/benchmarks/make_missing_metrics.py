#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bz2
import gzip
import io
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    import brotli
except Exception:
    brotli = None

try:
    import lz4.frame as lz4f
except Exception:
    lz4f = None

try:
    import zstandard as zstd
except Exception:
    zstd = None

try:
    import oqs
    OQS_OK = True
except Exception:
    OQS_OK = False

try:
    from PIL import Image
except Exception:
    Image = None

try:
    from skimage.metrics import structural_similarity as ssim
except Exception:
    ssim = None


IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
BIN_EXT = {".bin", ".dat", ".raw", ".pdf"}  # adapt if needed

def now() -> float:
    return time.perf_counter()

def read_bytes(p: Path, cap: int = 0) -> bytes:
    # cap>0 reads only the leading `cap` bytes — keeps compression of very large
    # incompressible files (e.g. 300 MB MP4) tractable; throughput is per-byte.
    if cap and cap > 0:
        with p.open("rb") as f:
            return f.read(cap)
    return p.read_bytes()

def is_image(p: Path) -> bool:
    return p.suffix.lower() in IMG_EXT

def list_files(data_dir: Path) -> List[Path]:
    return [p for p in data_dir.rglob("*") if p.is_file()]

def ensure_dirs():
    Path("results/data").mkdir(parents=True, exist_ok=True)

# ------------------ Lossless compressors ------------------

def comp_gzip(b: bytes) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb") as f:
        f.write(b)
    return out.getvalue()

def decomp_gzip(b: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(b), mode="rb") as f:
        return f.read()

def comp_bz2(b: bytes) -> bytes:
    return bz2.compress(b, compresslevel=9)

def decomp_bz2(b: bytes) -> bytes:
    return bz2.decompress(b)

def comp_brotli(b: bytes) -> bytes:
    if brotli is None:
        raise RuntimeError("brotli not installed")
    return brotli.compress(b, quality=11)

def decomp_brotli(b: bytes) -> bytes:
    if brotli is None:
        raise RuntimeError("brotli not installed")
    return brotli.decompress(b)

def comp_lz4(b: bytes) -> bytes:
    if lz4f is None:
        raise RuntimeError("lz4 not installed")
    return lz4f.compress(b)

def decomp_lz4(b: bytes) -> bytes:
    if lz4f is None:
        raise RuntimeError("lz4 not installed")
    return lz4f.decompress(b)

def comp_zstd(b: bytes) -> bytes:
    if zstd is None:
        raise RuntimeError("zstandard not installed")
    c = zstd.ZstdCompressor(level=10)
    return c.compress(b)

def decomp_zstd(b: bytes) -> bytes:
    if zstd is None:
        raise RuntimeError("zstandard not installed")
    d = zstd.ZstdDecompressor()
    return d.decompress(b)

COMPRESSORS = {
    "gzip": (comp_gzip, decomp_gzip),
    "bz2": (comp_bz2, decomp_bz2),
}
# optional
if brotli is not None:
    COMPRESSORS["brotli"] = (comp_brotli, decomp_brotli)
if lz4f is not None:
    COMPRESSORS["lz4"] = (comp_lz4, decomp_lz4)
if zstd is not None:
    COMPRESSORS["zstd"] = (comp_zstd, decomp_zstd)

# ------------------ Image metrics ------------------

def to_chw_float(img: Image.Image, size: int = 32) -> np.ndarray:
    img = img.convert("RGB").resize((size, size))
    x = np.asarray(img).astype(np.float32) / 255.0
    # HWC -> CHW
    return np.transpose(x, (2, 0, 1))

def psnr(mse: float, maxv: float = 1.0) -> float:
    if mse <= 1e-12:
        return 99.0
    return float(10.0 * np.log10((maxv * maxv) / mse))

def img_metrics(x: np.ndarray, xh: np.ndarray) -> Dict[str, float]:
    mse_v = float(np.mean((x - xh) ** 2))
    if ssim is None:
        return {"mse": mse_v, "psnr": psnr(mse_v), "ssim": float("nan")}
    ss = 0.0
    for c in range(3):
        ss += ssim(x[c], xh[c], data_range=1.0)
    return {"mse": mse_v, "psnr": psnr(mse_v), "ssim": float(ss / 3.0)}

# ------------------ Crypto primitives ------------------

def aes_gcm_encrypt(plaintext: bytes) -> Tuple[bytes, int]:
    key = AESGCM.generate_key(bit_length=256)
    aes = AESGCM(key)
    nonce = os.urandom(12)
    aad = b"hybrid-secure-bigdata"
    ct = aes.encrypt(nonce, plaintext, aad)
    # overhead: nonce + tag included in ct already? cryptography includes tag in ct.
    # We'll count nonce+aad length as metadata; tag is inside ct length.
    overhead_bytes = len(nonce) + len(aad)
    return ct, overhead_bytes

def aes_gcm_decrypt(ciphertext: bytes, plaintext_len_hint: int, key: bytes, nonce: bytes, aad: bytes) -> bytes:
    aes = AESGCM(key)
    return aes.decrypt(nonce, ciphertext, aad)

def kem_key_exchange(alg: str = "ML-KEM-1024") -> Tuple[int, int]:
    """
    Returns: (kem_ct_bytes, kem_pk_bytes) – for overhead accounting
    """
    if not OQS_OK:
        raise RuntimeError("oqs/liboqs-python not installed")
    if alg not in oqs.get_enabled_kem_mechanisms():
        raise RuntimeError(f"KEM {alg} not enabled; available: {oqs.get_enabled_kem_mechanisms()}")
    with oqs.KeyEncapsulation(alg) as kem:
        pk = kem.generate_keypair()
        ct, ss1 = kem.encap_secret(pk)
        # New object with same secret key: NOTE: some oqs versions cannot import secret key.
        # We'll use the same kem instance to decap (supported).
        ss2 = kem.decap_secret(ct)
        if ss1 != ss2:
            raise RuntimeError("KEM shared secret mismatch")
        return len(ct), len(pk)

# ------------------ Bench generation ------------------

@dataclass
class BenchCfg:
    data_dir: Path
    max_files: int = 200
    image_size: int = 32
    kem_alg: str = "ML-KEM-1024"
    max_bytes_per_file: int = 0

def make_compression_ratios(cfg: BenchCfg, files: List[Path]) -> pd.DataFrame:
    rows = []
    for p in files[: cfg.max_files]:
        b = read_bytes(p, cfg.max_bytes_per_file)
        n_in = len(b)
        for algo, (comp, decomp) in COMPRESSORS.items():
            try:
                t0 = now()
                cb = comp(b)
                t1 = now()
                rb = decomp(cb)
                t2 = now()
                ok = (rb == b)
                n_out = len(cb)
                ratio = (n_in / max(n_out, 1))
                pct = (1.0 - (n_out / max(n_in, 1))) * 100.0
                rows.append({
                    "path": str(p),
                    "kind": "image" if is_image(p) else "binary",
                    "algorithm": algo,
                    "input_bytes": n_in,
                    "compressed_bytes": n_out,
                    "compression_ratio": float(ratio),
                    "compression_percent": float(pct),
                    "compress_ms": (t1 - t0) * 1000.0,
                    "decompress_ms": (t2 - t1) * 1000.0,
                    "lossless_ok": int(ok),
                })
            except Exception as e:
                rows.append({
                    "path": str(p),
                    "kind": "image" if is_image(p) else "binary",
                    "algorithm": algo,
                    "input_bytes": n_in,
                    "compressed_bytes": np.nan,
                    "compression_ratio": np.nan,
                    "compression_percent": np.nan,
                    "compress_ms": np.nan,
                    "decompress_ms": np.nan,
                    "lossless_ok": 0,
                    "error": str(e),
                })
    return pd.DataFrame(rows)

def make_quality_images(cfg: BenchCfg, files: List[Path]) -> pd.DataFrame:
    if Image is None:
        raise RuntimeError("Pillow not installed; cannot compute image metrics.")
    img_files = [p for p in files if is_image(p)][: cfg.max_files]
    rows = []
    for p in img_files:
        try:
            img = Image.open(p)
            x = to_chw_float(img, size=cfg.image_size)

            # Lossless compressors: reconstruct bytes -> decode again -> same pixels (for PNG/BMP) not guaranteed for JPG.
            # For honesty: we measure quality after roundtrip bytes and decode.
            raw_bytes = read_bytes(p)
            for algo, (comp, decomp) in COMPRESSORS.items():
                try:
                    cb = comp(raw_bytes)
                    rb = decomp(cb)
                    img2 = Image.open(io.BytesIO(rb))
                    xh = to_chw_float(img2, size=cfg.image_size)
                    met = img_metrics(x, xh)
                    rows.append({"path": str(p), "algorithm": algo, **met})
                except Exception as e:
                    rows.append({"path": str(p), "algorithm": algo, "mse": np.nan, "psnr": np.nan, "ssim": np.nan, "error": str(e)})
        except Exception as e:
            rows.append({"path": str(p), "algorithm": "ALL", "mse": np.nan, "psnr": np.nan, "ssim": np.nan, "error": str(e)})
    return pd.DataFrame(rows)

def make_pipeline_throughput_and_latency(cfg: BenchCfg, files: List[Path]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Pipelines A/B/C/D (micro-macro over real files):
      A: Compress(zstd) + AES + KEM
      B: Raw + AES + KEM
      C: Raw + AES only
      D: Compress(gzip) + AES + KEM
    Notes:
      - We use zstd/gzip as compression stage here because your project does not yet provide a stable VAE codec end-to-end.
      - Still REAL DATA ONLY, no synthetic.
    """
    rows_thr = []
    rows_lat = []

    # pre-check KEM once
    kem_ct_bytes = kem_pk_bytes = 0
    if OQS_OK:
        kem_ct_bytes, kem_pk_bytes = kem_key_exchange(cfg.kem_alg)

    pipelines = {
        "A": "zstd + AES + KEM",
        "B": "raw + AES + KEM",
        "C": "raw + AES",
        "D": "gzip + AES + KEM",
    }

    for p in files[: cfg.max_files]:
        b = read_bytes(p, cfg.max_bytes_per_file)
        size_mb = len(b) / (1024.0 * 1024.0)

        for pid, desc in pipelines.items():
            t_comp = 0.0
            t_aes = 0.0
            t_kem = 0.0

            payload = b

            # compression
            if pid == "A" and "zstd" in COMPRESSORS:
                comp, _ = COMPRESSORS["zstd"]
                t0 = now()
                payload = comp(payload)
                t1 = now()
                t_comp = (t1 - t0) * 1000.0
            elif pid == "D":
                comp, _ = COMPRESSORS["gzip"]
                t0 = now()
                payload = comp(payload)
                t1 = now()
                t_comp = (t1 - t0) * 1000.0

            # KEM (fixed cost per message)
            if pid in {"A", "B", "D"}:
                if not OQS_OK:
                    # If oqs missing, we still record AES-only (but mark KEM missing)
                    t_kem = np.nan
                else:
                    t0 = now()
                    _ = kem_key_exchange(cfg.kem_alg)
                    t1 = now()
                    t_kem = (t1 - t0) * 1000.0

            # AES
            t0 = now()
            key = AESGCM.generate_key(bit_length=256)
            aes = AESGCM(key)
            nonce = os.urandom(12)
            aad = b"hybrid-secure-bigdata"
            ct = aes.encrypt(nonce, payload, aad)
            _ = aes.decrypt(nonce, ct, aad)
            t1 = now()
            t_aes = (t1 - t0) * 1000.0

            t_total = t_comp + t_aes + (0.0 if np.isnan(t_kem) else t_kem)
            # throughput based on original size (fair) / total time
            thr = (size_mb / max(t_total / 1000.0, 1e-9))

            rows_thr.append({
                "path": str(p),
                "pipeline": pid,
                "description": desc,
                "size_mb": size_mb,
                "throughput_mbps": float(thr),
            })

            rows_lat.append({
                "path": str(p),
                "pipeline": pid,
                "size_mb": size_mb,
                "t_comp_ms": float(t_comp),
                "t_aes_ms": float(t_aes),
                "t_kem_ms": float(t_kem),
                "t_total_ms": float(t_total),
            })

    return pd.DataFrame(rows_thr), pd.DataFrame(rows_lat)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/user_data")
    ap.add_argument("--max-files", type=int, default=200)
    ap.add_argument("--image-size", type=int, default=32)
    ap.add_argument("--kem-alg", default="ML-KEM-1024")
    ap.add_argument("--max-bytes-per-file", type=int, default=0, help="0=full file; >0 caps bytes read per file")
    args = ap.parse_args()

    cfg = BenchCfg(data_dir=Path(args.data_dir), max_files=args.max_files, image_size=args.image_size, kem_alg=args.kem_alg, max_bytes_per_file=args.max_bytes_per_file)
    ensure_dirs()

    files = list_files(cfg.data_dir)
    if not files:
        raise SystemExit(f"No files found in {cfg.data_dir}")

    # 1) compression ratios
    df_rat = make_compression_ratios(cfg, files)
    out1 = Path("results/data/metrics_compression_ratios.csv")
    df_rat.to_csv(out1, index=False)
    print("OK:", out1)

    # 2) quality (images)
    df_q = make_quality_images(cfg, files)
    out2 = Path("results/data/metrics_compression_quality.csv")
    df_q.to_csv(out2, index=False)
    print("OK:", out2)

    # 3) pipelines throughput + 4) latency breakdown
    df_thr, df_lat = make_pipeline_throughput_and_latency(cfg, files)
    out3 = Path("results/data/metrics_pipeline_throughput.csv")
    out4 = Path("results/data/metrics_latency_breakdown.csv")
    df_thr.to_csv(out3, index=False)
    df_lat.to_csv(out4, index=False)
    print("OK:", out3)
    print("OK:", out4)

if __name__ == "__main__":
    main()
