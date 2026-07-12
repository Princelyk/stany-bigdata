# Conformité aux standards NIST

## Standards implémentés

### AES-256-GCM
- **Standard**: NIST FIPS 197 + SP 800-38D
- **Clé**: 256 bits
- **IV**: 96 bits (recommandation NIST)
- **Tag**: 128 bits
- **Implémentation**: cryptography.hazmat
- **URLs**:
  - https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.197.pdf
  - https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf

### ML-KEM-1024 (CRYSTALS-Kyber)
- **Standard**: NIST FIPS 203
- **Niveau de sécurité**: NIST Level 5 (équivalent AES-256)
- **Tailles**:
  - Clé publique: 1568 bytes
  - Clé secrète: 3168 bytes
  - Ciphertext: 1568 bytes
- **Implémentation**: liboqs (Open Quantum Safe)
- **URLs**:
  - https://csrc.nist.gov/pubs/fips/203/final
  - https://pq-crystals.org/kyber/

## Vecteurs de test

Tous les vecteurs de test NIST sont téléchargés automatiquement :
- `data/nist_vectors/aes/` - Tests AES
- `data/nist_vectors/gcm/` - Tests GCM
- `data/nist_vectors/ml-kem/` - Référence ML-KEM

## Tests de conformité

Lancer les tests :
```bash
python -m src.security.nist_tests
```

## Conformité journaux Q1

- Figures: 300 DPI, PDF vectoriel
- Tableaux: LaTeX format IEEE/ACM
- Répétitions: ≥ 10 par configuration
- Statistiques: Médiane + IQR
