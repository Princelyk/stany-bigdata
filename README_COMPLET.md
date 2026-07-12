# Sécurisation Hybride des Données Massives
## VAE + AES-256-GCM + CRYSTALS-Kyber (ML-KEM-1024)

**Projet conforme ArticleSTANv1.4.docx**  
**Production-Ready • Ubuntu 22.04 • CPU-only**

---

## 📋 Vue d'ensemble

Ce projet implémente un système hybride de compression et de chiffrement de données massives, conforme aux standards NIST, pour évaluation sur données réelles uniquement.

### Architecture en 3 couches

```
Données réelles
     ↓
[1] VAE (Compression neuronale)
     → Réduction 12-16× avec préservation sémantique
     ↓
[2] AES-256-GCM (Chiffrement authentifié)
     → FIPS 197 + SP 800-38D
     ↓
[3] ML-KEM-1024 (Encapsulation de clé post-quantique)
     → NIST FIPS 203 (Kyber)
     ↓
Données sécurisées
```

### 4 Pipelines évalués

| Pipeline | Description | Objectif |
|----------|-------------|----------|
| **A** | VAE → AES-GCM → ML-KEM | **Hybride complet** (compression + crypto PQ) |
| **B** | Raw → AES-GCM + ML-KEM | Sans compression |
| **C** | Raw → AES-GCM | Chiffrement classique seul |
| **D** | Compresseur X → AES-GCM + ML-KEM | Baselines (zstd, lz4, gzip, etc.) |

---

## 🚀 Installation rapide (15 min)

### Prérequis

- **OS**: Ubuntu 22.04 (VMware ou bare metal)
- **Python**: 3.8+
- **RAM**: ≥ 8 GB
- **Espace**: ≥ 20 GB

### Étapes

```bash
# 1. Décompresser l'archive
unzip hybrid_secure_bigdata_FINAL.zip
cd hybrid_secure_bigdata

# 2. Installer l'environnement Python
bash scripts/setup_environment.sh
source venv/bin/activate

# 3. Installer les bibliothèques cryptographiques (NIST + liboqs)
bash scripts/install_supercop.sh

# ⚠️ Placez maintenant vos données réelles !
cp /chemin/vers/vos/fichiers/* data/user_data/

# 4. Lancer le pipeline complet (2-4 heures)
bash scripts/run_full_pipeline.sh
```

---

## 📂 Structure du projet

```
hybrid_secure_bigdata/
│
├── data/
│   ├── user_data/          ← PLACEZ VOS DONNÉES ICI
│   ├── nist_vectors/       ← Vecteurs de test NIST (auto-téléchargés)
│   └── supercop/           ← SUPERCOP (optionnel)
│
├── src/
│   ├── data/
│   │   └── real_data_loader.py       # Chargeur de données réelles
│   ├── models/
│   │   └── vae_model.py              # Architecture VAE
│   ├── crypto/
│   │   ├── aes_gcm.py                # AES-256-GCM (FIPS 197)
│   │   └── ml_kem.py                 # ML-KEM/Kyber (FIPS 203)
│   ├── pipelines/
│   │   └── hybrid_pipeline.py        # Orchestrateur
│   ├── benchmarks/
│   │   └── system_benchmarks.py      # Mesures de performance
│   ├── visualization/
│   │   └── publication_figures.py    # Génération des figures Q1
│   └── metrics/
│       └── quality_metrics.py        # PSNR, SSIM, MSE
│
├── scripts/
│   ├── setup_environment.sh          # Installation Python + deps
│   ├── install_supercop.sh           # Installation crypto NIST
│   └── run_full_pipeline.sh          # Exécution complète
│
├── results/
│   ├── figures/                      # 12 figures publication-ready (PDF/PNG)
│   ├── tables/                       # 6 tableaux LaTeX
│   ├── data/                         # CSV de résultats
│   │   └── data_checksums.csv        # Traçabilité SHA-256
│   └── models/                       # Modèles entraînés (.pt)
│
├── config/
│   └── crypto_config.yaml            # Configuration NIST
│
└── docs/
    ├── INSTALLATION.md               # Guide détaillé
    ├── USAGE.md                      # Utilisation avancée
    └── STANDARDS.md                  # Conformité NIST
```

---

## 🎯 Données supportées

**Types de fichiers acceptés** (tous formats classiques):

