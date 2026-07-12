#!/bin/bash
# =============================================================================
# Script d'installation SUPERCOC + NIST Standards
# Conforme aux normes de reproductibilité académique
# =============================================================================

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SUPERCOP_DIR="${PROJECT_ROOT}/data/supercop"
NIST_DIR="${PROJECT_ROOT}/data/nist_vectors"

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# =============================================================================
# Vérification des prérequis système
# =============================================================================
check_dependencies() {
    log_info "Vérification des dépendances système..."
    
    local missing_deps=()
    
    # Compilateurs et outils de build
    for cmd in gcc g++ make cmake wget unzip git; do
        if ! command -v $cmd &> /dev/null; then
            missing_deps+=($cmd)
        fi
    done
    
    # Bibliothèques de développement
    for lib in openssl-dev libssl-dev python3-dev; do
        if ! dpkg -l | grep -q $lib 2>/dev/null; then
            missing_deps+=($lib)
        fi
    done
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "Dépendances manquantes: ${missing_deps[*]}"
        log_info "Installation automatique..."
        sudo apt-get update
        sudo apt-get install -y build-essential cmake wget unzip git \
                                libssl-dev python3-dev python3-pip
        log_success "Dépendances installées"
    else
        log_success "Toutes les dépendances sont présentes"
    fi
}

# =============================================================================
# Installation de liboqs (Open Quantum Safe)
# Implémentations NIST-conformes de ML-KEM (Kyber)
# =============================================================================
install_liboqs() {
    log_info "Installation de liboqs (ML-KEM/Kyber conforme NIST FIPS 203)..."
    
    cd /tmp
    
    # Clone du dépôt officiel
    if [ -d "liboqs" ]; then
        rm -rf liboqs
    fi
    
    git clone --depth 1 https://github.com/open-quantum-safe/liboqs.git
    cd liboqs
    
    # Configuration avec support complet
    mkdir -p build
    cd build
    cmake -DCMAKE_INSTALL_PREFIX=/usr/local \
          -DOQS_USE_OPENSSL=ON \
          -DBUILD_SHARED_LIBS=ON \
          -DOQS_BUILD_ONLY_LIB=OFF \
          ..
    
    # Compilation (utilise tous les cœurs disponibles)
    make -j$(nproc)
    
    # Installation (nécessite sudo)
    sudo make install
    sudo ldconfig
    
    log_success "liboqs installé avec succès"
    
    # Vérification
    if ldconfig -p | grep -q liboqs; then
        log_success "Bibliothèque liboqs détectée dans le système"
    else
        log_warn "liboqs installé mais non détecté par ldconfig"
    fi
    
    # Installation du wrapper Python
    log_info "Installation du wrapper Python liboqs-python..."
    pip install liboqs-python
    log_success "liboqs-python installé"
    
    # Cleanup
    cd /tmp
    rm -rf liboqs
}

# =============================================================================
# Téléchargement des vecteurs de test NIST
# =============================================================================
download_nist_vectors() {
    log_info "Téléchargement des vecteurs de test NIST..."
    
    mkdir -p "${NIST_DIR}"
    cd "${NIST_DIR}"
    
    # NIST AES Test Vectors (FIPS 197)
    log_info "  → AES Test Vectors (FIPS 197)..."
    if [ ! -f "aes_vectors.zip" ]; then
        wget -q --show-progress \
            https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/aes/aesmmt.zip \
            -O aes_vectors.zip
        unzip -q aes_vectors.zip -d aes/
        log_success "Vecteurs AES téléchargés"
    else
        log_warn "Vecteurs AES déjà présents"
    fi
    
    # NIST GCM Test Vectors (SP 800-38D)
    log_info "  → GCM Test Vectors (SP 800-38D)..."
    if [ ! -f "gcm_vectors.zip" ]; then
        wget -q --show-progress \
            https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/mac/gcmtestvectors.zip \
            -O gcm_vectors.zip
        unzip -q gcm_vectors.zip -d gcm/
        log_success "Vecteurs GCM téléchargés"
    else
        log_warn "Vecteurs GCM déjà présents"
    fi
    
    # NIST ML-KEM/Kyber reference (FIPS 203)
    log_info "  → ML-KEM Reference Implementation (FIPS 203)..."
    if [ ! -d "ml-kem" ]; then
        git clone --depth 1 https://github.com/pq-crystals/kyber.git ml-kem
        log_success "Référence ML-KEM téléchargée"
    else
        log_warn "ML-KEM déjà présent"
    fi
    
    log_success "Tous les vecteurs NIST téléchargés"
}

