#!/bin/bash
################################################################################
# setup_environment.sh
# Installation complète pour Ubuntu 22.04 (testé VMware)
#
# Ce script installe :
# 1. Dépendances système (build tools, libs)
# 2. Python venv + packages
# 3. liboqs (Open Quantum Safe) pour ML-KEM (ex-Kyber)
# 4. liboqs-python (bindings Python) - robuste (pip puis fallback source)
#
# Usage: bash scripts/setup_environment.sh
################################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Hybrid Secure Big Data - Installation Complète${NC}"
echo -e "${BLUE}  Ubuntu 22.04 LTS (VMware compatible)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""

# Check OS
if [ ! -f /etc/lsb-release ]; then
  echo -e "${RED}❌ Erreur: /etc/lsb-release non trouvé${NC}"
  echo "   Ce script est conçu pour Ubuntu 22.04"
  exit 1
fi

OS_VERSION=$(grep DISTRIB_RELEASE /etc/lsb-release | cut -d= -f2)
echo -e "${GREEN}✓${NC} OS détecté: Ubuntu ${OS_VERSION}"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
echo -e "${GREEN}✓${NC} Python version: ${PYTHON_VERSION}"

if [ "$(printf '%s\n' "3.10" "$PYTHON_VERSION" | sort -V | head -n1)" != "3.10" ]; then
  echo -e "${RED}❌ Python 3.10+ requis, détecté: ${PYTHON_VERSION}${NC}"
  exit 1
fi

# Check not root
if [ "${EUID}" -eq 0 ]; then
  echo -e "${RED}❌ Ne pas exécuter ce script en root${NC}"
  echo "   Exécutez en tant qu'utilisateur normal."
  exit 1
fi

echo ""
echo -e "${YELLOW}[1/6]${NC} Installation des dépendances système..."
echo "        (Cela peut demander votre mot de passe sudo)"

sudo apt-get update -qq
sudo apt-get install -y -qq \
  build-essential \
  cmake \
  ninja-build \
  git \
  wget \
  curl \
  libssl-dev \
  python3-dev \
  python3-venv \
  python3-pip \
  pkg-config \
  astyle \
  xsltproc \
  doxygen \
  graphviz \
  unzip

echo -e "${GREEN}✓${NC} Dépendances système installées"

echo ""
echo -e "${YELLOW}[2/6]${NC} Création environnement virtuel Python..."

if [ -d "venv" ]; then
  echo -e "${YELLOW}⚠${NC}  venv existe déjà, suppression..."
  rm -rf venv
fi

python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

PY_BIN="venv/bin/python"
PIP_BIN="venv/bin/pip"

${PY_BIN} -m pip install -U pip setuptools wheel --quiet
echo -e "${GREEN}✓${NC} Environnement virtuel créé: $(pwd)/venv"

echo ""
echo -e "${YELLOW}[3/6]${NC} Installation des packages Python..."
echo "        (Cela peut prendre 2-3 minutes)"

# NOTE: Sur Ubuntu/VM, mieux vaut installer torch/torchvision via index officiel.
# Ici, on garde ton pinning mais on ajoute l'index CPU pour éviter des wheels manquants.
${PIP_BIN} install --quiet --upgrade \
  "torch==2.1.0" \
  "torchvision==0.16.0" \
  --index-url https://download.pytorch.org/whl/cpu

${PIP_BIN} install --quiet \
  numpy==1.24.3 \
  pandas==2.0.3 \
  cryptography==41.0.7 \
  zstandard==0.21.0 \
  lz4==4.3.2 \
  brotli==1.0.9 \
  Pillow==10.0.1 \
  scikit-image==0.21.0 \
  scipy==1.11.3 \
  matplotlib==3.7.3 \
  seaborn==0.12.2 \
  psutil==5.9.6 \
  pytest==7.4.3 \
  pytest-cov==4.1.0 \
  tqdm==4.66.1 \
  pyyaml==6.0.1 \
  tabulate==0.9.0

echo -e "${GREEN}✓${NC} Packages Python installés"

echo ""
echo -e "${YELLOW}[4/6]${NC} Compilation liboqs (Open Quantum Safe)..."
echo "        (Cela peut prendre 5-10 minutes)"
echo "        liboqs fournit ML-KEM (ex-CRYSTALS-Kyber)"

