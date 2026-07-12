#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate image compression quality metrics (REAL DATA ONLY).

Outputs:
  results/data/metrics_compression_quality.csv

Metrics:
  - MSE
  - PSNR
  - SSIM

Supports VAE models saved as:
  - TorchScript
  - Full torch module
  - state_dict (weights only)

If no VAE model can be loaded, falls back to an identity baseline
(transparent, honest, clearly marked).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Optional heavy deps
try:
    import torch
except Exception:
    torch = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    from skimage.metrics import structural_similarity as ssim
except Exception:
    ssim = None


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def list_images(root: Path) -> List[Path]:
    return [p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in IMG_EXT]


def to_chw_float(img: Image.Image, size: int) -> np.ndarray:
    img = img.convert("RGB").resize((size, size))
    arr = np.asarray(img).astype(np.float32) / 255.0
    return np.transpose(arr, (2, 0, 1))


def psnr(mse: float, maxv: float = 1.0) -> float:
    if mse <= 1e-12:
        return 99.0
    return float(10.0 * np.log10((maxv ** 2) / mse))


def image_metrics(x: np.ndarray, xh: np.ndarray) -> Dict[str, float]:
    mse_v = float(np.mean((x - xh) ** 2))
    if ssim is None:
        return {
            "mse": mse_v,
            "psnr": psnr(mse_v),
            "ssim": float("nan"),
        }

    s = 0.0
    for c in range(3):
        s += ssim(x[c], xh[c], data_range=1.0)
    return {
        "mse": mse_v,
        "psnr": psnr(mse_v),
        "ssim": float(s / 3.0),
    }


# ---------------------------------------------------------------------
# VAE loading (robust)
# ---------------------------------------------------------------------

def find_vae_model(models_dir: Path) -> Optional[Path]:
    if not models_dir.exists():
        return None

    preferred = ["vae_best.pt", "vae_custom.pt", "vae.pt"]
    for name in preferred:
        p = models_dir / name
        if p.exists():
            return p

    pts = sorted(models_dir.glob("*.pt"))
    return pts[0] if pts else None


def try_load_vae(model_path: Path):
    """
    Returns a callable f(x) -> x_recon
    where x is a torch tensor (N,3,H,W) in [0,1].
    """
    if torch is None:
        raise RuntimeError("PyTorch not available")

    # --- 1) TorchScript
    try:
        m = torch.jit.load(str(model_path), map_location="cpu")
        m.eval()

        def _f(x):
            with torch.no_grad():
                out = m(x)
                return out[0] if isinstance(out, (tuple, list)) else out

        return _f
    except Exception:
        pass

    # --- 2) Full module
    obj = torch.load(str(model_path), map_location="cpu")
    if hasattr(obj, "eval") and callable(getattr(obj, "__call__", None)):
        obj.eval()

        def _f(x):
            with torch.no_grad():
                out = obj(x)
                return out[0] if isinstance(out, (tuple, list)) else out

        return _f

    # --- 3) state_dict only
    if isinstance(obj, dict):
        state_dict = obj.get("state_dict", obj)

        try:
            from src.models.vae_model import VAE
        except Exception as e:
            raise RuntimeError(
                "State_dict found but could not import src.models.vae_model.VAE: "
                f"{e}"
            )

        # Infer latent dim if possible (fallback = 128)
        latent_dim = 128
        for k, v in state_dict.items():
            if "fc_mu" in k and hasattr(v, "shape") and len(v.shape) == 2:
                latent_dim = int(v.shape[0])
                break

        model = VAE(latent_dim=latent_dim)
        model.load_state_dict(state_dict, strict=False)
        model.eval()

        def _f(x):
            with torch.no_grad():
                out = model(x)
                return out[0] if isinstance(out, (tuple, list)) else out

        return _f

    raise RuntimeError("Unsupported model format")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/user_data")
    ap.add_argument("--out", default="results/data/metrics_compression_quality.csv")
    ap.add_argument("--models-dir", default="results/models")
    ap.add_argument("--image-size", type=int, default=32)
    ap.add_argument("--max-images", type=int, default=200)
    args = ap.parse_args()

    if Image is None:
        raise SystemExit("ERROR: Pillow not installed")

    data_dir = Path(args.data_dir)
    images = list_images(data_dir)

    if not images:
        raise SystemExit(f"ERROR: no images found in {data_dir}")

    images = images[: args.max_images]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    model_path = find_vae_model(Path(args.models_dir))
    vae_fn = None
    load_error = None

    if model_path is not None:
        try:
            vae_fn = try_load_vae(model_path)
        except Exception as e:
            load_error = str(e)

    rows = []

    if vae_fn is not None:
        print(f"Using VAE model: {model_path}")
        for p in images:
            try:
                img = Image.open(p)
                x = to_chw_float(img, args.image_size)
                xt = torch.from_numpy(x).unsqueeze(0)
                with torch.no_grad():
                    xh = vae_fn(xt).clamp(0.0, 1.0).squeeze(0).cpu().numpy()
                met = image_metrics(x, xh)
                rows.append({
                    "path": str(p),
                    "algorithm": "vae",
                    **met,
                })
            except Exception as e:
                rows.append({
                    "path": str(p),
                    "algorithm": "vae",
                    "mse": np.nan,
                    "psnr": np.nan,
                    "ssim": np.nan,
                    "error": str(e),
                })
    else:
        print("WARNING: No usable VAE model found")
        if load_error:
            print("  Load error:", load_error)
        print("  Falling back to identity baseline")

        for p in images:
            img = Image.open(p)
            x = to_chw_float(img, args.image_size)
            met = image_metrics(x, x)
            rows.append({
                "path": str(p),
                "algorithm": "baseline_identity",
                **met,
            })

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)

    print(f"✓ Wrote {out_path}")
    print(f"  Images processed: {len(df)}")


if __name__ == "__main__":
    main()
