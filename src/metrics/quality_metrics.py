#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Métriques de qualité pour évaluation VAE
PSNR, SSIM, MSE
"""

import numpy as np
from skimage.metrics import structural_similarity as ssim
from skimage.metrics import peak_signal_noise_ratio as psnr


def calculate_mse(original: np.ndarray, reconstructed: np.ndarray) -> float:
    """
    Mean Squared Error
    """
    return np.mean((original - reconstructed) ** 2)


def calculate_psnr(original: np.ndarray, reconstructed: np.ndarray) -> float:
    """
    Peak Signal-to-Noise Ratio (dB)
    """
    return psnr(original, reconstructed, data_range=original.max() - original.min())


def calculate_ssim(original: np.ndarray, reconstructed: np.ndarray) -> float:
    """
    Structural Similarity Index
    """
    if original.ndim == 3:  # Images couleur
        return ssim(original, reconstructed, channel_axis=2, data_range=original.max() - original.min())
    else:  # Images grayscale
        return ssim(original, reconstructed, data_range=original.max() - original.min())


def evaluate_reconstruction(original: np.ndarray, reconstructed: np.ndarray) -> dict:
    """
    Évaluation complète de la qualité de reconstruction
    """
    metrics = {
        'mse': calculate_mse(original, reconstructed),
        'psnr_db': calculate_psnr(original, reconstructed),
        'ssim': calculate_ssim(original, reconstructed)
    }
    
    return metrics
