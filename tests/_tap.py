"""Minimal TAP runner shared by the delivered test suites.

Every suite below collects plain ``test_*`` functions, runs them, prints a TAP
report and returns a nonzero exit status when any check fails.  ``$TAP_OUT``
overrides the report path so the mutation harness can point a mutant's run at
a throwaway directory; ``env_var`` lets a suite that must *read* the
acceptance report write its own report through a different variable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent


def run_tests(
    tests: Sequence[Callable[[], None]],
    default_path: str,
    env_var: str = "TAP_OUT",
) -> int:
    results: List[Tuple[str, bool, str]] = []
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - every failure is a TAP result
            detail = str(exc) or exc.__class__.__name__
            results.append((test.__name__, False, detail))
        else:
            results.append((test.__name__, True, ""))

    out = ["TAP version 13"]
    for number, (name, passed, detail) in enumerate(results, start=1):
        out.append(("ok " if passed else "not ok ") + f"{number} - {name}")
        if not passed:
            for detail_line in detail.splitlines():
                out.append(f"  # {detail_line}")
    out.append(f"1..{len(results)}")
    passed_count = sum(1 for _, passed, _ in results if passed)
    out.append(f"# tests {len(results)}")
    out.append(f"# pass {passed_count}")
    out.append(f"# fail {len(results) - passed_count}")
    text = "\n".join(out) + "\n"

    tap_path = Path(os.environ.get(env_var, default_path))
    if not tap_path.is_absolute():
        tap_path = ROOT / tap_path
    tap_path.parent.mkdir(parents=True, exist_ok=True)
    tap_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if passed_count == len(results) else 1
