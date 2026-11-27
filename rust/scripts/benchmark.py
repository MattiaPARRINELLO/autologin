#!/usr/bin/env python3
"""Harnais de benchmark du binaire Rust.

Mesure le demarrage, le pic de memoire, le temps CPU et la taille du binaire,
puis compare le resultat aux budgets de `benchmarks/budgets.json`.

La memoire est echantillonnee pendant une execution courte retenue par
`--bench-hold-ms`, pour lire le pic reel du processus au lieu du maximum
herite de l'environnement.

La detection CESAR et l'interface GPUI n'existent pas encore : les budgets
correspondants restent declares mais marques `required: false`, donc le script
les signale comme en attente au lieu de les mesurer a tort.

Usage :

    python3 scripts/benchmark.py
    python3 scripts/benchmark.py --runs 20 --json benchmarks/report.json
    python3 scripts/benchmark.py --binary target/release/checkmate --no-build
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGETS = ROOT / "benchmarks" / "budgets.json"
DEV_NULL = subprocess.DEVNULL
HOLD_FLAG = "--bench-hold-ms="
SAMPLE_DELAY = 0.25
HOLD_MS = 500


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(ratio * (len(ordered) - 1))))
    return ordered[index]


def aggregate(values: list[float]) -> dict[str, float]:
    return {
        "median": statistics.median(values),
        "p95": percentile(values, 0.95),
        "max": max(values),
        "min": min(values),
    }


def executable_name() -> str:
    return "checkmate.exe" if sys.platform == "win32" else "checkmate"


def build_binary(profile: str = "release") -> Path:
    subprocess.run(
        ["cargo", "build", "--profile", profile, "-p", "checkmate-cli"],
        cwd=ROOT,
        check=True,
    )
    return ROOT / "target" / profile / executable_name()


def measure_startup(
    command: list[str], runs: int, warmup: int = 1
) -> dict[str, dict[str, float]]:
    for _ in range(warmup):
        subprocess.run(command, stdout=DEV_NULL, stderr=DEV_NULL, check=False)
    walls: list[float] = []
    cpus: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        process = subprocess.Popen(command, stdout=DEV_NULL, stderr=DEV_NULL)
        if sys.platform == "win32":
            code = process.wait()
        else:
            _, status, usage = _wait(process)
            code = _exit_code(status)
            cpus.append((usage.ru_utime + usage.ru_stime) * 1000)
        walls.append((time.perf_counter() - start) * 1000)
        if code != 0:
            raise SystemExit(f"le binaire a echoue avec le code {code}")
    metrics = {"cli_startup_ms": aggregate(walls)}
    if cpus:
        metrics["cpu_startup_ms"] = aggregate(cpus)
    return metrics


def measure_memory(command: list[str], runs: int = 3) -> float | None:
    hold = [*command, f"{HOLD_FLAG}{HOLD_MS}"]
    peaks = [peak for _ in range(runs) if (peak := _peak_memory(hold)) is not None]
    return max(peaks) if peaks else None


def _peak_memory(command: list[str]) -> float | None:
    if sys.platform == "win32":
        return _peak_memory_windows(command)
    if sys.platform.startswith("linux"):
        return _peak_memory_linux(command)
    return None


def _peak_memory_linux(command: list[str]) -> float | None:
    process = subprocess.Popen(command, stdout=DEV_NULL, stderr=DEV_NULL)
    time.sleep(SAMPLE_DELAY)
    peak = None
    status = Path(f"/proc/{process.pid}/status")
    try:
        for line in status.read_text(encoding="ascii").splitlines():
            if line.startswith("VmHWM:"):
                peak = int(line.split()[1]) / 1024
                break
    except OSError:
        peak = None
    process.wait()
    return peak


def _peak_memory_windows(command: list[str]) -> float | None:
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    process = subprocess.Popen(command, stdout=DEV_NULL, stderr=DEV_NULL)
    handle = kernel32.OpenProcess(0x0400 | 0x0010, False, process.pid)
    time.sleep(SAMPLE_DELAY)
    peak = None
    if handle:
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if ok:
            peak = counters.PeakWorkingSetSize / (1024 * 1024)
        kernel32.CloseHandle(handle)
    process.wait()
    return peak


def _wait(process: subprocess.Popen) -> tuple[int, int, object]:
    import os

    pid, status, usage = os.wait4(process.pid, 0)
    process.returncode = _exit_code(status)
    return pid, status, usage


def _exit_code(status: int) -> int:
    import os

    return os.waitstatus_to_exitcode(status)


def evaluate(metrics: dict, budgets: dict) -> list[dict]:
    checks = []
    for entry in budgets["budgets"]:
        key = entry["metric"]
        measured = metrics.get(key)
        if measured is None:
            status = "pending" if not entry.get("required") else "fail"
            checks.append({"metric": key, "status": status, "max": entry["max"]})
            continue
        value = measured.get(entry.get("aggregate", "max"))
        if value is None:
            checks.append({"metric": key, "status": "fail", "max": entry["max"]})
            continue
        status = "pass" if value <= entry["max"] else "fail"
        checks.append(
            {
                "metric": key,
                "value": round(value, 3),
                "max": entry["max"],
                "status": status,
            }
        )
    return checks


def report(
    binary: Path,
    runs: int,
    budgets: dict,
) -> dict:
    command = [str(binary)]
    metrics = measure_startup(command, runs)
    memory = measure_memory(command)
    if memory is not None:
        metrics["rss_peak_mib"] = {"max": memory}
    metrics["binary_mib"] = {"max": binary.stat().st_size / (1024 * 1024)}
    checks = evaluate(metrics, budgets)
    return {
        "schema": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _git_commit(),
        "platform": sys.platform,
        "machine": platform.machine(),
        "runs": runs,
        "binary": str(binary),
        "metrics": metrics,
        "checks": checks,
        "passed": all(check["status"] != "fail" for check in checks),
    }


def _git_commit() -> str | None:
    if shutil.which("git") is None:
        return None
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument(
        "--json", type=Path, default=ROOT / "benchmarks" / "report.json"
    )
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGETS)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()

    binary = args.binary or build_binary()
    if not binary.is_file():
        raise SystemExit(f"binaire introuvable : {binary}")
    budgets = json.loads(args.budgets.read_text(encoding="utf-8"))
    payload = report(binary, args.runs, budgets)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for check in payload["checks"]:
        value = check.get("value", "non mesure")
        print(f"{check['status']:7} {check['metric']:20} {value} / {check['max']}")
    print(f"rapport : {args.json}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
