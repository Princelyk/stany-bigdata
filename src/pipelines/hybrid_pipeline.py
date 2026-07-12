#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipelines hybrides de compression + chiffrement
4 pipelines: A (VAE+AES+KEM), B (AES+KEM), C (AES), D (Compresseur+AES+KEM)
"""

import time
from typing import Tuple, Dict, Any
import torch
import numpy as np

from src.models.vae_model import VAE
from src.crypto.aes_gcm import AESGCMCipher
from src.crypto.ml_kem import MLKEMCipher
from src.compression.classic_compressors import ClassicCompressor


class HybridPipeline:
    """
    Pipeline hybride configurable
    """
    
    def __init__(
        self,
        pipeline_type: str = 'A',
        vae_model: VAE = None,
        compressor_algo: str = None
    ):
        """
        Args:
            pipeline_type: 'A', 'B', 'C', 'D'
            vae_model: Modèle VAE pré-entraîné (pour pipeline A)
            compressor_algo: Algorithme de compression (pour pipeline D)
        """
        self.pipeline_type = pipeline_type
        self.vae_model = vae_model
        self.compressor_algo = compressor_algo
        
        # Initialisation crypto
        self.aes_cipher = AESGCMCipher()
        self.kem_cipher = MLKEMCipher(security_level=1024)
        
        # Génération clés KEM
        if pipeline_type in ['A', 'B', 'D']:
            self.kem_public_key, self.kem_secret_key, _ = self.kem_cipher.generate_keypair()
    
    def encrypt(self, data: bytes) -> Tuple[Dict[str, Any], Dict]:
        """
        Chiffre les données selon le pipeline configuré
        
        Returns:
            (encrypted_package, metadata)
        """
        metadata = {
            'pipeline': self.pipeline_type,
            'size_original_bytes': len(data)
        }
        
        start_total = time.perf_counter()
        
        # === ÉTAPE 1: Compression (si applicable) ===
        if self.pipeline_type == 'A':
            # VAE compression
            if self.vae_model is None:
                raise ValueError("VAE model requis pour pipeline A")
            
            start_compress = time.perf_counter()
            
            # Conversion bytes → tensor
            data_array = np.frombuffer(data, dtype=np.uint8).astype(np.float32) / 255.0
            # Padding si nécessaire
            input_dim = self.vae_model.input_dim
            if len(data_array) < input_dim:
                data_array = np.pad(data_array, (0, input_dim - len(data_array)))
            elif len(data_array) > input_dim:
                data_array = data_array[:input_dim]
            
            data_tensor = torch.from_numpy(data_array).unsqueeze(0)
            
            # Compression VAE
            latent = self.vae_model.compress(data_tensor)
            compressed_data = latent.cpu().numpy().tobytes()
            
            metadata['t_compress_ms'] = (time.perf_counter() - start_compress) * 1000
            metadata['size_compressed_bytes'] = len(compressed_data)
            metadata['compression_ratio'] = len(data) / len(compressed_data)
            
            data_to_encrypt = compressed_data
        
        elif self.pipeline_type == 'D':
            # Compresseur classique
            if self.compressor_algo is None:
                raise ValueError("Compressor algo requis pour pipeline D")
            
            start_compress = time.perf_counter()
            
            compressor = ClassicCompressor(algorithm=self.compressor_algo)
            compressed_data, comp_meta = compressor.compress(data)
            
            metadata['t_compress_ms'] = comp_meta['compression_time_ms']
            metadata['size_compressed_bytes'] = len(compressed_data)
            metadata['compression_ratio'] = comp_meta['compression_ratio']
            metadata['compressor_algo'] = self.compressor_algo
            
            data_to_encrypt = compressed_data
        
        else:
            # Pas de compression (pipelines B et C)
            metadata['t_compress_ms'] = 0
            metadata['size_compressed_bytes'] = len(data)
            metadata['compression_ratio'] = 1.0
            data_to_encrypt = data
        
        # === ÉTAPE 2: Chiffrement AES-GCM ===
        start_aes = time.perf_counter()
        ciphertext, iv, aes_meta = self.aes_cipher.encrypt(data_to_encrypt)
        metadata['t_aes_encrypt_ms'] = (time.perf_counter() - start_aes) * 1000
        metadata['aes_overhead_bytes'] = aes_meta['overhead_bytes']
        
        # === ÉTAPE 3: Encapsulation KEM (si applicable) ===
        if self.pipeline_type in ['A', 'B', 'D']:
            start_kem = time.perf_counter()
            
            # Encapsulation de la clé AES
            kem_ciphertext, shared_secret, kem_meta = self.kem_cipher.encapsulate()
            
            metadata['t_kem_encaps_ms'] = (time.perf_counter() - start_kem) * 1000
            metadata['kem_ciphertext_bytes'] = len(kem_ciphertext)
            
            encrypted_package = {
                'ciphertext': ciphertext,
                'iv': iv,
                'kem_ciphertext': kem_ciphertext,
                'aes_key': self.aes_cipher.get_key()
            }
        else:
            # Pipeline C: AES seul
            metadata['t_kem_encaps_ms'] = 0
            encrypted_package = {
                'ciphertext': ciphertext,
                'iv': iv,
                'aes_key': self.aes_cipher.get_key()
            }
        
        metadata['t_total_ms'] = (time.perf_counter() - start_total) * 1000
        metadata['size_encrypted_bytes'] = len(ciphertext)
        
        return encrypted_package, metadata
    
    def decrypt(self, encrypted_package: Dict[str, Any]) -> Tuple[bytes, Dict]:
        """
        Déchiffre et décompresse les données
        
        Returns:
            (original_data, metadata)
        """
        metadata = {'pipeline': self.pipeline_type}
        start_total = time.perf_counter()
        
        # === ÉTAPE 1: Décapsulation KEM (si applicable) ===
        if self.pipeline_type in ['A', 'B', 'D']:
            start_kem = time.perf_counter()
            kem_ciphertext = encrypted_package['kem_ciphertext']
            shared_secret, kem_meta = self.kem_cipher.decapsulate(kem_ciphertext)
            metadata['t_kem_decaps_ms'] = (time.perf_counter() - start_kem) * 1000
        else:
            metadata['t_kem_decaps_ms'] = 0
        
        # === ÉTAPE 2: Déchiffrement AES ===
        start_aes = time.perf_counter()
        ciphertext = encrypted_package['ciphertext']
        iv = encrypted_package['iv']
        decrypted_data, aes_meta = self.aes_cipher.decrypt(ciphertext, iv)
        metadata['t_aes_decrypt_ms'] = (time.perf_counter() - start_aes) * 1000
        
        # === ÉTAPE 3: Décompression (si applicable) ===
        if self.pipeline_type == 'A':
            start_decompress = time.perf_counter()
            
            # Reconstruction VAE
            latent_array = np.frombuffer(decrypted_data, dtype=np.float32)
            latent_tensor = torch.from_numpy(latent_array).reshape(1, -1)
            reconstructed = self.vae_model.decompress(latent_tensor)
            
            # Conversion tensor → bytes
            reconstructed_array = (reconstructed.cpu().numpy() * 255).astype(np.uint8)
            original_data = reconstructed_array.tobytes()
            
            metadata['t_decompress_ms'] = (time.perf_counter() - start_decompress) * 1000
        
        elif self.pipeline_type == 'D':
            start_decompress = time.perf_counter()
            
            compressor = ClassicCompressor(algorithm=self.compressor_algo)
            original_data, decomp_meta = compressor.decompress(decrypted_data)
            
            metadata['t_decompress_ms'] = decomp_meta['decompression_time_ms']
        
        else:
            metadata['t_decompress_ms'] = 0
            original_data = decrypted_data
        
        metadata['t_total_ms'] = (time.perf_counter() - start_total) * 1000
        
        return original_data, metadata


def test_pipeline(pipeline_type: str = 'A', data_size_kb: int = 100):
    """
    Test d'un pipeline
    """
    import os
    
    print(f"\n{'='*70}")
    print(f"Test Pipeline {pipeline_type}")
    print('='*70)
    
    # Données de test
    test_data = os.urandom(data_size_kb * 1024)
    print(f"Taille données: {len(test_data) / 1024:.2f} KB")
    
    # Configuration
    if pipeline_type == 'A':
        vae = VAE(input_dim=1024, latent_dim=64)
        pipeline = HybridPipeline('A', vae_model=vae)
    elif pipeline_type == 'D':
        pipeline = HybridPipeline('D', compressor_algo='zstd')
    else:
        pipeline = HybridPipeline(pipeline_type)
    
    # Chiffrement
    encrypted_pkg, enc_meta = pipeline.encrypt(test_data)
    
    print(f"\nChiffrement:")
    for key, value in enc_meta.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
    
    # Déchiffrement
    decrypted_data, dec_meta = pipeline.decrypt(encrypted_pkg)
    
    print(f"\nDéchiffrement:")
    for key, value in dec_meta.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
    
    # Vérification (approximative pour VAE)
    if pipeline_type in ['B', 'C', 'D']:
        assert decrypted_data == test_data, "Erreur: données différentes!"
        print("\n✓ Vérification: données identiques")
    else:
        print("\n⚠ VAE: reconstruction approximative")


if __name__ == "__main__":
    # Test de tous les pipelines
    test_pipeline('B', 100)  # Sans compression
    test_pipeline('C', 100)  # AES seul
    test_pipeline('D', 100)  # Compresseur classique
