#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
real_data_loader.py

- Scan + inventaire "REAL DATA ONLY"
- Checksums CSV
- Manifest CSV pour les benchmarks
- Interface CLI propre (argparse)

Exemples:
  python -m src.data.real_data_loader --help
  python -m src.data.real_data_loader --validate --data-dir data/user_data_big
  python -m src.data.real_data_loader --create-manifest --data-dir data/user_data_big
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
CSV_EXT = {".csv"}
TEXT_EXT = {".txt", ".log", ".json", ".xml", ".yaml", ".yml"}


def _human_gb(n_bytes: int) -> float:
    return n_bytes / (1024 ** 3)


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(block_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def scan_data_dir(data_dir: str, max_files: int = 0) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    root = Path(data_dir)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"ERROR: data dir not found: {data_dir}")

    files: List[Path] = []
    for p in root.rglob("*"):
        if p.is_file():
            files.append(p)

    files = sorted(files)
    if max_files and max_files > 0:
        files = files[:max_files]

    rows = []
    stats: Dict[str, Dict[str, float]] = {
        "images": {"count": 0, "gb": 0.0},
        "binaries": {"count": 0, "gb": 0.0},
        "csv": {"count": 0, "gb": 0.0},
        "text": {"count": 0, "gb": 0.0},
        "other": {"count": 0, "gb": 0.0},
    }

    total_bytes = 0
    for fp in files:
        size = fp.stat().st_size
        total_bytes += size
        ext = fp.suffix.lower()

        if ext in IMAGE_EXT:
            kind = "images"
        elif ext in CSV_EXT:
            kind = "csv"
        elif ext in TEXT_EXT:
            kind = "text"
        else:
            kind = "binaries"

        stats[kind]["count"] += 1
        stats[kind]["gb"] += _human_gb(size)

        rows.append(
            {
                "path": str(fp),
                "relpath": str(fp.relative_to(root)),
                "ext": ext,
                "kind": kind,
                "size_bytes": int(size),
                "size_mb": float(size) / (1024 ** 2),
                "size_gb": _human_gb(size),
            }
        )

    df = pd.DataFrame(rows)
    stats["__total__"] = {"count": len(files), "gb": _human_gb(total_bytes)}
    return df, stats


def print_summary(stats: Dict[str, Dict[str, float]]) -> None:
    total_count = int(stats["__total__"]["count"])
    total_gb = float(stats["__total__"]["gb"])

    print("\n======================================================================")
    print("RÉSUMÉ DES DONNÉES DISPONIBLES")
    print("======================================================================")
    print(f"Total: {total_count} fichiers ({total_gb:.2f} GB)\n")

    for k in ["images", "binaries", "csv", "text", "other"]:
        c = int(stats[k]["count"])
        g = float(stats[k]["gb"])
        if c > 0:
            print(f"{k.upper()}:")
            print(f"  Fichiers: {c}")
            print(f"  Taille: {g:.2f} GB\n")


def write_checksums(df: pd.DataFrame, data_dir: str, out_dir: str) -> Path:
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    checksums_path = outp / "data_checksums.csv"

    root = Path(data_dir)
    # compute sha256 for reproducibility
    sha = []
    for p in df["path"].tolist():
        fp = Path(p)
        sha.append(_sha256_file(fp))

    out_df = df.copy()
    out_df["sha256"] = sha
    out_df.to_csv(checksums_path, index=False)
    return checksums_path


def write_manifest(df: pd.DataFrame, out_dir: str) -> Path:
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    manifest_path = outp / "data_manifest.csv"

    # manifest minimal et stable pour les benches
    cols = ["path", "kind", "size_bytes", "size_mb", "size_gb", "ext", "relpath"]
    df[cols].to_csv(manifest_path, index=False)
    return manifest_path


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="python -m src.data.real_data_loader",
        description="Scan/validate user real data + produce checksums + manifest (REAL DATA ONLY).",
    )
    ap.add_argument("--data-dir", default="data/user_data", help="Root directory containing real user data.")
    ap.add_argument("--out-dir", default="results/data", help="Where to write CSV outputs.")
    ap.add_argument("--max-files", type=int, default=0, help="If >0, limit number of files scanned (debug).")
    ap.add_argument("--validate", action="store_true", help="Scan + summary + checksums.")
    ap.add_argument("--create-manifest", action="store_true", help="Create data_manifest.csv for benchmarking.")

    args = ap.parse_args()

    print(f"📂 Scan du répertoire: {args.data_dir}")
    df, stats = scan_data_dir(args.data_dir, max_files=args.max_files)

    total_files = int(stats["__total__"]["count"])
    total_gb = float(stats["__total__"]["gb"])

    print(f"✓ {total_files} fichiers trouvés")
    print(f"✓ Taille totale: {total_gb:.2f} GB")

    # breakdown
    for k in ["images", "binaries", "csv", "text", "other"]:
        c = int(stats[k]["count"])
        g = float(stats[k]["gb"])
        if c > 0:
            print(f"  • {k}: {c} fichiers ({g:.2f} GB)")

    if args.validate:
        checksums_path = write_checksums(df, args.data_dir, args.out_dir)
        print(f"✓ Checksums sauvegardés: {checksums_path}")

    print_summary(stats)

    if args.create_manifest:
        man = write_manifest(df, args.out_dir)
        print(f"✓ Manifest sauvegardé: {man}")


if __name__ == "__main__":
    main()
