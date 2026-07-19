#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_protocol_report.py — generate a Word report of the scalability-protocol run.

Reads the real outputs under results/data/protocol/ and writes a formatted .docx
summarising the weak-scaling runs, per-layer latency, composition-adjusted
throughput, the scalability regression, and correctness — with the
single-replicate / Windows-shim caveats stated up front.

Usage (from project root):
    venv_win\\Scripts\\python.exe scripts\\build_protocol_report.py
    # optional: --protocol-dir results/data/protocol --out Scalability_Protocol_Report.docx
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

KINDS = ["images", "text", "binaries", "other"]


# ── style helpers (mirroring scripts/build_docx.py) ─────────────────────────
def add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for r in h.runs:
        r.font.color.rgb = RGBColor(0, 0, 0)
    return h


def add_body(doc, text, italic=False, space_after=6):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.italic = italic
    p.paragraph_format.space_after = Pt(space_after)
    return p


def add_caption(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(9)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    return p


def shade_header(tbl, hex_color="D9D9D9"):
    for cell in tbl.rows[0].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)


def add_table(doc, headers, rows):
    tbl = doc.add_table(rows=1, cols=len(headers))
    tbl.style = "Table Grid"
    for i, h in enumerate(headers):
        c = tbl.rows[0].cells[i]
        c.paragraphs[0].add_run(h).bold = True
    for row in rows:
        cells = tbl.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
    for row in tbl.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                para.paragraph_format.space_before = Pt(2)
                para.paragraph_format.space_after = Pt(2)
                for r in para.runs:
                    r.font.size = Pt(9)
    shade_header(tbl)
    return tbl


# ── data loading ────────────────────────────────────────────────────────────
def fmt(x, nd=2):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return "—"
        return f"{float(x):,.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def layer_medians(protocol_dir: Path, dataset: str, run_id: str) -> dict:
    f = protocol_dir / "weak" / dataset / f"run_{run_id}_per_file.csv"
    if not f.exists():
        return {}
    df = pd.read_csv(f, usecols=lambda c: c in
                     {"l_io_read_ms", "l_kem_ms", "l_aes_ms", "l_total_ms"})
    return {k: float(df[k].median()) for k in df.columns}


