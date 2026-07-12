import torch
import torch.nn as nn
import torch.nn.functional as F


class VAE(nn.Module):
    """
    Convolutional VAE for 32x32 RGB images (stable on CPU).

    Encoder: 3x32x32 -> 256x4x4 -> latent (mu, logvar)
    Decoder: latent -> 256x4x4 -> 3x32x32
    """

    def __init__(self, latent_dim: int = 128, beta: float = 1.0, in_channels: int = 3, image_size: int = 32):
        super().__init__()
        if image_size != 32:
            raise ValueError("This VAE implementation expects image_size=32.")
        self.latent_dim = int(latent_dim)
        self.beta = float(beta)

        self.enc = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=4, stride=2, padding=1),   # 32x16x16
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 64, kernel_size=4, stride=2, padding=1),            # 64x8x8
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 128, kernel_size=4, stride=2, padding=1),           # 128x4x4
            nn.ReLU(inplace=True),
            nn.Conv2d(128, 256, kernel_size=3, stride=1, padding=1),          # 256x4x4
            nn.ReLU(inplace=True),
        )

        self.enc_flat = 256 * 4 * 4
        self.fc_mu = nn.Linear(self.enc_flat, self.latent_dim)
        self.fc_logvar = nn.Linear(self.enc_flat, self.latent_dim)

        self.fc_dec = nn.Linear(self.latent_dim, self.enc_flat)
        self.dec = nn.Sequential(
            nn.ConvTranspose2d(256, 128, kernel_size=4, stride=2, padding=1),  # 128x8x8
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(128, 64, kernel_size=4, stride=2, padding=1),   # 64x16x16
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(64, 32, kernel_size=4, stride=2, padding=1),    # 32x32x32
            nn.ReLU(inplace=True),
            nn.Conv2d(32, in_channels, kernel_size=3, stride=1, padding=1),
            nn.Sigmoid(),
        )

    def encode(self, x: torch.Tensor):
        h = self.enc(x).view(x.size(0), -1)
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        return mu, logvar

    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor):
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def decode(self, z: torch.Tensor):
        h = self.fc_dec(z).view(z.size(0), 256, 4, 4)
        return self.dec(h)

    def forward(self, x: torch.Tensor):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        x_hat = self.decode(z)
        return x_hat, mu, logvar

    def loss(self, x: torch.Tensor, x_hat: torch.Tensor, mu: torch.Tensor, logvar: torch.Tensor):
        recon = F.mse_loss(x_hat, x, reduction="mean")
        kl = -0.5 * torch.mean(1.0 + logvar - mu.pow(2) - logvar.exp())
        total = recon + self.beta * kl
        return total, recon, kl
