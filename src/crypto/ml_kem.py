#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Implémentation ML-KEM (Kyber) conforme NIST FIPS 203
Utilise liboqs (Open Quantum Safe)
"""

import time
from typing import Tuple, Dict
try:
    import oqs
    LIBOQS_AVAILABLE = True
except ImportError:
    LIBOQS_AVAILABLE = False
    print("⚠️  liboqs non disponible. Installez avec: pip install liboqs-python")


class MLKEMCipher:
    """
    Mécanisme d'encapsulation de clé post-quantique ML-KEM (Kyber)
    
    Conformité NIST:
    - FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism
    - Algorithme: CRYSTALS-Kyber
    
    Niveaux de sécurité:
    - Kyber512: Équivalent AES-128 (NIST Level 1)
    - Kyber768: Équivalent AES-192 (NIST Level 3)
    - Kyber1024: Équivalent AES-256 (NIST Level 5) ← Utilisé ici
    
    Référence:
    - https://csrc.nist.gov/pubs/fips/203/final
    - https://pq-crystals.org/kyber/
    """
    
    def __init__(self, security_level: int = 1024):
        """
        Initialise le KEM Kyber
        
        Args:
            security_level: 512, 768, ou 1024 (défaut: 1024 = AES-256 équivalent)
        """
        if not LIBOQS_AVAILABLE:
            raise ImportError(
                "liboqs n'est pas installé. "
                "Exécutez: bash scripts/install_supercop.sh"
            )
        
        # Mapping des niveaux de sécurité
        kem_algorithms = {
            512: "Kyber512",
            768: "Kyber768",
            1024: "Kyber1024"
        }
        
        if security_level not in kem_algorithms:
            raise ValueError(f"Niveau de sécurité invalide. Choisir: {list(kem_algorithms.keys())}")
        
        self.security_level = security_level
        self.algorithm_name = kem_algorithms[security_level]
        
        # Création du KEM
        self.kem = oqs.KeyEncapsulation(self.algorithm_name)
        
        # Récupération des détails
        self.details = self.kem.details
        
        # Clés (générées à la première utilisation)
        self.public_key = None
        self.secret_key = None
    
    def generate_keypair(self) -> Tuple[bytes, bytes, Dict]:
        """
        Génère une paire de clés Kyber
        
        Returns:
            (public_key, secret_key, metadata)
        """
        start_time = time.perf_counter()
        
        # Génération de clés
        self.public_key = self.kem.generate_keypair()
        self.secret_key = self.kem.export_secret_key()
        
        elapsed = (time.perf_counter() - start_time) * 1000  # ms
        
        metadata = {
            'algorithm': self.algorithm_name,
            'standard': 'NIST FIPS 203 (ML-KEM)',
            'security_level': self.security_level,
            'public_key_size_bytes': len(self.public_key),
            'secret_key_size_bytes': len(self.secret_key),
            'keygen_time_ms': elapsed,
            'claimed_nist_level': self.details['claimed_nist_level'],
            'claimed_security': self.details['claimed_security']
        }
        
        return self.public_key, self.secret_key, metadata
    
    def encapsulate(self, public_key: bytes = None) -> Tuple[bytes, bytes, Dict]:
        """
        Encapsule un secret partagé
        
        Args:
            public_key: Clé publique du destinataire (utilise self.public_key si None)
        
        Returns:
            (ciphertext, shared_secret, metadata)
        """
        if public_key is None:
            if self.public_key is None:
                raise ValueError("Aucune clé publique disponible. Générez d'abord une paire de clés.")
            public_key = self.public_key
        
        start_time = time.perf_counter()
        
        # Encapsulation
        ciphertext, shared_secret = self.kem.encap_secret(public_key)
        
        elapsed = (time.perf_counter() - start_time) * 1000
        
        metadata = {
            'algorithm': self.algorithm_name,
            'ciphertext_size_bytes': len(ciphertext),
            'shared_secret_size_bytes': len(shared_secret),
            'encapsulation_time_ms': elapsed
        }
        
        return ciphertext, shared_secret, metadata
    
    def decapsulate(self, ciphertext: bytes, secret_key: bytes = None) -> Tuple[bytes, Dict]:
        """
        Décapsule le secret partagé
        
        Args:
            ciphertext: Texte chiffré du KEM
            secret_key: Clé secrète (utilise self.secret_key si None)
        
        Returns:
            (shared_secret, metadata)
        """
        if secret_key is None:
            if self.secret_key is None:
                raise ValueError("Aucune clé secrète disponible.")
            secret_key = self.secret_key
        
        # Import de la clé secrète si nécessaire
        if secret_key != self.secret_key:
            self.kem = oqs.KeyEncapsulation(self.algorithm_name, secret_key)
        
        start_time = time.perf_counter()
        
        # Décapsulation
        shared_secret = self.kem.decap_secret(ciphertext)
        
        elapsed = (time.perf_counter() - start_time) * 1000
        
        metadata = {
            'algorithm': self.algorithm_name,
            'ciphertext_size_bytes': len(ciphertext),
            'shared_secret_size_bytes': len(shared_secret),
            'decapsulation_time_ms': elapsed
        }
        
        return shared_secret, metadata
    
    def get_algorithm_info(self) -> Dict:
        """
        Retourne les informations sur l'algorithme
        """
        return {
            'name': self.algorithm_name,
            'version': self.details.get('version', 'unknown'),
            'claimed_nist_level': self.details['claimed_nist_level'],
            'claimed_security': self.details['claimed_security'],
            'length_public_key': self.details['length_public_key'],
            'length_secret_key': self.details['length_secret_key'],
            'length_ciphertext': self.details['length_ciphertext'],
            'length_shared_secret': self.details['length_shared_secret']
        }


def benchmark_mlkem(security_levels: list = [512, 768, 1024], iterations: int = 100) -> Dict:
    """
    Benchmark ML-KEM sur différents niveaux de sécurité
    """
    results = []
    
    for level in security_levels:
        print(f"\nBenchmark Kyber{level} ({iterations} itérations)...")
        
        kem = MLKEMCipher(security_level=level)
        
        # Métriques
        keygen_times = []
        encap_times = []
        decap_times = []
        
        for i in range(iterations):
            # Génération de clés
            pub_key, sec_key, keygen_meta = kem.generate_keypair()
            keygen_times.append(keygen_meta['keygen_time_ms'])
            
            # Encapsulation
            ciphertext, shared_secret1, encap_meta = kem.encapsulate()
            encap_times.append(encap_meta['encapsulation_time_ms'])
            
            # Décapsulation
            shared_secret2, decap_meta = kem.decapsulate(ciphertext)
            decap_times.append(decap_meta['decapsulation_time_ms'])
            
            # Vérification
            assert shared_secret1 == shared_secret2, "Secrets partagés différents!"
        
        import numpy as np
        
        result = {
            'security_level': level,
            'algorithm': f'Kyber{level}',
            'iterations': iterations,
            'keygen': {
                'mean_ms': np.mean(keygen_times),
                'std_ms': np.std(keygen_times),
                'min_ms': np.min(keygen_times),
                'max_ms': np.max(keygen_times)
            },
            'encapsulation': {
                'mean_ms': np.mean(encap_times),
                'std_ms': np.std(encap_times),
                'min_ms': np.min(encap_times),
                'max_ms': np.max(encap_times)
            },
            'decapsulation': {
                'mean_ms': np.mean(decap_times),
                'std_ms': np.std(decap_times),
                'min_ms': np.min(decap_times),
                'max_ms': np.max(decap_times)
            },
            'sizes': kem.get_algorithm_info()
        }
        
        results.append(result)
        
        print(f"  ✓ KeyGen: {result['keygen']['mean_ms']:.3f} ± {result['keygen']['std_ms']:.3f} ms")
        print(f"  ✓ Encaps: {result['encapsulation']['mean_ms']:.3f} ± {result['encapsulation']['std_ms']:.3f} ms")
        print(f"  ✓ Decaps: {result['decapsulation']['mean_ms']:.3f} ± {result['decapsulation']['std_ms']:.3f} ms")
    
    return results


if __name__ == "__main__":
    if not LIBOQS_AVAILABLE:
        print("liboqs non installé. Exécutez:")
        print("  bash scripts/install_supercop.sh")
        exit(1)
    
    print("="*70)
    print("ML-KEM (Kyber) - Implémentation conforme NIST FIPS 203")
    print("="*70)
    print()
    
    # Test simple
    kem = MLKEMCipher(security_level=1024)
    
    print("Informations sur l'algorithme:")
    info = kem.get_algorithm_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
    print()
    
    # Test de bout en bout
    print("Test d'encapsulation/décapsulation:")
    pub_key, sec_key, keygen_meta = kem.generate_keypair()
    print(f"  ✓ Clés générées en {keygen_meta['keygen_time_ms']:.3f} ms")
    
    ciphertext, secret1, encap_meta = kem.encapsulate()
    print(f"  ✓ Encapsulation en {encap_meta['encapsulation_time_ms']:.3f} ms")
    
    secret2, decap_meta = kem.decapsulate(ciphertext)
    print(f"  ✓ Décapsulation en {decap_meta['decapsulation_time_ms']:.3f} ms")
    
    assert secret1 == secret2
    print(f"  ✓ Secrets partagés identiques ({len(secret1)} bytes)")
    print()
    
    # Benchmark
    print("Benchmark sur 3 niveaux de sécurité:")
    benchmark_mlkem([512, 768, 1024], iterations=50)
