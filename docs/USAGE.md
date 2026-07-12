# Guide d'utilisation

## Utilisation basique

### 1. Placer vos données
```bash
cp /chemin/vers/vos/fichiers/* data/user_data/
```

### 2. Lancer le pipeline
```bash
bash scripts/run_full_pipeline.sh
```

### 3. Récupérer les résultats
```bash
ls results/figures/*.pdf    # 12 figures
ls results/tables/*.tex     # 6 tableaux
ls results/data/*.csv       # Données brutes
```

## Utilisation avancée

### Utilisation Python directe
```python
from src.data.real_data_loader import RealDataLoader
from src.pipelines.hybrid_pipeline import HybridPipeline

# Charger données
loader = RealDataLoader()
data = loader.get_file_batch(batch_size_gb=1.0)

# Pipeline hybride
pipeline = HybridPipeline('A')  # VAE + AES + KEM
encrypted, metadata = pipeline.encrypt(data[0])
```

## Types de données supportés
- Images: .jpg, .png, .bmp
- Textes: .txt, .log, .md
- CSV: .csv, .tsv
- Binaires: .pdf, .bin

Pour plus de détails, voir README_COMPLET.md