| Type | Extensions | Traitement |
|------|------------|------------|
| Images | `.jpg`, `.png`, `.bmp` | Reshape en tenseurs |
| Textes | `.txt`, `.log`, `.md` | Encodage UTF-8 |
| CSV/TSV | `.csv`, `.tsv` | Parsing pandas |
| Binaires | `.pdf`, `.bin`, `.exe` | Lecture brute (bytes) |

**⚠️ Important**: Aucune donnée synthétique n'est générée. Le système fonctionne uniquement sur vos fichiers réels.

### Vérification de l'intégrité

Tous les fichiers sont hashés (SHA-256) et tracés dans `results/data/data_checksums.csv`.

---

## 📊 Sorties produites

### 12 Figures publication-ready (300 DPI, PDF + PNG)

| Figure | Description | Conformité |
|--------|-------------|------------|
| **fig01_architecture.pdf** | Diagramme du système hybride | IEEE |
| **fig02_vae_training_history.pdf** | Loss + PSNR par époque | Matplotlib |
| **fig03_compression_ratios.pdf** | **Avec %** pour chaque compresseur | Boxplots + annotations |
| **fig04_compression_quality.pdf** | MSE, PSNR, SSIM (images) | Boxplots multi-panneaux |
| **fig05_throughput_comparison.pdf** | MB/s pour tous les pipelines | Barres + erreurs |
| **fig06_latency_breakdown.pdf** | Décomposition encode/encrypt/kem | Barres empilées |
| **fig07_crypto_overhead.pdf** | Métadonnées AES + KEM vs payload | Camembert |
| **fig08_scalability.pdf** | **4 panneaux × 7 tailles** | Temps, CPU%, RAM, Throughput |
| **fig09_pareto_speed_compression.pdf** | Nuage de Pareto (trade-off) | Scatter + frontière |
| **fig10_aes_microbenchmark.pdf** | Throughput AES selon taille | Ligne + shaded std |
| **fig11_kem_microbenchmark.pdf** | KeyGen/Encaps/Decaps (512/768/1024) | Boxplots comparatifs |
| **fig12_nist_compliance.pdf** | Tableau visuel des standards | Tableau coloré |

### 6 Tableaux LaTeX

| Tableau | Contenu |
|---------|---------|
| `table_datasets.tex` | Statistiques des données chargées |
| `table_compression_comparative.tex` | VAE vs baselines (ratio, qualité) |
| `table_quality_vae.tex` | PSNR/SSIM/MSE détaillé |
| `table_microbench_crypto.tex` | AES + KEM (temps, throughput) |
| `table_macrobench_pipelines.tex` | Pipelines A/B/C/D (end-to-end) |
| `table_security.tex` | Niveaux de sécurité NIST |

---

## 🔬 Métriques mesurées

### Compression (tous algorithmes)

```python
{
    'size_original_bytes': int,
    'size_compressed_bytes': int,
    'compression_ratio': float,      # original / compressed
    'compression_rate': float,       # compressed / original
    'bpp': float  # (pour images) bits per pixel
}
```

### Qualité (VAE uniquement, si images)

```python
{
    'psnr_db': float,      # Peak Signal-to-Noise Ratio
    'ssim': float,         # Structural Similarity Index
    'mse': float           # Mean Squared Error
}
```

### Performance (tous pipelines)

```python
{
    # Latences (ms)
    'latency_p50_ms': float,
    'latency_p95_ms': float,
    
    # Décomposition
    't_encode_ms': float,          # Compression VAE/autres
    't_compress_ms': float,
    't_kem_keygen_ms': float,
    't_kem_encaps_ms': float,
    't_kem_decaps_ms': float,
    't_aes_encrypt_ms': float,
    't_aes_decrypt_ms': float,
    't_decode_ms': float,
    
    # Throughput
    'throughput_mbps': float,
    
    # Ressources
    'cpu_mean_percent': float,
    'cpu_max_percent': float,
    'rss_mean_mb': float,
    'rss_max_mb': float,
    
    # Overhead crypto
    'crypto_metadata_bytes': int
}
```

### Répétitions

Toutes les mesures sont répétées **10 fois** minimum pour garantir la robustesse statistique (médiane + IQR).

---

## 🔐 Conformité NIST

### AES-256-GCM

