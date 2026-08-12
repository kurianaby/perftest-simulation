#!/usr/bin/env python3
"""
Evaluate a JMeter result file (.JTL) against the NFR thresholds in thresholds.yaml.

Exit codes:
  0 - all thresholds met
  1 - one or more thresholds breached
  2 - configuration or input error (cannot evaluate)

Measurement policy:
  Latency percentiles are calculated on the steady-state load

  Error rate and sample count are assessed across the FULL run. 
"""

import argparse
import collections
import csv
import sys

import yaml

REQUIRED_GLOBAL = ["error_rate_pct_max", "min_throughput_rps", "min_samples"]
REQUIRED_TXN = ["p95_response_time_ms_max", "p99_response_time_ms_max"]


def percentile(sorted_values, q):
    """Nearest-rank percentile — matches the method used for calibration."""
    if not sorted_values:
        return None
    idx = min(int(len(sorted_values) * q / 100), len(sorted_values) - 1)
    return sorted_values[idx]


def load_config(path):
    with open(path) as fh:
        cfg = yaml.safe_load(fh)

    if not isinstance(cfg, dict) or "global" not in cfg or "transactions" not in cfg:
        sys.exit(f"[CONFIG] {path} must define both 'global' and 'transactions'")

    missing = [k for k in REQUIRED_GLOBAL if k not in cfg["global"]]
    if missing:
        sys.exit(f"[CONFIG] global section missing keys: {', '.join(missing)}")

    for txn, limits in cfg["transactions"].items():
        absent = [k for k in REQUIRED_TXN if k not in limits]
        if absent:
            sys.exit(f"[CONFIG] transaction '{txn}' missing keys: {', '.join(absent)}")

    return cfg


def load_samples(path):
    try:
        with open(path) as fh:
            rows = list(csv.DictReader(fh))
    except FileNotFoundError:
        sys.exit(f"[INPUT] results file not found: {path}")

    if not rows:
        sys.exit(f"[INPUT] {path} contains no samples — the run produced no load")

    for col in ("timeStamp", "elapsed", "label", "success"):
        if col not in rows[0]:
            sys.exit(f"[INPUT] {path} missing required column '{col}'")

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="path to JMeter .jtl file")
    ap.add_argument("thresholds", help="path to thresholds.yaml")
    ap.add_argument("--warmup-seconds", type=int, default=90,
                    help="window excluded from latency percentiles (default: 90)")
    args = ap.parse_args()

    cfg = load_config(args.thresholds)
    rows = load_samples(args.results)

    start = min(int(r["timeStamp"]) for r in rows)
    end = max(int(r["timeStamp"]) for r in rows)
    duration_s = max((end - start) / 1000, 1)

    breaches = []

    # ---- Global checks: assessed across the FULL run ----
    total = len(rows)
    failures = sum(1 for r in rows if r["success"] != "true")
    error_pct = 100 * failures / total
    throughput = total / duration_s

    g = cfg["global"]
    print(f"\n{'GLOBAL (full run)':<32} {'observed':>10} {'limit':>10}")
    print("-" * 54)

    print(f"{'samples':<32} {total:>10} {g['min_samples']:>10} (min)")
    if total < g["min_samples"]:
        breaches.append(f"sample count {total} below minimum {g['min_samples']}")

    print(f"{'error rate %':<32} {error_pct:>10.2f} {g['error_rate_pct_max']:>10} (max)")
    if error_pct > g["error_rate_pct_max"]:
        breaches.append(f"error rate {error_pct:.2f}% exceeds {g['error_rate_pct_max']}%")

    print(f"{'throughput /s':<32} {throughput:>10.1f} {g['min_throughput_rps']:>10} (min)")
    if throughput < g["min_throughput_rps"]:
        breaches.append(
            f"throughput {throughput:.1f}/s below minimum {g['min_throughput_rps']}/s")

    # ---- Latency checks: steady-state window only ----
    cutoff = start + args.warmup_seconds * 1000
    steady = [r for r in rows if int(r["timeStamp"]) >= cutoff]

    if not steady:
        sys.exit(f"[INPUT] warmup of {args.warmup_seconds}s leaves no samples "
                 f"to evaluate (run lasted {duration_s:.0f}s)")

    by_label = collections.defaultdict(list)
    for r in steady:
        by_label[r["label"]].append(int(r["elapsed"]))

    print(f"\nLATENCY (steady state, excluding first {args.warmup_seconds}s)")
    print(f"{'transaction':<24} {'n':>6} {'p95':>6} {'lim':>6} {'p99':>6} {'lim':>6}")
    print("-" * 60)

    for txn, limits in cfg["transactions"].items():
        if txn not in by_label:
            breaches.append(
                f"transaction '{txn}' is configured but absent from results — "
                f"sampler renamed or removed?")
            print(f"{txn:<24} {'ABSENT':>6}")
            continue

        d = sorted(by_label[txn])
        p95, p99 = percentile(d, 95), percentile(d, 99)
        l95 = limits["p95_response_time_ms_max"]
        l99 = limits["p99_response_time_ms_max"]

        print(f"{txn:<24} {len(d):>6} {p95:>6} {l95:>6} {p99:>6} {l99:>6}")

        if p95 > l95:
            breaches.append(f"{txn}: p95 {p95}ms exceeds {l95}ms")
        if p99 > l99:
            breaches.append(f"{txn}: p99 {p99}ms exceeds {l99}ms")

    ungated = sorted(set(by_label) - set(cfg["transactions"]))
    if ungated:
        print(f"\n[WARN] present in results but not gated: {', '.join(ungated)}")

    # ---- Verdict ----
    print()
    if breaches:
        print(f"NFR GATE FAILED — {len(breaches)} breach(es):")
        for b in breaches:
            print(f"  - {b}")
        return 1

    print("NFR GATE PASSED — all thresholds met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())