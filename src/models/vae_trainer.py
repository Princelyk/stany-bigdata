import argparse
import csv
import os
import time
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from PIL import Image

import torch
from torch.utils.data import Dataset, DataLoader, random_split
from torchvision import transforms
from tqdm import tqdm

import matplotlib.pyplot as plt

from src.models.vae_model import VAE


IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _is_image(path: str) -> bool:
    return os.path.splitext(path.lower())[1] in IMG_EXT


def psnr_from_mse(mse: float, maxv: float = 1.0) -> float:
    if mse <= 1e-12:
        return 99.0
    return float(10.0 * np.log10((maxv * maxv) / mse))


@dataclass
class TrainConfig:
    data_dir: str
    out_dir: str
    epochs: int
    batch_size: int
    lr: float
    latent_dim: int
    beta: float
    image_size: int
    val_split: float
    max_images: int
    device: str
    num_workers: int
    seed: int
    beta_warmup_epochs: int = 0  # linearly anneal beta from 0→beta over this many epochs


class ImageFolderDataset(Dataset):
    def __init__(self, paths: List[str], image_size: int = 32):
        self.paths = paths
        self.tfm = transforms.Compose(
            [
                transforms.Resize((image_size, image_size)),
                transforms.ToTensor(),
            ]
        )

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, str]:
        p = self.paths[idx]
        img = Image.open(p).convert("RGB")
        x = self.tfm(img)
        return x, p


def discover_images(data_dir: str) -> List[str]:
    paths: List[str] = []
    for root, _, files in os.walk(data_dir):
        for fn in files:
            p = os.path.join(root, fn)
            if _is_image(p):
                paths.append(p)
    paths.sort()
    return paths


@torch.no_grad()
def eval_epoch(model: VAE, dl: DataLoader, device: torch.device) -> Tuple[float, float]:
    model.eval()
    losses = []
    mses = []
    for x, _ in dl:
        x = x.to(device, non_blocking=True)
        xh, mu, logvar = model(x)
        loss, _, _ = model.loss(x, xh, mu, logvar)
        losses.append(float(loss.detach().cpu()))
        mse = torch.mean((xh - x) ** 2).detach().cpu().item()
        mses.append(float(mse))
    val_loss = float(np.mean(losses)) if losses else 0.0
    val_mse = float(np.mean(mses)) if mses else 0.0
    return val_loss, psnr_from_mse(val_mse)


