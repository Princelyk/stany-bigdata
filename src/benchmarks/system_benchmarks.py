#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System-level benchmarks for hybrid pipelines
Generates CSV outputs for publication figures.
"""

from __future__ import annotations

import time
import os
import csv
import psutil
from typing import Callable, Dict, List
import numpy as np


class SystemBenchmark:
    def __init__(self):
        self.process = psutil.Process(os.getpid())

    def run(
        self,
        name: str,
        func: Callable,
        repetitions: int = 10,
        payload_bytes: int | None = None,
        out_csv: str = "results/data/metrics_systembench.csv",
    ) -> None:
        rows: List[Dict] = []

        for rep in range(repetitions):
            cpu_before = self.process.cpu_percent(interval=None)
            mem_before = self.process.memory_info().rss / 1e6

            t0 = time.perf_counter()
            func()
            t1 = time.perf_counter()

            cpu_after = self.process.cpu_percent(interval=0.1)
            mem_after = self.process.memory_info().rss / 1e6

            wall_ms = (t1 - t0) * 1000
            throughput = None
            if payload_bytes:
                throughput = (payload_bytes / 1e6) / (t1 - t0)

            rows.append({
                "rep": rep,
                "pipeline": name,
                "wall_ms": wall_ms,
                "cpu_mean_percent": cpu_after,
                "rss_mean_mb": mem_after,
                "throughput_mb_s": throughput,
            })

        os.makedirs(os.path.dirname(out_csv), exist_ok=True)
        write_header = not os.path.exists(out_csv)

        with open(out_csv, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            if write_header:
                writer.writeheader()
            writer.writerows(rows)

        print(f"✓ system metrics appended → {out_csv}")

