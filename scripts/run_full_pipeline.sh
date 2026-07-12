#!/bin/bash
################################################################################
# run_full_pipeline.sh
# Pipeline d'exécution complet pour benchmarking hybride (REAL DATA ONLY)
#
# Étapes :
# 1. Validation des données utilisateur
# 2. Entraînement VAE + historiques (loss + PSNR + composantes)
# 3. Micro-benchmarks (AES, Kyber)
# 4. Tests de sécurité (NIST vectors)
# 5. Macro-benchmarks (4 pipelines)
# 6. Analyse de scalabilité (7 tailles)
# 7. Génération figures (12+)
# 8. Génération tableaux LaTeX (6)
# 9. Rapport final PDF
################################################################################

set -euo pipefail

# ---- Move to project root (so relative paths always work) ----
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

START_TIME="$(date +%s)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Outputs
RESULTS_DIR="results"
DATA_DIR="${RESULTS_DIR}/data"
FIG_DIR="${RESULTS_DIR}/figures"
TAB_DIR="${RESULTS_DIR}/tables"
MODEL_DIR="${RESULTS_DIR}/models"
LOG_DIR="${RESULTS_DIR}/logs"

mkdir -p "$LOG_DIR" "$DATA_DIR" "$FIG_DIR" "$TAB_DIR" "$MODEL_DIR"

# Logging
LOG_FILE="${LOG_DIR}/execution_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Hybrid Secure Big Data - Pipeline Complet${NC}"
echo -e "${BLUE}  Exécution démarrée: $(date)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""

# ---- Ensure venv is active (activate automatically if needed) ----
if [ -z "${VIRTUAL_ENV:-}" ]; then
  if [ -f "venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "venv/bin/activate"
  fi
fi

if [ -z "${VIRTUAL_ENV:-}" ]; then
  echo -e "${RED}❌ Environnement virtuel non activé${NC}"
  echo "   Exécutez d'abord:"
  echo "   source venv/bin/activate"
  exit 1
fi

echo -e "${GREEN}✓${NC} Environnement virtuel activé: $VIRTUAL_ENV"

# Ensure imports find local src/
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:$PYTHONPATH}"

# ---- User data ----
echo ""
echo -e "${YELLOW}[1/9]${NC} Validation des données utilisateur..."

USER_DATA_DIR="data/user_data"
if [ ! -d "$USER_DATA_DIR" ]; then
  echo -e "${RED}❌ Répertoire ${USER_DATA_DIR} non trouvé${NC}"
  exit 1
fi

FILE_COUNT="$(find "$USER_DATA_DIR" -type f | wc -l | tr -d ' ')"
if [ "$FILE_COUNT" -eq 0 ]; then
  echo -e "${RED}❌ Aucun fichier trouvé dans ${USER_DATA_DIR}${NC}"
  echo ""
  echo "Placez vos données dans ce répertoire avant d'exécuter le pipeline."
  echo "Formats supportés: JPG, PNG, TXT, LOG, CSV, BIN, PDF, etc."
  exit 1
fi

echo "   → Fichiers détectés: ${FILE_COUNT}"

# Run data validation and inventory
python -m src.data.real_data_loader --validate

TOTAL_SIZE_BYTES="$(du -sb "$USER_DATA_DIR" | awk '{print $1}')"
TOTAL_SIZE_MB=$((TOTAL_SIZE_BYTES / 1024 / 1024))
TOTAL_SIZE_GB=$((TOTAL_SIZE_BYTES / 1024 / 1024 / 1024))

echo "   → Taille totale: ${TOTAL_SIZE_MB} MB (${TOTAL_SIZE_GB} GB)"
echo -e "${GREEN}✓${NC} Validation des données réussie"

# Create data manifest
python -m src.data.real_data_loader --create-manifest

echo ""
echo -e "${YELLOW}[2/9]${NC} Entraînement du VAE..."
echo "        Mode: Adaptatif selon taille données"
echo "        Tracking: Loss + PSNR par époque + figures training history"