def plot_history(rows: List[dict], out_dir: str) -> None:
    fig_dir = os.path.join(out_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    epochs = [r["epoch"] for r in rows]
    train_loss = [r["train_loss"] for r in rows]
    val_loss = [r["val_loss"] for r in rows]
    val_psnr = [r["val_psnr"] for r in rows]
    train_recon = [r["train_recon"] for r in rows]
    train_kl = [r["train_kl"] for r in rows]

    fig = plt.figure(figsize=(12, 6))
    ax1 = plt.gca()
    ax1.plot(epochs, train_loss, marker="o", label="train_loss")
    ax1.plot(epochs, val_loss, marker="o", label="val_loss")
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Loss (recon + β·KL)")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(epochs, val_psnr, marker="s", linestyle="--", label="val_PSNR(dB)")
    ax2.set_ylabel("Val PSNR (dB)")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best")

    fig.suptitle("Figure: VAE training history (loss + PSNR)", fontsize=14)

    for ext in ("png", "pdf", "svg"):
        fig.savefig(os.path.join(fig_dir, f"figure_vae_training_history.{ext}"), bbox_inches="tight", dpi=300)
    plt.close(fig)

    fig = plt.figure(figsize=(12, 6))
    ax = plt.gca()
    ax.plot(epochs, train_recon, marker="o", label="train_recon(MSE)")
    ax.plot(epochs, train_kl, marker="o", label="train_KL")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Value")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.suptitle("Figure: VAE loss components (recon + KL)", fontsize=14)
    for ext in ("png", "pdf", "svg"):
        fig.savefig(os.path.join(fig_dir, f"figure_vae_loss_components.{ext}"), bbox_inches="tight", dpi=300)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description="Train VAE on REAL images (no synthetic fallback).")
    ap.add_argument("--data-dir", default="data/user_data")
    ap.add_argument("--out", default="results")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--latent-dim", type=int, default=128)
    ap.add_argument("--beta", type=float, default=1.0)
    ap.add_argument("--image-size", type=int, default=32)
    ap.add_argument("--val-split", type=float, default=0.1)
    ap.add_argument("--max-images", type=int, default=0)
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    ap.add_argument("--num-workers", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--beta-warmup-epochs", type=int, default=5,
                    help="Linearly anneal beta 0→target over this many epochs (prevents KL collapse)")
    args = ap.parse_args()

    cfg = TrainConfig(
        data_dir=args.data_dir,
        out_dir=args.out,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        latent_dim=args.latent_dim,
        beta=args.beta,
        image_size=args.image_size,
        val_split=args.val_split,
        max_images=args.max_images,
        device=args.device,
        num_workers=args.num_workers,
        seed=args.seed,
        beta_warmup_epochs=args.beta_warmup_epochs,
    )

    os.makedirs(cfg.out_dir, exist_ok=True)
    os.makedirs(os.path.join(cfg.out_dir, "models"), exist_ok=True)
    os.makedirs(os.path.join(cfg.out_dir, "figures"), exist_ok=True)

    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    device = torch.device("cuda" if (cfg.device == "cuda" and torch.cuda.is_available()) else "cpu")
    pin = bool(device.type == "cuda")

    print(f"[VAE] data_dir={cfg.data_dir} | device={device} | epochs={cfg.epochs} | bs={cfg.batch_size}")

    imgs = discover_images(cfg.data_dir)
    if cfg.max_images and cfg.max_images > 0:
        imgs = imgs[: cfg.max_images]

    if len(imgs) < 4:
        raise SystemExit(f"ERROR: Not enough images found in {cfg.data_dir}. Found {len(imgs)} images. Need >= 4.")

    ds = ImageFolderDataset(imgs, image_size=cfg.image_size)
    n = len(ds)
    n_val = max(1, int(cfg.val_split * n))
    n_tr = n - n_val
    gen = torch.Generator().manual_seed(cfg.seed)
    ds_tr, ds_val = random_split(ds, [n_tr, n_val], generator=gen)

    dl_tr = DataLoader(ds_tr, batch_size=cfg.batch_size, shuffle=True, num_workers=cfg.num_workers, pin_memory=pin)
    dl_val = DataLoader(ds_val, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers, pin_memory=pin)

    model = VAE(latent_dim=cfg.latent_dim, beta=cfg.beta, image_size=cfg.image_size).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr)

    history_rows: List[dict] = []
    best_val = float("inf")

    for ep in range(1, cfg.epochs + 1):
        t0 = time.perf_counter()
        model.train()

        # KL warm-up: linearly anneal beta from 0 → cfg.beta over beta_warmup_epochs
        if cfg.beta_warmup_epochs > 0:
            beta_eff = cfg.beta * min(1.0, ep / cfg.beta_warmup_epochs)
            model.beta = beta_eff

        losses = []
        recons = []
        kls = []

        pbar = tqdm(dl_tr, desc=f"epoch {ep}/{cfg.epochs} β={model.beta:.3f}", ncols=90)
        for x, _ in pbar:
            x = x.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            xh, mu, logvar = model(x)
            loss, recon, kl = model.loss(x, xh, mu, logvar)
            loss.backward()
            opt.step()

            losses.append(float(loss.detach().cpu()))
            recons.append(float(recon.detach().cpu()))
            kls.append(float(kl.detach().cpu()))
            pbar.set_postfix(loss=float(loss.detach().cpu()), recon=float(recon.detach().cpu()), kl=float(kl.detach().cpu()))

        train_loss = float(np.mean(losses)) if losses else 0.0
        train_recon = float(np.mean(recons)) if recons else 0.0
        train_kl = float(np.mean(kls)) if kls else 0.0

        val_loss, val_psnr = eval_epoch(model, dl_val, device)
        t1 = time.perf_counter()

        row = {
            "epoch": ep,
            "train_loss": train_loss,
            "train_recon": train_recon,
            "train_kl": train_kl,
            "val_loss": val_loss,
            "val_psnr": float(val_psnr),
            "seconds": float(t1 - t0),
            "n_train": int(n_tr),
            "n_val": int(n_val),
            "latent_dim": int(cfg.latent_dim),
            "beta": float(cfg.beta),
            "lr": float(cfg.lr),
            "image_size": int(cfg.image_size),
        }
        history_rows.append(row)

        print(f"[epoch {ep:02d}] train_loss={train_loss:.6f} val_loss={val_loss:.6f} val_psnr={val_psnr:.2f}dB time={t1-t0:.1f}s")

        last_path = os.path.join(cfg.out_dir, "models", "vae_last.pt")
        torch.save({"model": model.state_dict(), "config": row}, last_path)

        if val_loss < best_val:
            best_val = val_loss
            best_path = os.path.join(cfg.out_dir, "models", "vae_best.pt")
            torch.save({"model": model.state_dict(), "config": row}, best_path)

    out_csv = os.path.join(cfg.out_dir, "metrics_vae_history.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(history_rows[0].keys()))
        w.writeheader()
        w.writerows(history_rows)
    print("OK:", out_csv)

    plot_history(history_rows, cfg.out_dir)
    print("OK: results/figures/figure_vae_training_history.(png|pdf|svg)")


if __name__ == "__main__":
    main()
