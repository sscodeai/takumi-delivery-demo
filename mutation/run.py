#!/usr/bin/env python3
"""Mutation harness for the delivered ticket-summary tests.

Each mutant below is one deliberate defect applied to ``summary.py`` (the
counting logic that ``summary.sh`` executes) or, for one mutant, to the entry
point itself.  The harness copies the delivered project into a throwaway
directory, applies ONE defect, runs the delivered suite
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
    "README.md",
)
PER_MUTANT_TIMEOUT_S = 300

Edit = Tuple[str, str]

# (id, description, edits).  Every anchor must occur exactly once in its
# target file, so a source change that invalidates a mutant fails loudly
# instead of silently mutating nothing.
MUTANTS: List[Dict[str, object]] = [
    {
        "id": "swap-per-assignee-counts",
        "target": "summary.py",
        "description": "swap the open and closed counts in every assignee line",
        "edits": [
            (
                '        lines.append(f"{assignee} {opened} {closed}")',
                '        lines.append(f"{assignee} {closed} {opened}")',
            )
        ],
    },
    {
        "id": "reverse-sort-order",
        "target": "summary.py",
        "description": "sort assignees in descending byte order",
        "edits": [
            (
                '    for assignee in sorted(counts, key=lambda name: name.encode("utf-8")):',
                '    for assignee in sorted(counts, key=lambda name: name.encode("utf-8"), reverse=True):',
            )
        ],
    },
    {
        "id": "unsorted-report",
        "target": "summary.py",
        "description": "report assignees in insertion order instead of sorted order",
        "edits": [
            (
                '    for assignee in sorted(counts, key=lambda name: name.encode("utf-8")):',
                "    for assignee in counts:",
            )
        ],
    },
    {
        "id": "wrong-line-separator",
        "target": "summary.py",
        "description": "separate the three fields with two spaces",
        "edits": [
            (
                '        lines.append(f"{assignee} {opened} {closed}")',
                '        lines.append(f"{assignee}  {opened} {closed}")',
            )
        ],
    },
    {
        "id": "status-without-trim",
        "target": "summary.py",
        "description": "stop trimming whitespace around a status value",
        "edits": [
            ("    cleaned = value.strip().lower()", "    cleaned = value.lower()")
        ],
    },
    {
        "id": "status-without-case-fold",
        "target": "summary.py",
        "description": "compare the status value case-sensitively",
        "edits": [
            ("    cleaned = value.strip().lower()", "    cleaned = value.strip()")
        ],
    },
    {
        "id": "unknown-status-is-open",
        "target": "summary.py",
        "description": "count an unrecognised status as open instead of skipping it",
        "edits": [("    return None", "    return OPEN")],
    },
    {
        "id": "closed-counted-as-open",
        "target": "summary.py",
        "description": "classify a closed status as open",
        "edits": [
            (
                "    if cleaned == CLOSED:\n        return CLOSED",
                "    if cleaned == CLOSED:\n        return OPEN",
            )
        ],
    },
    {
        "id": "count-empty-assignee",
        "target": "summary.py",
        "description": "count rows whose assignee cell is empty",
        "edits": [
            (
                '        if assignee == "":',
                '        if assignee == "\\x00":',
            )
        ],
    },
    {
        "id": "assignee-without-trim",
        "target": "summary.py",
        "description": "keep surrounding whitespace in the assignee name",
        "edits": [("    return value.strip()", "    return value")],
    },
    {
        "id": "assignee-case-folded",
        "target": "summary.py",
        "description": "merge `Alice` and `alice` into one assignee",
        "edits": [("    return value.strip()", "    return value.strip().lower()")],
    },
    {
        "id": "uncounted-bad-status",
        "target": "summary.py",
        "description": "skip an unrecognised status without counting the row",
        "edits": [
            (
                "        if status is None:\n            skipped += 1\n            continue",
                "        if status is None:\n            continue",
            )
        ],
    },
    {
        "id": "uncounted-empty-assignee",
        "target": "summary.py",
        "description": "skip an empty assignee without counting the row",
        "edits": [
            (
                '        if assignee == "":\n            skipped += 1\n            continue',
                '        if assignee == "":\n            continue',
            )
        ],
    },
    {
        "id": "uncounted-short-row",
        "target": "summary.py",
        "description": "skip a too-short row without counting it",
        "edits": [
            (
                "        if len(record) <= needed:\n            skipped += 1\n            continue",
                "        if len(record) <= needed:\n            continue",
            )
        ],
    },
    {
        "id": "skip-report-suppressed",
        "target": "summary.py",
        "description": "never report the skipped row count on stderr",
        "edits": [("    if skipped:", "    if False:")],
    },
    {
        "id": "skip-report-always-printed",
        "target": "summary.py",
        "description": "print a skipped-row message even when nothing was skipped",
        "edits": [("    if skipped:", "    if True:")],
    },
    {
        "id": "extra-total-line",
        "target": "summary.py",
        "description": "append a file-wide TOTAL line after the assignee lines",
        "edits": [
            (
                '        lines.append(f"{assignee} {opened} {closed}")\n    return lines',
                '        lines.append(f"{assignee} {opened} {closed}")\n'
                '    lines.append("TOTAL %d %d" % (sum(p[0] for p in counts.values()), sum(p[1] for p in counts.values())))\n'
                "    return lines",
            )
        ],
    },
    {
        "id": "columns-by-position",
        "target": "summary.py",
        "description": "ignore the header names and read the first two columns",
        "edits": [
            (
                '    return positions["assignee"], positions["status"]',
                "    return 0, 1",
            )
        ],
    },
    {
        "id": "missing-header-tolerated",
        "target": "summary.py",
        "description": "treat a header without the required columns as column 0",
        "edits": [
            (
                "    if missing:\n"
                "        raise InputError(\n"
                '            "header is missing required column(s): " + ", ".join(missing)\n'
                "        )",
                "    if missing:\n"
                "        for name in missing:\n"
                "            positions[name] = 0",
            )
        ],
    },
    {
        "id": "empty-file-is-empty-report",
        "target": "summary.py",
        "description": "treat a file without a header as empty input with exit 0",
        "edits": [
            (
                "                raise InputError(\n"
                '                    f"{path} is empty; expected a header naming "\n'
                "                    + \", \".join(REQUIRED_COLUMNS)\n"
                "                )",
                "                return {}, 0",
            )
        ],
    },
    {
        "id": "count-header-row",
        "target": "summary.py",
        "description": "feed the header row to the counter as a data row",
        "edits": [
            (
                "            return summarise_records(header, reader)",
                "            return summarise_records(header, [header] + list(reader))",
            )
        ],
    },
    {
        "id": "overwrite-instead-of-increment",
        "target": "summary.py",
        "description": "set each bucket to 1 instead of incrementing it",
        "edits": [
            (
                "        counts.setdefault(assignee, [0, 0])[slot] += 1",
                "        counts.setdefault(assignee, [0, 0])[slot] = 1",
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
