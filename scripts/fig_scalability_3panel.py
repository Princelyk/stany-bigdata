#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fig_scalability_3panel.py — the anchor scalability figure for Section 5.6.

Three horizontal panels (per the JISA scalability protocol, Section 5.1):
  (a) Weak scaling    : throughput vs. log10(volume), points w/ error bars + fit
  (b) Composition     : composition-adjusted throughput vs. raw (ghost bars)
  (c) Strong scaling  : AES-GCM parallel efficiency vs. worker threads

Design follows the protocol's principles: Okabe-Ito colourblind-safe palette,
log x-axis on panel (a), error bars = std over replicates, >=9 pt labels, no
decoration. Reads only from results/data/protocol/ so it is fully reproducible.

Usage:
    venv_win\\Scripts\\python.exe scripts\\fig_scalability_3panel.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROT = ROOT / "results" / "data" / "protocol"
OUTDIR = ROOT / "results" / "figures"
OUTDIR.mkdir(parents=True, exist_ok=True)

# Okabe-Ito colourblind-safe palette
OK = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
      "vermillion": "#D55E00", "grey": "#999999", "black": "#000000"}
DS_ORDER = ["D1", "D2", "D3"]
DS_COLOR = {"D1": OK["blue"], "D2": OK["orange"], "D3": OK["green"]}
DS_MARKER = {"D1": "o", "D2": "s", "D3": "^"}

plt.rcParams.update({
    "font.size": 9, "axes.labelsize": 10, "axes.titlesize": 10,
    "legend.fontsize": 8, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.linewidth": 0.8, "lines.linewidth": 1.6, "figure.dpi": 300,
})


def main() -> None:
    weak = pd.read_csv(PROT / "weak_scaling_runs.csv")
    summ = json.load(open(PROT / "analysis_summary.json"))
    comp = pd.read_csv(PROT / "composition_adjusted_throughput.csv")
    strong = pd.read_csv(PROT / "strong_scaling_aggregate.csv")

    # per-dataset aggregates
    agg = {ds: weak[weak.dataset_id == ds] for ds in DS_ORDER}
    gb = {ds: agg[ds].processed_gb.mean() for ds in DS_ORDER}
    thr = {ds: agg[ds].t_bytes_mb_s.mean() for ds in DS_ORDER}
    err = {ds: agg[ds].t_bytes_mb_s.std() for ds in DS_ORDER}

    slope_ln = summ.get("slope_per_log_gb", 0.0)
    slope_dec = slope_ln * np.log(10)          # per decade
    intercept = summ.get("intercept", 0.0)
    r2 = summ.get("r2", float("nan"))
    cadj = dict(zip(comp.dataset_id, comp.composition_adjusted_throughput_mb_s))

    # ── panel drawers (each takes an axis + a title, so the same code renders
    #    both the combined 3-panel figure and the standalone single-panel ones) ─
    def draw_weak(ax, title):
        for ds in DS_ORDER:
            ax.errorbar(gb[ds], thr[ds], yerr=err[ds], fmt=DS_MARKER[ds],
                        color=DS_COLOR[ds], ms=8, capsize=4, elinewidth=1.3,
                        label=f"{ds} ({gb[ds]:.1f} GB)", zorder=3)
        xs = np.linspace(np.log10(min(gb.values())) - 0.1,
                         np.log10(max(gb.values())) + 0.1, 100)
        ys = intercept + slope_ln * (xs * np.log(10))   # summary fit is in ln(V)
        ax.plot(10 ** xs, ys, "--", color=OK["grey"], lw=1.3, zorder=1, label="linear fit (n.s.)")
        ax.set_xscale("log")
        ax.set_xlabel("Cumulative volume (GB, log scale)")
        ax.set_ylabel("Throughput $T_{bytes}$ (MB/s)")
        ax.set_title(title)
        ax.set_ylim(bottom=0)
        ax.grid(True, which="both", ls=":", lw=0.4, color=OK["grey"], alpha=0.5)
        ax.legend(frameon=False, loc="upper right")
        ax.text(0.03, 0.05, f"$\\beta$={slope_dec:.0f} MB/s/decade\n$R^2$={r2:.2f}, CI incl. 0",
                transform=ax.transAxes, fontsize=8, va="bottom", color=OK["black"])

    def draw_composition(ax, title):
        x = np.arange(len(DS_ORDER))
        raw = [thr[ds] for ds in DS_ORDER]
        adj = [cadj.get(ds, np.nan) for ds in DS_ORDER]
        ax.bar(x, raw, width=0.55, color=OK["grey"], alpha=0.35, label="raw $T_{bytes}$", zorder=1)
        ax.bar(x, adj, width=0.30, color=[DS_COLOR[d] for d in DS_ORDER],
               label="composition-adjusted $T_{adj}$", zorder=2)
        ax.set_xticks(x)
        ax.set_xticklabels(DS_ORDER)
        ax.set_ylabel("Throughput (MB/s)")
        ax.set_xlabel("Dataset")
        ax.set_title(title)
        ax.grid(True, axis="y", ls=":", lw=0.4, color=OK["grey"], alpha=0.5)
        ax.legend(frameon=False, loc="upper center")

    def draw_strong(ax, title):
        ecol = "efficiency_mean" if "efficiency_mean" in strong else "parallel_efficiency_mean"
        estd = "efficiency_std" if "efficiency_std" in strong else None
        t = strong.threads.values
        e = strong[ecol].values
        yerr = strong[estd].values if estd and estd in strong else None
        ax.axhline(1.0, ls="--", color=OK["grey"], lw=1.2, label="ideal $E=1$")
        ax.errorbar(t, e, yerr=yerr, fmt="-o", color=OK["vermillion"], ms=7,
                    capsize=4, elinewidth=1.2, label="measured (AES-GCM)", zorder=3)
        ax.set_xscale("log", base=2)
        ax.set_xticks(t)
        ax.set_xticklabels([str(int(v)) for v in t])
        ax.set_xlabel("AES-GCM worker threads")
        ax.set_ylabel("Parallel efficiency $E(T)$")
        ax.set_title(title)
        ax.set_ylim(0, 1.08)
        ax.grid(True, which="both", ls=":", lw=0.4, color=OK["grey"], alpha=0.5)
        ax.legend(frameon=False, loc="upper right")

    def savefig(fig, stem):
        for ext in ("png", "pdf"):
            out = OUTDIR / f"{stem}.{ext}"
            fig.savefig(out, bbox_inches="tight")
        print(f"OK: wrote {OUTDIR / (stem + '.png')}")

    # combined 3-panel (kept for reference / backwards compatibility)
    fig, ax = plt.subplots(1, 3, figsize=(11.0, 3.5))
    draw_weak(ax[0], "(a) Weak scaling")
    draw_composition(ax[1], "(b) Composition effect")
    draw_strong(ax[2], "(c) Strong scaling (D2)")
    fig.tight_layout()
    savefig(fig, "fig_scalability_3panel")
    plt.close(fig)

    # standalone single-panel figures (one plot per figure)
    for stem, drawer, title in [
        ("fig_scalability_a_weak", draw_weak, "Weak scaling"),
        ("fig_scalability_b_composition", draw_composition, "Composition effect"),
        ("fig_scalability_c_strong", draw_strong, "Strong scaling (D2)"),
    ]:
        f1, a1 = plt.subplots(1, 1, figsize=(4.2, 3.6))
        drawer(a1, title)
        f1.tight_layout()
        savefig(f1, stem)
        plt.close(f1)


if __name__ == "__main__":
    main()
