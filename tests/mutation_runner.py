#!/usr/bin/env python3
"""Mutation check for the delivered ticket-summary tests.

Each mutant is a small textual edit to ``summary.py`` -- the counting logic
that ``summary.sh`` runs -- applied to a throwaway copy of the project.  The
delivered suite (``bash run-tests.sh``) is then re-run against that copy.  A
mutant is *killed* when the suite fails; a mutant that the suite still passes
is a *survivor* and is reported.

The report is written to ``reports/mutation/mutation.json`` as

    {"total": <int>, "survivors": [{"file": "...", "line": <int>,
                                    "description": "..."}, ...]}

The process exits non-zero when any mutant survives, so a broken test suite
cannot silently pass this check.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "mutation" / "mutation.json"

Edit = Tuple[str, str]

MUTANTS: List[Dict[str, object]] = [
    {
        "id": "swap-per-assignee-counts",
        "description": "swap the open and closed counts in every assignee line",
        "edits": [
            (
                'lines.append(f"{assignee} {opened} {closed}")',
                'lines.append(f"{assignee} {closed} {opened}")',
            )
        ],
    },
    {
        "id": "swap-totals",
        "description": "swap the open and closed totals on the TOTAL line",
        "edits": [
            (
                'lines.append(f"{TOTAL_LABEL} {open_total} {closed_total}")',
                'lines.append(f"{TOTAL_LABEL} {closed_total} {open_total}")',
            )
        ],
    },
    {
        "id": "drop-totals-line",
        "description": "omit the file-wide TOTAL line",
        "edits": [
            (
                'lines.append(f"{TOTAL_LABEL} {open_total} {closed_total}")',
                "pass  # mutant: totals line dropped",
            )
        ],
    },
    {
        "id": "totals-line-first",
        "description": "print the TOTAL line before the assignee lines",
        "edits": [
            (
                'lines.append(f"{TOTAL_LABEL} {open_total} {closed_total}")',
                'lines.insert(0, f"{TOTAL_LABEL} {open_total} {closed_total}")',
            )
        ],
    },
    {
        "id": "count-header-row",
        "description": "count the header row as an extra open ticket",
        "edits": [
            (
                "        rows: List[Tuple[str, str]] = []\n",
                "        rows: List[Tuple[str, str]] = [(header[assignee_index], OPEN)]\n",
            )
        ],
    },
    {
        "id": "omit-closed-zero-assignees",
        "description": "skip assignees whose closed count is zero",
        "edits": [
            (
                "        opened, closed = counts[assignee]\n",
                "        opened, closed = counts[assignee]\n"
                "        if closed == 0:\n"
                "            continue  # mutant: drop all-open assignees\n",
            )
        ],
    },
    {
        "id": "unrecognised-status-is-open",
        "description": "count an unrecognised status as open instead of skipping it",
        "edits": [
            (
                "        else:\n"
                "            continue  # AMB-004 (skip): unrecognised status, no count.\n",
                "        else:\n"
                "            slot = 0\n",
            )
        ],
    },
    {
        "id": "count-empty-assignee",
        "description": "count rows whose assignee cell is empty",
        "edits": [
            (
                '        if assignee == "":\n'
                "            continue  # AMB-004 (skip): empty assignee, no count.\n",
                '        if assignee == "":\n'
                "            pass  # mutant: count empty assignees\n",
            )
        ],
    },
    {
        "id": "keep-too-short-rows",
        "description": "do not skip rows that lack one of the two columns",
        "edits": [
            (
                "                    if len(record) <= needed:\n"
                "                        continue  # AMB-004 (skip): too short, contributes to no count.\n",
                "                    if False:\n"
                "                        continue  # mutant: keep short rows\n",
            )
        ],
    },
    {
        "id": "reverse-sort-order",
        "description": "sort assignees in descending byte order",
        "edits": [
            (
                'key=lambda name: name.encode("utf-8")',
                'key=lambda name: name.encode("utf-8"), reverse=True',
            )
        ],
    },
    {
        "id": "case-insensitive-status",
        "description": "accept Open/CLOSED and surrounding blanks as recognised statuses",
        "edits": [
            (
                "        if status == OPEN:",
                "        if status.strip().lower() == OPEN:",
            ),
            (
                "        elif status == CLOSED:",
                "        elif status.strip().lower() == CLOSED:",
            ),
        ],
    },
    {
        "id": "open-total-is-assignee-count",
        "description": "print the number of assignees as the open total",
        "edits": [
            (
                "    open_total = sum(pair[0] for pair in counts.values())",
                "    open_total = len(counts)",
            )
        ],
    },
    {
        "id": "closed-total-is-assignee-count",
        "description": "print the number of assignees as the closed total",
        "edits": [
            (
                "    closed_total = sum(pair[1] for pair in counts.values())",
                "    closed_total = len(counts)",
            )
        ],
    },
    {
        "id": "double-count-every-row",
        "description": "increment both the open and the closed bucket for each row",
        "edits": [
            (
                "        counts.setdefault(assignee, [0, 0])[slot] += 1",
                "        counts.setdefault(assignee, [0, 0])[slot] += 1\n"
                "        counts.setdefault(assignee, [0, 0])[1 - slot] += 1",
            )
        ],
    },
    {
        "id": "entry-point-drops-totals",
        "target": "summary.sh",
        "description": "make summary.sh filter the TOTAL line out of the report",
        "edits": [
            (
                'exec python3 "$here/summary.py" "$1"\n',
                'python3 "$here/summary.py" "$1" | grep -v "^TOTAL "\n'
                'exit "${PIPESTATUS[0]}"\n',
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
        mutated = mutated.replace(old, new)
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
    for name in ("summary.sh", "summary.py", "run-tests.sh", "tests"):
        source = ROOT / name
        target = destination / name
        if source.is_dir():
            shutil.copytree(source, target, ignore=ignore)
        else:
            shutil.copy2(source, target)
        if name == "summary.sh":
            target.chmod(0o755)
    (destination / "run-tests.sh").chmod(0o755)
    (destination / "tests" / "mutation.sh").chmod(0o755)


def run_suite(work: Path) -> int:
    env = dict(os.environ)
    env["TAP_OUT"] = "reports/tests.tap"
    completed = subprocess.run(
        ["bash", "run-tests.sh"],
        cwd=str(work),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return completed.returncode


def main() -> int:
    sources = {
        "summary.py": (ROOT / "summary.py").read_text(encoding="utf-8"),
        "summary.sh": (ROOT / "summary.sh").read_text(encoding="utf-8"),
    }
    survivors: List[Dict[str, object]] = []

    for mutant in MUTANTS:
        target = str(mutant.get("target", "summary.py"))
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

        killed = returncode != 0
        print(
            f"{'killed  ' if killed else 'SURVIVED'} {mutant['id']}: "
            f"{mutant['description']}"
        )
        if not killed:
            survivors.append(
                {
                    "file": target,
                    "line": line,
                    "description": str(mutant["description"]),
                }
            )

    report = {"total": len(MUTANTS), "survivors": survivors}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"mutants: {len(MUTANTS)}")
    print(f"survivors: {len(survivors)}")
    print(f"report: {REPORT.relative_to(ROOT)}")
    print(json.dumps(report, indent=2))
    if not MUTANTS:
        print("mutation: no mutants were applied", file=sys.stderr)
        return 1
    return 0 if not survivors else 1


if __name__ == "__main__":
    sys.exit(main())
