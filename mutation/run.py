#!/usr/bin/env python3
"""Mutation harness for the delivered region-summary tests.

Each mutant below is one deliberate defect applied to ``summary.py`` (the
aggregation and formatting logic that ``summary.sh`` executes) or, for one
mutant, to the entry point itself.  The harness copies the delivered project
into a throwaway directory, applies ONE defect, runs the delivered suite
(``bash run-tests.sh``) against that copy and records whether the suite
noticed.  A mutant the suite still passes is a SURVIVOR -- a gap in the tests.

The tool-agnostic report is written to ``reports/mutation/mutation.json``::

    {"total": <mutants measured>,
     "survivors": [{"file": ..., "line": ..., "description": ...}, ...]}

The command exits nonzero when any mutant survives (or when no mutant was
measured), so a suite that cannot fail is never reported as green.  Only the
Python 3 standard library is used; no network access and no install step are
needed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "mutation" / "mutation.json"
COPY_ENTRIES = (
    "summary.sh",
    "summary.py",
    "run-tests.sh",
    "tests",
    "sample",
    "docs",
    "mutation",
    "README.md",
)
PER_MUTANT_TIMEOUT_S = 300

Edit = Tuple[str, str]

# (id, description, edits).  Every anchor must occur exactly once in its
# target file, so a source change that invalidates a mutant fails loudly
# instead of silently mutating nothing.
MUTANTS: List[Dict[str, object]] = [
    {
        "id": "mean-replaced-by-sum",
        "target": "summary.py",
        "description": "print the region sum where the mean belongs",
        "edits": [
            (
                'f"{format_amount(_mean(total, count))}"',
                'f"{format_amount(total)}"',
            )
        ],
    },
    {
        "id": "swap-sum-and-mean",
        "target": "summary.py",
        "description": "swap the sum and mean fields of every region line",
        "edits": [
            (
                '            f"{region} {count} {format_amount(total)} "\n'
                '            f"{format_amount(_mean(total, count))}"',
                '            f"{region} {count} {format_amount(_mean(total, count))} "\n'
                '            f"{format_amount(total)}"',
            )
        ],
    },
    {
        "id": "truncate-instead-of-half-up",
        "target": "summary.py",
        "description": "truncate the mean instead of rounding half up",
        "edits": [
            (
                "rounded = value.quantize(CENT, rounding=ROUND_HALF_UP)",
                "rounded = value.quantize(CENT, rounding=ROUND_DOWN)",
            )
        ],
    },
    {
        "id": "one-decimal-formatting",
        "target": "summary.py",
        "description": "print amounts with one decimal place instead of two",
        "edits": [
            ('    return format(rounded, "f")', '    return f"{rounded:.1f}"')
        ],
    },
    {
        "id": "mean-added-to-the-total-line",
        "target": "summary.py",
        "description": "add an overall mean to the TOTAL line",
        "edits": [
            (
                '    lines.append(f"TOTAL {total_count} {format_amount(total_sum)}")',
                '    lines.append(f"TOTAL {total_count} {format_amount(total_sum)} '
                '{format_amount(total_sum)}")',
            )
        ],
    },
    {
        "id": "last-amount-wins",
        "target": "summary.py",
        "description": "keep only the last amount per region instead of adding",
        "edits": [
            (
                "        totals[region] = totals.get(region, Decimal(0)) + amount",
                "        totals[region] = amount",
            )
        ],
    },
    {
        "id": "malformed-not-counted",
        "target": "summary.py",
        "description": "skip a malformed row without counting it on SKIPPED",
        "edits": [
            (
                '        if region == "" or amount is None:\n'
                "            skipped += 1\n"
                "            continue",
                '        if region == "" or amount is None:\n'
                "            continue",
            )
        ],
    },
    {
        "id": "blank-lines-counted",
        "target": "summary.py",
        "description": "treat a blank line as a malformed data row",
        "edits": [
            (
                "    for record in records:\n"
                "        if is_blank_record(record):\n"
                "            continue",
                "    for record in records:\n"
                "        if False:\n"
                "            continue",
            )
        ],
    },
    {
        "id": "columns-by-position",
        "target": "summary.py",
        "description": "ignore the header names and read the first two columns",
        "edits": [
            (
                '    return positions["region"], positions["amount"]',
                "    return 0, 1",
            )
        ],
    },
    {
        "id": "unsorted-regions",
        "target": "summary.py",
        "description": "report regions in insertion order instead of sorted order",
        "edits": [
            (
                '    for region in sorted(counts, key=lambda name: name.encode("utf-8")):',
                "    for region in counts:",
            )
        ],
    },
    {
        "id": "negative-refund-rejected",
        "target": "summary.py",
        "description": "reject a negative amount as unusable instead of including it",
        "edits": [
            (
                '        if region == "" or amount is None:',
                '        if region == "" or amount is None or amount < 0:',
            )
        ],
    },
    {
        "id": "skipped-line-always-zero",
        "target": "summary.py",
        "description": "always print SKIPPED 0 regardless of the real count",
        "edits": [
            (
                '    lines.append(f"SKIPPED {skipped}")',
                '    lines.append("SKIPPED 0")',
            )
        ],
    },
    {
        "id": "total-count-is-region-count",
        "target": "summary.py",
        "description": "put the number of distinct regions on TOTAL instead of records",
        "edits": [
            (
                "    total_count = sum(counts.values())",
                "    total_count = len(counts)",
            )
        ],
    },
    {
        "id": "header-never-detected",
        "target": "summary.py",
        "description": "treat a header row as a data row",
        "edits": [
            (
                "            if looks_like_header(first):",
                "            if False:",
            )
        ],
    },
    {
        "id": "header-always-assumed",
        "target": "summary.py",
        "description": "treat the first data row of a headerless file as a header",
        "edits": [
            (
                "            if looks_like_header(first):",
                "            if True:",
            )
        ],
    },
    {
        "id": "entry-point-truncates-report",
        "target": "summary.sh",
        "description": "make summary.sh print only the first report line",
        "edits": [
            (
                'exec python3 "$here/summary.py" "$1"',
                'exec python3 "$here/summary.py" "$1" | head -n 1',
            )
        ],
    },
]


def apply_edits(source: str, edits: Sequence[Edit]) -> str:
    mutated = source
    for old, new in edits:
        occurrences = mutated.count(old)
        if occurrences != 1:
            raise RuntimeError(
                "mutation anchor must occur exactly once, found "
                f"{occurrences}: {old!r}"
            )
        mutated = mutated.replace(old, new, 1)
    return mutated


def anchor_line(source: str, edits: Sequence[Edit]) -> int:
    old = edits[0][0]
    if old not in source:
        raise RuntimeError(f"mutation anchor not found: {old!r}")
    return source[: source.index(old)].count("\n") + 1


def copy_project(destination: Path) -> None:
    ignore = shutil.ignore_patterns(
        "__pycache__", "*.pyc", "reports", ".git", "node_modules"
    )
    for name in COPY_ENTRIES:
        source = ROOT / name
        target = destination / name
        if source.is_dir():
            shutil.copytree(source, target, ignore=ignore)
        else:
            shutil.copy2(source, target)


def run_suite(work: Path) -> int:
    environment = dict(os.environ)
    environment["TAP_OUT"] = str(work / "reports" / "tests.tap")
    try:
        completed = subprocess.run(
            ["bash", "run-tests.sh"],
            cwd=str(work),
            env=environment,
            capture_output=True,
            text=True,
            timeout=PER_MUTANT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return 124
    return completed.returncode


def run_mutant(
    mutant: Dict[str, object], sources: Dict[str, str]
) -> Tuple[int, int]:
    """Apply one mutant in a throwaway copy and return (anchor line, rc)."""
    target = str(mutant["target"])
    source = sources[target]
    edits = mutant["edits"]  # type: ignore[assignment]
    line = anchor_line(source, edits)
    work = Path(tempfile.mkdtemp(prefix="takumi-mutation-"))
    try:
        copy_project(work)
        (work / target).write_text(
            apply_edits(source, edits), encoding="utf-8"
        )
        returncode = run_suite(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return line, returncode


def write_report(payload: Dict[str, object]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if not MUTANTS:
        sys.stderr.write("mutation: no mutants were applied\n")
        return 1

    sources = {
        "summary.py": (ROOT / "summary.py").read_text(encoding="utf-8"),
        "summary.sh": (ROOT / "summary.sh").read_text(encoding="utf-8"),
    }

    jobs = max(1, int(os.environ.get("MUTATION_JOBS", "4")))
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        outcomes = list(
            pool.map(lambda mutant: run_mutant(mutant, sources), MUTANTS)
        )

    survivors: List[Dict[str, object]] = []
    for mutant, (line, returncode) in zip(MUTANTS, outcomes):
        killed = returncode != 0
        print(
            f"{'killed  ' if killed else 'SURVIVED'} {mutant['id']}: "
            f"{mutant['description']}"
        )
        if not killed:
            survivors.append(
                {
                    "file": str(mutant["target"]),
                    "line": line,
                    "description": str(mutant["description"]),
                }
            )

    report = {"total": len(MUTANTS), "survivors": survivors}
    write_report(report)

    print()
    print(f"mutants: {len(MUTANTS)}")
    print(f"survivors: {len(survivors)}")
    print(f"elapsed: {time.monotonic() - started:.1f}s")
    try:
        shown_report = REPORT.relative_to(ROOT)
    except ValueError:
        # A caller may point the report outside the project (the contract
        # suite does so to avoid touching the delivered report).
        shown_report = REPORT
    print(f"report: {shown_report}")
    print(json.dumps(report, indent=2))
    return 0 if not survivors else 1


if __name__ == "__main__":
    sys.exit(main())
