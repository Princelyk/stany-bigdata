# Scalability Protocol Execution Guide

This guide turns the JISA scalability protocol into executable steps for this repository.

## 1) Prerequisites

- Activate the project environment.
- Ensure `import oqs` works in the selected environment.
- Place datasets in dedicated folders:
  - `data/user_data/D1`
  - `data/user_data/D2`
  - `data/user_data/D3`

## 2) Optional dry run (sanity check)

```powershell
python -m src.benchmarks.scalability_protocol_run --dataset-id D1 --data-dir data/user_data/D1 --out results/data/protocol --run-id dryrun --max-files 25 --max-bytes-per-file 1048576
```

## 3) Weak-scaling runs (3 runs per dataset)

Run each dataset three times on separate days as requested by the protocol.

```powershell
python -m src.benchmarks.scalability_protocol_run --dataset-id D1 --data-dir data/user_data/D1 --out results/data/protocol --run-id D1_r1
python -m src.benchmarks.scalability_protocol_run --dataset-id D1 --data-dir data/user_data/D1 --out results/data/protocol --run-id D1_r2
python -m src.benchmarks.scalability_protocol_run --dataset-id D1 --data-dir data/user_data/D1 --out results/data/protocol --run-id D1_r3

python -m src.benchmarks.scalability_protocol_run --dataset-id D2 --data-dir data/user_data/D2 --out results/data/protocol --run-id D2_r1
python -m src.benchmarks.scalability_protocol_run --dataset-id D2 --data-dir data/user_data/D2 --out results/data/protocol --run-id D2_r2
python -m src.benchmarks.scalability_protocol_run --dataset-id D2 --data-dir data/user_data/D2 --out results/data/protocol --run-id D2_r3

python -m src.benchmarks.scalability_protocol_run --dataset-id D3 --data-dir data/user_data/D3 --out results/data/protocol --run-id D3_r1
python -m src.benchmarks.scalability_protocol_run --dataset-id D3 --data-dir data/user_data/D3 --out results/data/protocol --run-id D3_r2
python -m src.benchmarks.scalability_protocol_run --dataset-id D3 --data-dir data/user_data/D3 --out results/data/protocol --run-id D3_r3
```

## 4) Strong scaling (AES workers on D2)

```powershell
python -m src.benchmarks.scalability_protocol_strong --dataset-id D2 --data-dir data/user_data/D2 --out results/data/protocol --threads 1,2,4,8,16 --repetitions 3
```

## 5) Statistical analysis and aggregates

```powershell
python -m src.benchmarks.scalability_protocol_analyze --out results/data/protocol --baseline-dataset D1
```

## 6) One-command orchestration

Use the provided PowerShell script when datasets are ready:

```powershell
scripts/run_scalability_protocol.ps1 -RunStrongScaling
```

Dry-run mode (prints commands only):

```powershell
scripts/run_scalability_protocol.ps1 -DryRun -RunStrongScaling
```

## 7) Output files

Key outputs are written under `results/data/protocol`:

- `weak_scaling_runs.csv`: one row per weak-scaling run
- `weak/<dataset>/run_*_per_file.csv`: raw per-file stage timings
- `weak/<dataset>/run_*_size_buckets.csv`: median + IQR by size bucket
- `strong_scaling_runs.csv`: raw strong-scaling run rows
- `analysis_summary.json`: slope/CI/tests summary
- `dataset_summary.csv`: dataset-level aggregate table
- `composition_adjusted_throughput.csv`: composition-normalized throughput
- `strong_scaling_aggregate.csv`: E(T) aggregate table