# epochs policy
if [ "$TOTAL_SIZE_GB" -lt 1 ]; then
  EPOCHS=50
  echo "        Époques: ${EPOCHS} (mode complet, données < 1 GB)"
else
  EPOCHS=20
  echo "        Époques: ${EPOCHS} (mode rapide, données >= 1 GB)"
fi

# IMPORTANT:
# Our vae_trainer supports: --data-dir, --out, --epochs, --batch-size, --latent-dim, --beta, ...
# It writes:
# - results/models/vae_best.pt, results/models/vae_last.pt
# - results/metrics_vae_history.csv
# - results/figures/figure_vae_training_history.* and figure_vae_loss_components.*
python -m src.models.vae_trainer \
  --data-dir "$USER_DATA_DIR" \
  --out "$RESULTS_DIR" \
  --epochs "$EPOCHS" \
  --batch-size 64 \
  --latent-dim 128 \
  --beta 1.0 \
  --device cpu

# Sanity check: model file must exist
if [ ! -f "${MODEL_DIR}/vae_best.pt" ] && [ ! -f "${MODEL_DIR}/vae_last.pt" ]; then
  echo -e "${RED}❌ VAE: aucun modèle trouvé dans ${MODEL_DIR}${NC}"
  echo "   Attendu: vae_best.pt ou vae_last.pt"
  exit 1
fi

echo -e "${GREEN}✓${NC} VAE entraîné et sauvegardé"

echo ""
echo -e "${YELLOW}[3/9]${NC} Micro-benchmarks cryptographiques..."

echo "   → AES-256-GCM (1000 répétitions)..."
python -m src.benchmarks.micro_bench aes \
  --iterations 1000 \
  --sizes 1024 4096 16384 65536 262144 1048576 \
  --output "${DATA_DIR}/micro_aes.csv"

echo "   → CRYSTALS-Kyber ML-KEM-1024 (1000 répétitions)..."
python -m src.benchmarks.micro_bench kyber \
  --iterations 1000 \
  --algorithms Kyber512 Kyber768 Kyber1024 \
  --output "${DATA_DIR}/micro_kyber.csv"

echo -e "${GREEN}✓${NC} Micro-benchmarks terminés"

echo ""
echo -e "${YELLOW}[4/9]${NC} Tests de sécurité..."

echo "   → Vecteurs NIST pour AES-GCM..."
python -m src.security.nist_vectors \
  --test aes-gcm \
  --output "${DATA_DIR}/security_aes.csv"

echo "   → Tests de consistance KEM..."
python -m src.security.kem_validator \
  --iterations 100 \
  --output "${DATA_DIR}/security_kem.csv"

echo -e "${GREEN}✓${NC} Tests de sécurité réussis"

echo ""
echo -e "${YELLOW}[5/9]${NC} Macro-benchmarks (4 pipelines)..."
echo "        Pipeline A: VAE → AES-GCM → Kyber-1024"
echo "        Pipeline B: Raw → AES-GCM + Kyber-1024"
echo "        Pipeline C: Raw → AES-GCM only"
echo "        Pipeline D: Compresseur → AES-GCM + Kyber-1024"
echo "        Répétitions: 20 par configuration"

# Prefer best model if present, else last
VAE_MODEL_PATH="${MODEL_DIR}/vae_best.pt"
if [ ! -f "$VAE_MODEL_PATH" ]; then
  VAE_MODEL_PATH="${MODEL_DIR}/vae_last.pt"
fi

python -m src.benchmarks.macro_bench \
  --data-dir "$USER_DATA_DIR" \
  --vae-model "$VAE_MODEL_PATH" \
  --repetitions 20 \
  --pipelines A B C D \
  --compressors vae zstd lz4 gzip bz2 brotli \
  --output "${DATA_DIR}/macro_benchmarks.csv"

echo -e "${GREEN}✓${NC} Macro-benchmarks terminés"

