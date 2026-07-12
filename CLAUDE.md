# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

This project was originally built for **Ubuntu 22.04 / Python 3.10**. The `venv/` directory is a Linux venv and cannot be used on Windows.

**Windows setup** (already done — use `venv_win/`):
```powershell
venv_win\Scripts\Activate.ps1
```

**Linux/Ubuntu setup** (original target):
```bash
source venv/bin/activate  # if venv exists; else: bash scripts/setup_environment.sh
```

### liboqs / oqs — Windows shim

On Windows, `liboqs-python` fails to build its native C library (requires `rc.exe` from the Windows 10 SDK, which is not installed). **`venv_win` uses a pure-Python shim instead:**

- `venv_win/Lib/site-packages/oqs/__init__.py` has been **replaced** with a compatibility shim backed by `kyber-py` (pip package `kyber-py`).
- `import oqs` works correctly; all project code that calls `oqs.KeyEncapsulation`, `get_enabled_kem_mechanisms()`, etc. runs unchanged.
- Supports: `Kyber512`, `Kyber768`, `Kyber1024`, `ML-KEM-512`, `ML-KEM-768`, `ML-KEM-1024`.
- The shim is **slower** than native liboqs but functionally identical for development and benchmarking on Windows.
- On Linux (production), the real `liboqs-python` native library is used (installed via `bash scripts/install_supercop.sh`).

## Common Commands

All commands assume the venv is activated and run from the project root.

**Scan and validate real data:**
```bash
python -m src.data.real_data_loader --validate --data-dir data/user_data
python -m src.data.real_data_loader --create-manifest --data-dir data/user_data
```

**Train the VAE** (requires images in `data/user_data/`):
```bash
python -m src.models.vae_trainer --data-dir data/user_data --out results --epochs 20
# Fast debug run:
python -m src.models.vae_trainer --data-dir data/user_data --out results --epochs 2 --max-images 200
```

**Micro-benchmarks:**
```bash
python -m src.benchmarks.micro_bench aes --output results/data/micro_aes.csv
python -m src.benchmarks.micro_bench kyber --output results/data/micro_kyber.csv
```

**Scalability benchmark** (real data, 7 size points):
```bash
python -m src.benchmarks.scalability_bench --data-dir data/user_data --out results
```

**Generate missing metrics** (when real data is insufficient for a figure):
```bash
python -m src.benchmarks.make_missing_metrics --out results/data
```

**Smoke-test individual modules** (each has a `__main__` demo):
```bash
python -m src.crypto.aes_gcm
python -m src.crypto.ml_kem
python -m src.compression.classic_compressors
```

**Full pipeline** (Linux/bash, runs everything end-to-end, 2–4 hours):
```bash
bash scripts/run_full_pipeline.sh
```

There are no automated tests (`tests/` is empty). Use the `__main__` blocks above as smoke tests.

## Architecture

### The 3-layer pipeline

```
Real file bytes
    ↓
[1] Compression  (VAE or classic compressor)
    ↓
[2] AES-256-GCM  (cryptography.hazmat — FIPS 197 + SP 800-38D)
    ↓
[3] ML-KEM-1024  (liboqs — NIST FIPS 203 / Kyber)
```

### 4 Pipeline variants (`src/pipelines/hybrid_pipeline.py`)

`HybridPipeline(pipeline_type)` selects the variant at construction:

| Type | Compression | Crypto |
|------|-------------|--------|
| `A` | VAE (neural) | AES-GCM + ML-KEM |
| `B` | None | AES-GCM + ML-KEM |
| `C` | None | AES-GCM only |
| `D` | Classic (zstd/lz4/gzip/bz2/brotli) | AES-GCM + ML-KEM |

Pipeline A requires a pre-trained `VAE` model object: `HybridPipeline('A', vae_model=vae)`.

### VAE constraints (`src/models/vae_model.py`)

- **Fixed input**: 32×32 RGB images only (`image_size=32` is hardcoded — the constructor raises if changed)
- Architecture: 4-layer ConvEncoder → (mu, logvar) → reparameterise → 4-layer ConvDecoder
- Default `latent_dim=128`; loss = MSE reconstruction + β·KL
- Trained by `src/models/vae_trainer.py`, which saves `results/models/vae_best.pt` and `vae_last.pt`

### Data flow

1. **`src/data/real_data_loader.py`** — scans `data/user_data/` recursively, classifies files (images / csv / text / binaries), computes SHA-256 checksums, writes `results/data/data_manifest.csv` and `data_checksums.csv`. **No synthetic data is ever generated** — every pipeline aborts if no real files are found.

2. **`src/models/vae_trainer.py`** — discovers images via `discover_images()`, trains VAE with Adam, plots training history to `results/figures/`.

3. **`src/benchmarks/`** — standalone CLI scripts; each writes a CSV to `results/data/`. Key outputs: `micro_aes.csv`, `micro_kyber.csv` + `kem_samples_us.csv`, `scalability.csv`.

4. **`src/visualization/`** — one script per figure (`fig03_` … `fig12_`). Each reads specific CSVs from `results/data/` and writes PDF + PNG to `results/figures/`. `make_missing_metrics.py` in `src/benchmarks/` generates the required CSVs if real benchmark runs haven't been done yet.

### KEM usage pattern

The `oqs.KeyEncapsulation` object must stay alive across keygen → decap (the secret key is held internally). Avoid calling `load_secret_key` / `import_secret_key` — the API varies across liboqs versions. The correct pattern used throughout:

```python
kem = oqs.KeyEncapsulation(alg)
pk = kem.generate_keypair()           # secret key stored internally
ct, ss1 = kem.encap_secret(pk)
ss2 = kem.decap_secret(ct)            # uses internally stored secret key
assert ss1 == ss2
```

### Results layout

```
results/
  data/        ← CSV outputs from benchmark scripts
  figures/     ← PDF + PNG figures (300 DPI) from visualization scripts
  models/      ← vae_best.pt, vae_last.pt
  tables/      ← LaTeX tables
```

### Config

`config/crypto_config.yaml` documents the NIST parameter choices (AES key/IV/tag sizes, ML-KEM security level, benchmark repetition counts). The code hardcodes these values directly; the YAML is reference documentation, not runtime config.
