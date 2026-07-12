#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

try:
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import het_breuschpagan, linear_reset
    from statsmodels.stats.multicomp import pairwise_tukeyhsd
except Exception:  # pragma: no cover - optional dependency
    sm = None
    het_breuschpagan = None
    linear_reset = None
    pairwise_tukeyhsd = None


def bootstrap_slope_ci(x: np.ndarray, y: np.ndarray, n_boot: int = 10_000, alpha: float = 0.05) -> tuple[float, float]:
    rng = np.random.default_rng(42)
    n = len(x)
    if n < 2:
        return float("nan"), float("nan")
    slopes = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        xb = x[idx]
        yb = y[idx]
        if np.unique(xb).size < 2:
            slopes[i] = np.nan
            continue
        slopes[i] = np.polyfit(xb, yb, 1)[0]
    slopes = slopes[np.isfinite(slopes)]
    if slopes.size == 0:
        return float("nan"), float("nan")
    lo = float(np.percentile(slopes, 100 * (alpha / 2.0)))
    hi = float(np.percentile(slopes, 100 * (1.0 - alpha / 2.0)))
    return lo, hi


def find_latest_per_file(out_root: Path) -> pd.DataFrame:
    weak_dir = out_root / "weak"
    rows: List[pd.DataFrame] = []
    if not weak_dir.exists():
        return pd.DataFrame()
    for dataset_dir in weak_dir.iterdir():
        if not dataset_dir.is_dir():
            continue
        files = sorted(dataset_dir.glob("run_*_per_file.csv"))
        if not files:
            continue
        latest = files[-1]
        df = pd.read_csv(latest)
        rows.append(df)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="python -m src.benchmarks.scalability_protocol_analyze",
        description="Analyze weak/strong scaling outputs from protocol runs.",
    )
    ap.add_argument("--out", default="results/data/protocol", help="Protocol output root")
    ap.add_argument(
        "--baseline-dataset",
        default="D1",
        help="Baseline dataset id for composition-adjusted throughput",
    )
    args = ap.parse_args()

    out_root = Path(args.out)
    weak_csv = out_root / "weak_scaling_runs.csv"
    if not weak_csv.exists():
        raise SystemExit(f"ERROR: not found: {weak_csv}")

    weak = pd.read_csv(weak_csv)
    if weak.empty:
        raise SystemExit("ERROR: weak_scaling_runs.csv is empty")

    weak["log_processed_gb"] = np.log(np.maximum(weak["processed_gb"].astype(float), 1e-9))

    x = weak["log_processed_gb"].to_numpy(dtype=float)
    y = weak["t_bytes_mb_s"].to_numpy(dtype=float)

    slope = float("nan")
    intercept = float("nan")
    r2 = float("nan")
    adj_r2 = float("nan")
    slope_pvalue = float("nan")
    shapiro_p = float("nan")
    bp_p = float("nan")
    reset_p = float("nan")

    if len(weak) >= 2 and np.unique(x).size >= 2:
        reg = stats.linregress(x, y)
        slope = float(reg.slope)
        intercept = float(reg.intercept)
        r2 = float(reg.rvalue ** 2)
        slope_pvalue = float(reg.pvalue)
        n = len(weak)
        p = 1
        adj_r2 = float(1 - (1 - r2) * ((n - 1) / max(n - p - 1, 1)))

        residuals = y - (slope * x + intercept)
        if len(residuals) >= 3:
            shapiro_p = float(stats.shapiro(residuals).pvalue)

        if sm is not None and het_breuschpagan is not None and linear_reset is not None:
            X = sm.add_constant(x)
            model = sm.OLS(y, X).fit()
            try:
                bp = het_breuschpagan(model.resid, model.model.exog)
                bp_p = float(bp[1])
            except Exception:
                bp_p = float("nan")
            try:
                rst = linear_reset(model, power=2, use_f=True)
                reset_p = float(rst.pvalue)
            except Exception:
                reset_p = float("nan")

    slope_ci_lo, slope_ci_hi = bootstrap_slope_ci(x, y)

    anova_p = float("nan")
    tukey_rows: List[Dict] = []
    grouped = [g["t_bytes_mb_s"].to_numpy(dtype=float) for _, g in weak.groupby("dataset_id")]
    if len(grouped) >= 2 and all(len(g) > 0 for g in grouped):
        anova_p = float(stats.f_oneway(*grouped).pvalue)

        if pairwise_tukeyhsd is not None:
            tk = pairwise_tukeyhsd(endog=weak["t_bytes_mb_s"], groups=weak["dataset_id"], alpha=0.05)
            table = tk.summary()
            for row in table.data[1:]:
                tukey_rows.append(
                    {
                        "group1": row[0],
                        "group2": row[1],
                        "meandiff": float(row[2]),
                        "p_adj": float(row[3]),
                        "lower": float(row[4]),
                        "upper": float(row[5]),
                        "reject": bool(row[6]),
                    }
                )

    ds_summary = (
        weak.groupby("dataset_id", as_index=False)
        .agg(
            runs=("run_id", "nunique"),
            processed_gb_mean=("processed_gb", "mean"),
            throughput_mb_s_mean=("t_bytes_mb_s", "mean"),
            throughput_mb_s_std=("t_bytes_mb_s", "std"),
            latency_p95_ms_mean=("latency_p95_ms", "mean"),
            rss_peak_mb_mean=("rss_peak_mb", "mean"),
            cpu_utilization_percent_mean=("cpu_utilization_percent", "mean"),
        )
        .sort_values("dataset_id")
    )

    per_file = find_latest_per_file(out_root)
    comp_adj = pd.DataFrame()
    if not per_file.empty:
        by_kind = (
            per_file.groupby(["dataset_id", "kind"], as_index=False)
            .agg(
                kind_bytes=("payload_bytes_processed", "sum"),
                kind_total_ms=("l_total_ms", "sum"),
            )
        )
        by_kind["kind_throughput_mb_s"] = (
            (by_kind["kind_bytes"] / (1024 ** 2))
            / np.maximum(by_kind["kind_total_ms"] / 1000.0, 1e-9)
        )

        base = by_kind[by_kind["dataset_id"] == args.baseline_dataset].copy()
        if not base.empty:
            total_base = float(base["kind_bytes"].sum())
            base["baseline_fraction"] = base["kind_bytes"] / max(total_base, 1e-9)

            merged = by_kind.merge(
                base[["kind", "baseline_fraction"]],
                on="kind",
                how="left",
            )
            merged["baseline_fraction"] = merged["baseline_fraction"].fillna(0.0)
            merged["weighted"] = merged["kind_throughput_mb_s"] * merged["baseline_fraction"]
            comp_adj = (
                merged.groupby("dataset_id", as_index=False)
                .agg(composition_adjusted_throughput_mb_s=("weighted", "sum"))
                .sort_values("dataset_id")
            )

    strong_csv = out_root / "strong_scaling_runs.csv"
    strong_agg = pd.DataFrame()
    if strong_csv.exists():
        strong = pd.read_csv(strong_csv)
        strong_agg = (
            strong.groupby("threads", as_index=False)
            .agg(
                throughput_mb_s_mean=("throughput_mb_s", "mean"),
                throughput_mb_s_std=("throughput_mb_s", "std"),
                efficiency_mean=("parallel_efficiency", "mean"),
                efficiency_std=("parallel_efficiency", "std"),
            )
            .sort_values("threads")
        )

    analysis = {
        "n_runs": int(len(weak)),
        "datasets": sorted(weak["dataset_id"].astype(str).unique().tolist()),
        "slope_per_log_gb": slope,
        "slope_ci95": [slope_ci_lo, slope_ci_hi],
        "slope_pvalue": slope_pvalue,
        "intercept": intercept,
        "r2": r2,
        "adjusted_r2": adj_r2,
        "breusch_pagan_pvalue": bp_p,
        "ramsey_reset_pvalue": reset_p,
        "shapiro_pvalue": shapiro_p,
        "anova_pvalue": anova_p,
        "notes": {
            "diagnostics_require_statsmodels": sm is not None,
            "tukey_available": pairwise_tukeyhsd is not None,
            "baseline_dataset_for_composition_adjustment": args.baseline_dataset,
        },
    }

    if tukey_rows:
        pd.DataFrame(tukey_rows).to_csv(out_root / "tukey_hsd.csv", index=False)

    ds_summary.to_csv(out_root / "dataset_summary.csv", index=False)
    if not comp_adj.empty:
        comp_adj.to_csv(out_root / "composition_adjusted_throughput.csv", index=False)
    if not strong_agg.empty:
        strong_agg.to_csv(out_root / "strong_scaling_aggregate.csv", index=False)

    with (out_root / "analysis_summary.json").open("w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)

    print(f"OK: wrote {out_root / 'analysis_summary.json'}")
    print(f"OK: wrote {out_root / 'dataset_summary.csv'}")
    if not comp_adj.empty:
        print(f"OK: wrote {out_root / 'composition_adjusted_throughput.csv'}")
    if (out_root / "tukey_hsd.csv").exists():
        print(f"OK: wrote {out_root / 'tukey_hsd.csv'}")
    if not strong_agg.empty:
        print(f"OK: wrote {out_root / 'strong_scaling_aggregate.csv'}")


if __name__ == "__main__":
    main()