echo ""
echo -e "${YELLOW}[6/9]${NC} Analyse de scalabilité..."
echo "        Tailles testées: 1 MB, 10 MB, 100 MB, 500 MB, 1 GB, 2 GB, 5 GB"
echo "        Métriques: Temps, Throughput, CPU%, RAM"

python -m src.benchmarks.scalability_bench \
  --data-dir "$USER_DATA_DIR" \
  --vae-model "$VAE_MODEL_PATH" \
  --sizes 1M 10M 100M 500M 1G 2G 5G \
  --repetitions 10 \
  --output "${DATA_DIR}/scalability.csv"

echo -e "${GREEN}✓${NC} Analyse de scalabilité terminée"

echo ""
echo -e "${YELLOW}[7/9]${NC} Génération des figures (12+)..."
echo "        Format: PDF vectoriel + PNG 300 DPI"
echo "        Style: modern, publication-ready"

python -m src.visualization.figure_generator \
  --data-dir "$DATA_DIR" \
  --output-dir "$FIG_DIR" \
  --dpi 300 \
  --format pdf png

# Check figures count (PDF)
FIG_PDF_COUNT="$(find "$FIG_DIR" -maxdepth 1 -type f -name "*.pdf" | wc -l | tr -d ' ')"
echo "   → Figures PDF générées: ${FIG_PDF_COUNT}"

if [ "$FIG_PDF_COUNT" -lt 12 ]; then
  echo -e "${RED}❌ Figures insuffisantes: ${FIG_PDF_COUNT}/12${NC}"
  echo "   Vérifie:"
  echo "   - Que src.visualization.figure_generator génère bien toutes les figures"
  echo "   - Que tous les CSV attendus existent dans ${DATA_DIR}"
  echo "   - Consulte le log: ${LOG_FILE}"
  exit 1
fi

echo -e "${GREEN}✓${NC} Figures générées dans ${FIG_DIR}/"

echo ""
echo -e "${YELLOW}[8/9]${NC} Génération des tableaux LaTeX (6)..."

python -m src.visualization.table_generator \
  --data-dir "$DATA_DIR" \
  --output-dir "$TAB_DIR"

echo -e "${GREEN}✓${NC} Tableaux LaTeX générés dans ${TAB_DIR}/"

echo ""
echo -e "${YELLOW}[9/9]${NC} Création du rapport final..."

python -m src.visualization.report_builder \
  --figures-dir "$FIG_DIR" \
  --tables-dir "$TAB_DIR" \
  --data-dir "$DATA_DIR" \
  --output "${RESULTS_DIR}/report_FINAL.pdf"

echo -e "${GREEN}✓${NC} Rapport PDF généré: ${RESULTS_DIR}/report_FINAL.pdf"

echo ""
echo "Génération du manifeste de reproductibilité..."
python -m src.metrics.manifest_generator \
  --output "${RESULTS_DIR}/reproducibility_manifest.json"

echo -e "${GREEN}✓${NC} Manifeste: ${RESULTS_DIR}/reproducibility_manifest.json"

# Summary
END_TIME="$(date +%s)"
DUR=$((END_TIME - START_TIME))

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Pipeline complet terminé avec succès !${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""
echo "Durée totale: ${DUR} secondes"
echo ""
echo -e "${CYAN}Résultats disponibles :${NC}"
echo ""
echo "  📊 Figures (>=12):"
echo "     ${FIG_DIR}/*.pdf"
echo "     ${FIG_DIR}/*.png"
echo ""
echo "  📋 Tableaux LaTeX:"
echo "     ${TAB_DIR}/*.tex"
echo ""
echo "  📈 Données brutes (CSV):"
echo "     ${DATA_DIR}/*.csv"
echo ""
echo "  📄 Rapport final:"
echo "     ${RESULTS_DIR}/report_FINAL.pdf"
echo ""
echo "  🔍 Manifeste reproductibilité:"
echo "     ${RESULTS_DIR}/reproducibility_manifest.json"
echo ""
echo "  📝 Log d'exécution:"
echo "     ${LOG_FILE}"
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"

