# Guide d'installation détaillé

## Installation rapide (3 étapes)

```bash
# 1. Décompression
unzip hybrid_secure_bigdata_FINAL_v2.zip && cd hybrid_secure_bigdata

# 2. Installation
bash scripts/setup_environment.sh && source venv/bin/activate
bash scripts/install_supercop.sh

# 3. Vérification
python -c "import torch, oqs; print('✓ Installation OK')"
```

## Prérequis
- Ubuntu 22.04 LTS
- 8 GB RAM minimum
- 20 GB espace disque

## Support
Voir README_COMPLET.md pour détails complets
