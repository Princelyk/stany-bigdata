#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compresseurs classiques pour comparaison avec VAE
Baselines: zstd, lz4, gzip, bz2, brotli
"""

import time
import gzip
import bz2
import lz4.frame
import zstandard as zstd
import brotli
from typing import Tuple, Dict


class ClassicCompressor:
    """
    Interface unifiée pour tous les compresseurs classiques
    """
    
    ALGORITHMS = ['zstd', 'lz4', 'gzip', 'bz2', 'brotli']
    
    def __init__(self, algorithm: str = 'zstd', level: int = None):
        """
        Args:
            algorithm: 'zstd', 'lz4', 'gzip', 'bz2', 'brotli'
            level: Niveau de compression (None = défaut)
        """
        if algorithm not in self.ALGORITHMS:
            raise ValueError(f"Algorithme invalide. Choisir: {self.ALGORITHMS}")
        
        self.algorithm = algorithm
        self.level = level
    
    def compress(self, data: bytes) -> Tuple[bytes, Dict]:
        """
        Compresse les données
        
        Returns:
            (compressed_data, metadata)
        """
        start_time = time.perf_counter()
        
        if self.algorithm == 'zstd':
            compressor = zstd.ZstdCompressor(level=self.level or 3)
            compressed = compressor.compress(data)
        
        elif self.algorithm == 'lz4':
            compressed = lz4.frame.compress(data, compression_level=self.level or 0)
        
        elif self.algorithm == 'gzip':
            compressed = gzip.compress(data, compresslevel=self.level or 9)
        
        elif self.algorithm == 'bz2':
            compressed = bz2.compress(data, compresslevel=self.level or 9)
        
        elif self.algorithm == 'brotli':
            compressed = brotli.compress(data, quality=self.level or 11)
        
        elapsed = (time.perf_counter() - start_time) * 1000  # ms
        
        metadata = {
            'algorithm': self.algorithm,
            'level': self.level,
            'size_original_bytes': len(data),
            'size_compressed_bytes': len(compressed),
            'compression_ratio': len(data) / len(compressed) if len(compressed) > 0 else 0,
            'compression_rate': len(compressed) / len(data) if len(data) > 0 else 0,
            'compression_time_ms': elapsed,
            'throughput_mbps': (len(data) / (1024*1024)) / (elapsed / 1000) if elapsed > 0 else 0
        }
        
        return compressed, metadata
    
    def decompress(self, data: bytes) -> Tuple[bytes, Dict]:
        """
        Décompresse les données
        
        Returns:
            (decompressed_data, metadata)
        """
        start_time = time.perf_counter()
        
        if self.algorithm == 'zstd':
            decompressor = zstd.ZstdDecompressor()
            decompressed = decompressor.decompress(data)
        
        elif self.algorithm == 'lz4':
            decompressed = lz4.frame.decompress(data)
        
        elif self.algorithm == 'gzip':
            decompressed = gzip.decompress(data)
        
        elif self.algorithm == 'bz2':
            decompressed = bz2.decompress(data)
        
        elif self.algorithm == 'brotli':
            decompressed = brotli.decompress(data)
        
        elapsed = (time.perf_counter() - start_time) * 1000
        
        metadata = {
            'algorithm': self.algorithm,
            'size_compressed_bytes': len(data),
            'size_decompressed_bytes': len(decompressed),
            'decompression_time_ms': elapsed,
            'throughput_mbps': (len(decompressed) / (1024*1024)) / (elapsed / 1000) if elapsed > 0 else 0
        }
        
        return decompressed, metadata


def benchmark_compressors(data: bytes, algorithms: list = None) -> Dict:
    """
    Benchmark tous les compresseurs sur les mêmes données
    """
    if algorithms is None:
        algorithms = ClassicCompressor.ALGORITHMS
    
    results = []
    
    for algo in algorithms:
        compressor = ClassicCompressor(algorithm=algo)
        
        # Compression
        compressed, comp_meta = compressor.compress(data)
        
        # Décompression
        decompressed, decomp_meta = compressor.decompress(compressed)
        
        # Vérification
        assert decompressed == data, f"Erreur {algo}: données différentes!"
        
        results.append({
            'algorithm': algo,
            'compression': comp_meta,
            'decompression': decomp_meta
        })
        
        print(f"{algo:8s} | Ratio: {comp_meta['compression_ratio']:.2f}x | "
              f"Comp: {comp_meta['compression_time_ms']:.2f} ms | "
              f"Decomp: {decomp_meta['decompression_time_ms']:.2f} ms")
    
    return results


if __name__ == "__main__":
    import os
    
    print("="*70)
    print("Benchmark des compresseurs classiques")
    print("="*70)
    
    # Données de test (1 MB aléatoire)
    test_data = os.urandom(1024 * 1024)
    
    print(f"\nTaille des données: {len(test_data) / (1024*1024):.2f} MB")
    print()
    
    results = benchmark_compressors(test_data)
    
    # Tri par ratio de compression
    results.sort(key=lambda x: x['compression']['compression_ratio'], reverse=True)
    
    print("\n" + "="*70)
    print("Meilleur ratio de compression:")
    best = results[0]
    print(f"  {best['algorithm']}: {best['compression']['compression_ratio']:.2f}x")