LIBOQS_DIR="/tmp/liboqs-build-$$"
rm -rf "$LIBOQS_DIR"

echo "   → Clonage du dépôt liboqs..."
git clone --quiet --depth 1 https://github.com/open-quantum-safe/liboqs.git "$LIBOQS_DIR"

pushd "$LIBOQS_DIR" >/dev/null

echo "   → Configuration CMake..."
mkdir -p build
pushd build >/dev/null

cmake -GNinja \
  -DCMAKE_INSTALL_PREFIX="$VIRTUAL_ENV" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DOQS_USE_OPENSSL=ON \
  -DOQS_BUILD_ONLY_LIB=ON \
  .. >/dev/null

echo "   → Compilation (ninja)..."
ninja >/dev/null

echo "   → Installation dans venv..."
ninja install >/dev/null

popd >/dev/null
popd >/dev/null

rm -rf "$LIBOQS_DIR"

# Make sure runtime can find liboqs.so
export LD_LIBRARY_PATH="${VIRTUAL_ENV}/lib:${LD_LIBRARY_PATH:-}"
export LIBRARY_PATH="${VIRTUAL_ENV}/lib:${LIBRARY_PATH:-}"
export CPATH="${VIRTUAL_ENV}/include:${CPATH:-}"

if [ -f "$VIRTUAL_ENV/lib/liboqs.so" ] || [ -f "$VIRTUAL_ENV/lib/liboqs.dylib" ]; then
  echo -e "${GREEN}✓${NC} liboqs compilé et installé: $VIRTUAL_ENV/lib/"
else
  echo -e "${RED}❌ Erreur: liboqs non trouvé après installation${NC}"
  exit 1
fi

echo ""
echo -e "${YELLOW}[5/6]${NC} Installation liboqs-python (bindings Python)..."

# Try PyPI first (latest version)
set +e
${PIP_BIN} install --quiet -U liboqs-python
rc=$?
set -e

if [ $rc -ne 0 ]; then
  echo -e "${YELLOW}⚠${NC}  Installation via pip échouée. Fallback: build depuis source..."
  TMP_OQSPY="/tmp/liboqs-python-$$"
  rm -rf "$TMP_OQSPY"
  git clone --quiet --recursive https://github.com/open-quantum-safe/liboqs-python.git "$TMP_OQSPY"
  pushd "$TMP_OQSPY" >/dev/null
  ${PIP_BIN} install --quiet .
  popd >/dev/null
  rm -rf "$TMP_OQSPY"
fi

# Test import (and show versions)
${PY_BIN} - <<'PY'
import os, sys
import oqs
print("✓ oqs import OK")
try:
    print("  oqs lib version:", oqs.oqs_version())
except Exception as e:
    print("  WARN: oqs_version() failed:", e)
PY

echo -e "${GREEN}✓${NC} liboqs-python installé et fonctionnel"

echo ""
echo -e "${YELLOW}[6/6]${NC} Installation du projet en mode développement..."

# Install project package (editable)
${PIP_BIN} install --quiet -e .

echo -e "${GREEN}✓${NC} Package hybrid_secure_bigdata installé"

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Installation terminée avec succès !${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""
echo "Vérification des installations :"
echo ""

${PY_BIN} -c "import torch; print('  ✓ PyTorch:', torch.__version__)"
${PY_BIN} -c "import cryptography; print('  ✓ cryptography:', cryptography.__version__)"
${PY_BIN} -c "import oqs; print('  ✓ liboqs:', oqs.oqs_version())"
${PY_BIN} -c "import zstandard; print('  ✓ zstd: installé')"
${PY_BIN} -c "import lz4; print('  ✓ lz4: installé')"
${PY_BIN} -c "import brotli; print('  ✓ brotli: installé')"

echo ""
echo -e "${YELLOW}Prochaines étapes :${NC}"
echo ""
echo "  1. Activer l'environnement virtuel :"
echo -e "     ${GREEN}source venv/bin/activate${NC}"
echo ""
echo "  2. Placer vos données dans :"
echo -e "     ${GREEN}data/user_data/${NC}"
echo ""
echo "  3. Lancer le pipeline complet :"
echo -e "     ${GREEN}bash scripts/run_full_pipeline.sh${NC}"
echo ""

# Deactivate venv
deactivate 2>/dev/null || true

echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"