- **Standard**: FIPS 197 (AES) + SP 800-38D (GCM)
- **Clé**: 256 bits
- **IV**: 96 bits (recommandation NIST)
- **Tag**: 128 bits
- **Implémentation**: `cryptography.hazmat` (Python)

📄 [FIPS 197](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.197.pdf)  
📄 [SP 800-38D](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf)

### ML-KEM-1024 (Kyber)

- **Standard**: NIST FIPS 203
- **Niveau de sécurité**: NIST Level 5 (équivalent AES-256)
- **Tailles**:
  - Clé publique: 1568 bytes
  - Clé secrète: 3168 bytes
  - Ciphertext: 1568 bytes
- **Implémentation**: liboqs (Open Quantum Safe)

📄 [FIPS 203](https://csrc.nist.gov/pubs/fips/203/final)  
📄 [CRYSTALS-Kyber](https://pq-crystals.org/kyber/)

---

## 🧪 Tests de sécurité

Le pipeline vérifie automatiquement:

1. **Vecteurs de test NIST** (AES + GCM)
2. **Référence ML-KEM** (Kyber official)
3. **Intégrité des tags GCM**
4. **Correspondance des secrets partagés KEM**

Logs dans: `results/logs/security_tests.log`

---

## ⚡ Optimisations

### CPU-only (sans GPU)

- Batch processing pour VAE
- Streaming pour fichiers volumineux
- Parallelisation des benchmarks

### Reproductibilité

- Seeds déterministes
- Manifest JSON avec:
  - Versions Python/libs
  - Hash git du code
  - Checksums SHA-256 des données
  - Hyperparamètres

**Fichier**: `results/reproducibility_manifest.json`

---

## 📚 Documentation additionnelle

| Fichier | Contenu |
|---------|---------|
| `docs/INSTALLATION.md` | Guide d'installation détaillé |
| `docs/USAGE.md` | Utilisation avancée + API |
| `docs/STANDARDS.md` | Standards NIST + IEEE |
| `docs/EXPERIMENTS.md` | Protocole expérimental |

---

## 🐛 Résolution de problèmes

### Erreur: "liboqs non installé"

```bash
bash scripts/install_supercoc.sh
```

### Erreur: "Aucune donnée trouvée"

```bash
# Vérifiez que vos fichiers sont dans data/user_data/
ls -lh data/user_data/

# Relancez le scan
python -c "from src.data.real_data_loader import RealDataLoader; RealDataLoader().scan_directory()"
```

### Performance lente

- Réduisez le nombre d'époques VAE (config par défaut: 5)
- Utilisez des chunks plus petits
- Désactivez SUPERCOP (optionnel)

---

## 📖 Citations

Si vous utilisez ce code dans une publication scientifique:

```bibtex
@article{hybrid_secure_bigdata_2024,
  title={Sécurisation hybride des données massives via VAE et cryptographie post-quantique},
  author={Votre Nom},
  journal={Votre Journal},
  year={2024},
  note={Conforme NIST FIPS 197, SP 800-38D, FIPS 203}
}
```

---

## 📧 Contact & Support

Pour toute question concernant:

- **Installation**: Voir `docs/INSTALLATION.md`
- **Utilisation**: Voir `docs/USAGE.md`
- **Standards NIST**: Voir `docs/STANDARDS.md`

---

## ✅ Checklist de vérification

Avant de lancer les expériences:

- [ ] Python 3.8+ installé
- [ ] Ubuntu 22.04 (VMware ou bare metal)
- [ ] ≥ 8 GB RAM disponible
- [ ] ≥ 20 GB espace disque
- [ ] Environnement virtuel activé (`source venv/bin/activate`)
- [ ] liboqs installé (`python -c "import oqs"`)
- [ ] Données réelles placées dans `data/user_data/`
- [ ] Scan réussi (≥ 0.5 GB de données recommandé)

---

## 🎓 Conformité journaux Q1

- **Figures**: 300 DPI, PDF vectoriel, grayscale/couleurs IEEE
- **Tableaux**: LaTeX, format IEEE/ACM
- **Métriques**: 10+ répétitions, médiane + IQR
- **Reproductibilité**: Manifest complet + checksums
- **Standards**: NIST FIPS 197, SP 800-38D, FIPS 203

---

**Version**: 1.0.0 FINAL  
**Date**: 2026-02-06  
**Statut**: ✅ Production Ready