# =============================================================================
# Installation de SUPERCOP (optionnel, pour benchmarks supplémentaires)
# =============================================================================
install_supercop() {
    log_info "Installation de SUPERCOP..."
    log_warn "SUPERCOP est très volumineux (~2GB) et peut prendre 1-2 heures"
    read -p "Voulez-vous installer SUPERCOP ? [y/N] " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Installation SUPERCOP ignorée"
        return 0
    fi
    
    mkdir -p "${SUPERCOP_DIR}"
    cd "${SUPERCOP_DIR}"
    
    # Téléchargement de la dernière version
    log_info "Téléchargement de SUPERCOP..."
    if [ ! -f "supercop.tar.gz" ]; then
        wget -q --show-progress \
            https://bench.cr.yp.to/supercop/supercop-20231215.tar.xz \
            -O supercop.tar.xz
        tar xf supercop.tar.xz
        mv supercop-* supercop
        log_success "SUPERCOP téléchargé"
    fi
    
    cd supercop
    
    # Compilation (très long)
    log_info "Compilation SUPERCOP (peut prendre 1-2 heures)..."
    ./do
    
    log_success "SUPERCOP compilé avec succès"
}

# =============================================================================
# Création d'un fichier de configuration
# =============================================================================
create_config() {
    log_info "Création du fichier de configuration..."
    
    cat > "${PROJECT_ROOT}/config/crypto_config.yaml" <<'EOF'
# =============================================================================
# Configuration des implémentations cryptographiques
# Conforme NIST standards
# =============================================================================

aes:
  mode: GCM
  key_size: 256  # bits
  iv_size: 96    # bits (recommandé NIST SP 800-38D)
  tag_size: 128  # bits
  standard: "NIST FIPS 197 + SP 800-38D"
  urls:
    - "https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.197.pdf"
    - "https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf"

ml_kem:
  algorithm: Kyber
  security_level: 1024  # ML-KEM-1024
  standard: "NIST FIPS 203"
  key_sizes:
    public_key: 1568   # bytes
    secret_key: 3168   # bytes
    ciphertext: 1568   # bytes
  urls:
    - "https://csrc.nist.gov/pubs/fips/203/final"
    - "https://pq-crystals.org/kyber/"

implementations:
  aes_gcm: "cryptography.hazmat"
  ml_kem: "liboqs"
  
test_vectors:
  aes: "data/nist_vectors/aes/"
  gcm: "data/nist_vectors/gcm/"
  ml_kem: "data/nist_vectors/ml-kem/"
EOF

    log_success "Configuration créée: config/crypto_config.yaml"
}

# =============================================================================
# Vérification finale
# =============================================================================
verify_installation() {
    log_info "Vérification de l'installation..."
    
    # Test Python
    python3 << 'PYEOF'
import sys
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    print("✓ cryptography (AES-GCM) OK")
except ImportError as e:
    print(f"✗ cryptography manquant: {e}")
    sys.exit(1)

try:
    import oqs
    print("✓ liboqs (ML-KEM) OK")
    # Test de création d'un KEM
    kem = oqs.KeyEncapsulation("Kyber1024")
    print(f"  → Kyber1024 disponible")
    print(f"  → Public key: {kem.details['length_public_key']} bytes")
    print(f"  → Secret key: {kem.details['length_secret_key']} bytes")
except ImportError as e:
    print(f"✗ liboqs manquant: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Erreur liboqs: {e}")
    sys.exit(1)

print("\n✓ Toutes les dépendances cryptographiques sont fonctionnelles")
PYEOF

    if [ $? -eq 0 ]; then
        log_success "Installation validée avec succès"
    else
        log_error "Problèmes détectés dans l'installation"
        exit 1
    fi
}

# =============================================================================
# Main execution
# =============================================================================
main() {
    echo "============================================================================="
    echo "  Installation NIST Standards + liboqs + SUPERCOP"
    echo "  Projet: Hybrid Secure Big Data"
    echo "============================================================================="
    echo
    
    check_dependencies
    install_liboqs
    download_nist_vectors
    install_supercop  # optionnel
    create_config
    verify_installation
    
    echo
    log_success "Installation terminée avec succès!"
    echo
    echo "Prochaines étapes:"
    echo "  1. Activez l'environnement: source venv/bin/activate"
    echo "  2. Placez vos données: cp /chemin/vers/données/* data/user_data/"
    echo "  3. Lancez le pipeline: bash scripts/run_full_pipeline.sh"
    echo
}

main "$@"