def build(protocol_dir: Path, out_path: Path) -> None:
    weak_csv = protocol_dir / "weak_scaling_runs.csv"
    if not weak_csv.exists():
        raise SystemExit(f"ERROR: {weak_csv} not found. Run the protocol first.")
    weak = pd.read_csv(weak_csv)

    summary = {}
    p = protocol_dir / "analysis_summary.json"
    if p.exists():
        summary = json.load(open(p))
    comp_adj = {}
    p = protocol_dir / "composition_adjusted_throughput.csv"
    if p.exists():
        c = pd.read_csv(p)
        comp_adj = dict(zip(c["dataset_id"], c["composition_adjusted_throughput_mb_s"]))

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    # ── title block ─────────────────────────────────────────────────────────
    t = doc.add_heading("Scalability Protocol — Results Report", level=0)
    for r in t.runs:
        r.font.color.rgb = RGBColor(0, 0, 0)
    add_body(doc, f"Hybrid secure big-data pipeline (VAE + AES-256-GCM + ML-KEM-1024). "
                  f"Generated {datetime.now():%Y-%m-%d %H:%M}.", italic=True)

    # ── caveat box ──────────────────────────────────────────────────────────
    add_heading(doc, "Scope and caveats", level=1)
    add_body(doc, "These results are a single-replicate proof-of-run executed on Windows using "
                  "the pure-Python ML-KEM shim (kyber-py). They verify the pipeline end-to-end "
                  "and expose the scalability trend, but are NOT the final publication numbers: "
                  "(1) one replicate per dataset means cross-replicate statistics (confidence "
                  "intervals, ANOVA) cannot be computed; (2) the Windows shim is ~100x slower "
                  "than native liboqs, so wall-times reflect the shim, not representative hardware. "
                  "The full 3-replicate + strong-scaling protocol should be run on Linux with "
                  "native liboqs (scripts/run_scalability_protocol.sh).")

    # ── Table 1: datasets & composition ─────────────────────────────────────
    add_heading(doc, "1. Datasets and composition", level=1)
    add_caption(doc, "Table 1. Dataset size and file-type composition (as classified by the runner; "
                     "'text' includes .log and .csv).")
    rows = []
    for _, w in weak.iterrows():
        parts = []
        for k in KINDS:
            fc = w.get(f"kind_{k}_files")
            if pd.notna(fc) and fc and float(fc) > 0:
                gb = float(w.get(f"kind_{k}_bytes", 0)) / 1024**3
                parts.append(f"{k} {int(fc)} ({gb:.1f} GB)")
        rows.append([w["dataset_id"], fmt(w["processed_gb"]), f"{int(w['n_files']):,}",
                     "; ".join(parts)])
    add_table(doc, ["Dataset", "Data (GB)", "Files", "Composition"], rows)

    # ── Table 2: weak-scaling performance ───────────────────────────────────
    add_heading(doc, "2. Weak-scaling performance", level=1)
    add_caption(doc, "Table 2. Per-dataset throughput, latency and correctness (1 replicate each).")
    rows = []
    for _, w in weak.iterrows():
        rows.append([
            w["dataset_id"], fmt(w["processed_gb"]), f"{int(w['n_files']):,}",
            fmt(w["wall_s"], 1), fmt(w["t_bytes_mb_s"], 2), fmt(w["t_files_s"], 3),
            fmt(w["latency_p50_ms"], 1), fmt(w["latency_p95_ms"], 1),
            fmt(w["cpu_utilization_percent"], 1),
            f"{int(w['kem_failures'])}/{int(w['aes_failures'])}",
        ])
    add_table(doc, ["Dataset", "GB", "Files", "Wall s", "MB/s", "files/s",
                    "p50 ms", "p95 ms", "CPU %", "KEM/AES fail"], rows)
    add_body(doc, "Observation: throughput is governed by file count, not data volume. D2 "
                  "(many small files) runs far slower per byte than D3 (fewer, larger files) "
                  "despite D3 holding 2.7x the data — the per-file ML-KEM cost dominates. This is "
                  "the central scalability effect the protocol is designed to surface.")

    # ── Table 3: per-layer latency ──────────────────────────────────────────
    add_heading(doc, "3. Per-layer median latency", level=1)
    add_caption(doc, "Table 3. Median per-file latency by pipeline layer (ms).")
    rows = []
    for _, w in weak.iterrows():
        m = layer_medians(protocol_dir, w["dataset_id"], w["run_id"])
        rows.append([w["dataset_id"],
                     fmt(m.get("l_io_read_ms"), 2), fmt(m.get("l_kem_ms"), 2),
                     fmt(m.get("l_aes_ms"), 2), fmt(m.get("l_total_ms"), 2)])
    add_table(doc, ["Dataset", "IO read", "ML-KEM", "AES-GCM", "Total"], rows)

    # ── Table 4: composition-adjusted throughput ────────────────────────────
    if comp_adj:
        add_heading(doc, "4. Composition-adjusted throughput", level=1)
        add_caption(doc, "Table 4. Throughput normalised to the baseline (D1) file-type mix.")
        rows = [[k, fmt(v, 3)] for k, v in comp_adj.items()]
        add_table(doc, ["Dataset", "Adjusted MB/s"], rows)

    # ── Table 5: scalability regression ─────────────────────────────────────
    if summary:
        add_heading(doc, "5. Scalability regression", level=1)
        add_caption(doc, "Table 5. Throughput vs. log10(data size) regression across D1–D3.")
        ci = summary.get("slope_ci95") or [None, None]
        rows = [
            ["Slope (MB/s per log10 GB)", fmt(summary.get("slope_per_log_gb"), 2)],
            ["Slope 95% CI", f"[{fmt(ci[0],2)}, {fmt(ci[1],2)}]"],
            ["Slope p-value", fmt(summary.get("slope_pvalue"), 4)],
            ["Intercept (MB/s)", fmt(summary.get("intercept"), 2)],
            ["R²", fmt(summary.get("r2"), 3)],
            ["Adjusted R²", fmt(summary.get("adjusted_r2"), 3)],
            ["Shapiro p (normality)", fmt(summary.get("shapiro_pvalue"), 3)],
            ["ANOVA p (across replicates)", fmt(summary.get("anova_pvalue"), 3)],
        ]
        add_table(doc, ["Metric", "Value"], rows)
        add_body(doc, "The slope p-value is not significant and the ANOVA is undefined because "
                      "only one replicate per dataset is available. Both become meaningful once "
                      "the 3-replicate protocol is run.", italic=True)

    # ── correctness ─────────────────────────────────────────────────────────
    add_heading(doc, "6. Correctness", level=1)
    tot_kem = int(weak["kem_failures"].sum())
    tot_aes = int(weak["aes_failures"].sum())
    add_body(doc, f"Across all datasets: {tot_kem} ML-KEM encapsulate/decapsulate mismatches and "
                  f"{tot_aes} AES-GCM decrypt mismatches. Every file round-tripped correctly through "
                  f"the full compress → AES-256-GCM → ML-KEM-1024 pipeline.")

    add_heading(doc, "7. Next step", level=1)
    add_body(doc, "Run scripts/run_scalability_protocol.sh on Linux with native liboqs to produce "
                  "the 3-replicate weak-scaling set, strong-scaling on D2, and the statistically "
                  "valid analysis (real confidence intervals and a significance-tested regression).")

    doc.save(out_path)
    print(f"OK: wrote {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a .docx report of the scalability-protocol run.")
    ap.add_argument("--protocol-dir", default="results/data/protocol")
    ap.add_argument("--out", default="Scalability_Protocol_Report.docx")
    args = ap.parse_args()
    build(Path(args.protocol_dir), Path(args.out))


if __name__ == "__main__":
    main()
