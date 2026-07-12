#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Implémentation AES-256-GCM conforme NIST
FIPS 197 (AES) + SP 800-38D (GCM)
"""

import os
import time
from typing import Tuple, Dict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend


class AESGCMCipher:
    """
    Chiffrement authentifié AES-256-GCM
    
    Conformité NIST:
    - FIPS 197: AES avec clé 256 bits
    - SP 800-38D: Mode GCM avec IV 96 bits, tag 128 bits
    
    Références:
    - https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.197.pdf
    - https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf
    """
    
    # Constantes NIST
    KEY_SIZE = 32      # 256 bits
    IV_SIZE = 12       # 96 bits (recommandation NIST)
    TAG_SIZE = 16      # 128 bits
    
    def __init__(self, key: bytes = None):
        """
        Initialise le chiffreur AES-GCM
        
        Args:
            key: Clé AES-256 (32 bytes). Si None, génère une nouvelle clé.
        """
        if key is None:
            self.key = AESGCM.generate_key(bit_length=256)
        else:
            if len(key) != self.KEY_SIZE:
                raise ValueError(f"La clé doit faire {self.KEY_SIZE} bytes (256 bits)")
            self.key = key
        
        self.cipher = AESGCM(self.key)
    
    def encrypt(self, plaintext: bytes, associated_data: bytes = None) -> Tuple[bytes, bytes, Dict]:
        """
        Chiffre des données avec AES-256-GCM
        
        Args:
            plaintext: Données à chiffrer
            associated_data: Données authentifiées mais non chiffrées (optionnel)
        
        Returns:
            (ciphertext, iv, metadata)
            - ciphertext: données chiffrées + tag d'authentification
            - iv: vecteur d'initialisation (96 bits)
            - metadata: dictionnaire avec métriques
        """
        # Génération IV aléatoire (NIST recommande 96 bits)
        iv = os.urandom(self.IV_SIZE)
        
        # Mesure de performance
        start_time = time.perf_counter()
        
        # Chiffrement + authentification
        ciphertext = self.cipher.encrypt(iv, plaintext, associated_data)
        
        elapsed = (time.perf_counter() - start_time) * 1000  # ms
        
        # Métriques
        metadata = {
            'algorithm': 'AES-256-GCM',
            'standard': 'NIST FIPS 197 + SP 800-38D',
            'key_size_bits': 256,
            'iv_size_bits': 96,
            'tag_size_bits': 128,
            'plaintext_size_bytes': len(plaintext),
            'ciphertext_size_bytes': len(ciphertext),
            'overhead_bytes': len(ciphertext) - len(plaintext),
            'encryption_time_ms': elapsed,
            'throughput_mbps': (len(plaintext) / (1024*1024)) / (elapsed / 1000) if elapsed > 0 else 0
        }
        
        return ciphertext, iv, metadata
    
    def decrypt(self, ciphertext: bytes, iv: bytes, associated_data: bytes = None) -> Tuple[bytes, Dict]:
        """
        Déchiffre et vérifie l'authenticité avec AES-256-GCM
        
        Args:
            ciphertext: Données chiffrées (inclut le tag)
            iv: Vecteur d'initialisation utilisé lors du chiffrement
            associated_data: Données authentifiées (doit correspondre au chiffrement)
        
        Returns:
            (plaintext, metadata)
        
        Raises:
            cryptography.exceptions.InvalidTag: Si l'authentification échoue
        """
        if len(iv) != self.IV_SIZE:
            raise ValueError(f"L'IV doit faire {self.IV_SIZE} bytes (96 bits)")
        
        start_time = time.perf_counter()
        
        # Déchiffrement + vérification du tag
        try:
            plaintext = self.cipher.decrypt(iv, ciphertext, associated_data)
            success = True
        except Exception as e:
            success = False
            plaintext = None
            raise e
        finally:
            elapsed = (time.perf_counter() - start_time) * 1000
        
        metadata = {
            'algorithm': 'AES-256-GCM',
            'ciphertext_size_bytes': len(ciphertext),
            'plaintext_size_bytes': len(plaintext) if plaintext else 0,
            'decryption_time_ms': elapsed,
            'authentication_success': success,
            'throughput_mbps': (len(plaintext) / (1024*1024)) / (elapsed / 1000) if elapsed > 0 and plaintext else 0
        }
        
        return plaintext, metadata
    
    def encrypt_large_data(self, data: bytes, chunk_size: int = 64*1024) -> Tuple[bytes, bytes, Dict]:
        """
        Chiffre de grandes quantités de données par chunks
        Optimisé pour minimiser la mémoire utilisée
        
        Args:
            data: Données à chiffrer
            chunk_size: Taille des chunks (défaut: 64 KB)
        
        Returns:
            (ciphertext, iv, metadata)
        """
        # Pour l'instant, on chiffre en une fois
        # Dans une version production, on pourrait streamer
        return self.encrypt(data)
    
    @staticmethod
    def generate_key() -> bytes:
        """
        Génère une clé AES-256 aléatoire cryptographiquement sécurisée
        """
        return AESGCM.generate_key(bit_length=256)
    
    def get_key(self) -> bytes:
        """
        Retourne la clé actuelle (à protéger!)
        """
        return self.key


def benchmark_aes_gcm(data_sizes_mb: list = [1, 10, 100]) -> Dict:
    """
    Benchmark AES-256-GCM sur différentes tailles de données
    """
    results = []
    
    cipher = AESGCMCipher()
    
    for size_mb in data_sizes_mb:
        # Génération de données aléatoires
        data = os.urandom(size_mb * 1024 * 1024)
        
        print(f"Benchmark AES-GCM: {size_mb} MB...")
        
        # Test chiffrement
        ciphertext, iv, enc_metadata = cipher.encrypt(data)
        
        # Test déchiffrement
        plaintext, dec_metadata = cipher.decrypt(ciphertext, iv)
        
        # Vérification
        assert plaintext == data, "Erreur de déchiffrement!"
        
        results.append({
            'size_mb': size_mb,
            'encryption': enc_metadata,
            'decryption': dec_metadata
        })
        
        print(f"  ✓ Chiffrement: {enc_metadata['encryption_time_ms']:.2f} ms "
              f"({enc_metadata['throughput_mbps']:.2f} MB/s)")
        print(f"  ✓ Déchiffrement: {dec_metadata['decryption_time_ms']:.2f} ms "
              f"({dec_metadata['throughput_mbps']:.2f} MB/s)")
    
    return results


if __name__ == "__main__":
    print("="*70)
    print("AES-256-GCM - Implémentation conforme NIST")
    print("FIPS 197 (AES) + SP 800-38D (GCM)")
    print("="*70)
    print()
    
    # Test simple
    cipher = AESGCMCipher()
    message = b"Ceci est un message secret conforme NIST"
    
    print("Test basique:")
    print(f"  Message: {message.decode()}")
    
    ciphertext, iv, meta = cipher.encrypt(message)
    print(f"  Chiffré: {len(ciphertext)} bytes (overhead: {meta['overhead_bytes']} bytes)")
    
    plaintext, _ = cipher.decrypt(ciphertext, iv)
    print(f"  Déchiffré: {plaintext.decode()}")
    print()
    
    # Benchmark
    print("Benchmark sur différentes tailles:")
    benchmark_aes_gcm([1, 10, 50])
