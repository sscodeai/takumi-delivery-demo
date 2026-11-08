#!/usr/bin/env python3
"""Contract tests for the delivery as a whole.

These checks cover the acceptance criteria that are about the *delivery*
rather than about one invocation of the tool:

  REQ-005  ``bash run-tests.sh`` writes readable TAP with no failures, and the
           report asserts the per-assignee counts, the zero-count case and the
           totals line;
  REQ-006  the mutation harness declares mutants and its report has the
           documented survivors shape;
  REQ-007  the README names every ambiguity and says the decisions are pending
           human sign-off and are not checked by a judge.

They run after the acceptance and unit suites in ``run-tests.sh`` so the TAP
reports they read already exist.  The report for this suite is written to
``reports/tests-contract.tap`` (or ``$CONTRACT_TAP_OUT``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_runner  # noqa: E402  (path is set up above)

AMBIGUITIES = {
    "AMB-001": "one-line: one line per assignee carrying both the open count and the closed count",
    "AMB-002": "alphabetical: assignees sorted by name, locale-independent byte order",
    "AMB-003": "exact: only the lowercase tokens `open` and `closed` are recognised",
    "AMB-004": "skip: the row is ignored and the run continues, without affecting either count",
    "AMB-005": "explicit-zero: the missing category is printed as 0",
}

REQUIRED_ACCEPTANCE_CHECKS = (
    "test_header_line_is_recognised_and_not_counted",
    "test_mixed_per_assignee_open_and_closed_counts",
    "test_assignee_with_one_status_still_prints_both_counts",
    "test_totals_equal_the_sum_of_per_assignee_counts",
    "test_exactly_one_totals_line",
    "test_only_exact_lowercase_status_tokens_are_recognised",
    "test_assignees_are_sorted_by_locale_independent_bytes",
    "test_every_accepted_row_is_counted_exactly_once",
)


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def acceptance_tap_path() -> Path:
    return resolve(os.environ.get("TAP_OUT", "reports/tests.tap"))


def unit_tap_path() -> Path:
    tap = acceptance_tap_path()
    return tap.with_name(tap.name[: -len(".tap")] + "-summary-units.tap")


def read_tap(path: Path) -> List[str]:
    assert path.is_file(), f"missing TAP report: {path}"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines, f"empty TAP report: {path}"
    assert lines[0] == "TAP version 13", f"not TAP in {path}: {lines[0]!r}"
    plans = [line for line in lines if line.startswith("1..")]
    assert len(plans) == 1, f"expected exactly one TAP plan in {path}"
    total = int(plans[0][3:])
    results = [
        line
        for line in lines
        if line.startswith("ok ") or line.startswith("not ok ")
    ]
    assert len(results) == total, (
        f"{path} plan says {total} checks but it reports {len(results)}"
    )
    return lines


def result_names(lines: Sequence[str]) -> List[str]:
    names = []
    for line in lines:
        if line.startswith("ok ") or line.startswith("not ok "):
            names.append(line.split(" - ", 1)[1] if " - " in line else line)
    return names


def read_text(relative: str) -> str:
    path = ROOT / relative
    assert path.is_file(), f"missing required file: {relative}"
    return path.read_text(encoding="utf-8")


# --- REQ-005: the delivered test entry point -------------------------------


def test_run_tests_entry_point_runs_the_delivered_suites() -> None:
    script = read_text("run-tests.sh")
    assert "tests/test_summary.py" in script
    assert "tests/test_summary_units.py" in script
    assert "tests/test_contract.py" in script
    assert "reports/tests.tap" in script


def test_acceptance_tap_report_is_readable_and_has_no_failures() -> None:
    lines = read_tap(acceptance_tap_path())
    failures = [line for line in lines if line.startswith("not ok ")]
    assert not failures, f"acceptance report contains failures: {failures!r}"
    names = result_names(lines)
    for required in REQUIRED_ACCEPTANCE_CHECKS:
        assert required in names, (
            f"acceptance report does not assert {required}"
        )


def test_acceptance_report_has_ok_lines_for_each_required_behaviour() -> None:
    lines = read_tap(acceptance_tap_path())
    ok_names = {
        line.split(" - ", 1)[1]
        for line in lines
        if line.startswith("ok ") and " - " in line
    }
    missing = [
        name for name in REQUIRED_ACCEPTANCE_CHECKS if name not in ok_names
    ]
    assert not missing, f"no passing check for: {missing!r}"


def test_default_acceptance_report_path_is_reports_tests_tap() -> None:
    override = os.environ.get("TAP_OUT", "")
    if override in ("", "reports/tests.tap"):
        assert (ROOT / "reports" / "tests.tap").is_file(), (
            "the delivered suite must write reports/tests.tap"
        )


def test_unit_tap_report_is_readable_and_has_no_failures() -> None:
    lines = read_tap(unit_tap_path())
    failures = [line for line in lines if line.startswith("not ok ")]
    assert not failures, f"unit report contains failures: {failures!r}"
    assert result_names(lines), "unit report contains no checks"


# --- REQ-006: the mutation check -------------------------------------------


def test_mutation_harness_declares_mutants() -> None:
    assert len(mutation_runner.MUTANTS) > 0, "the mutation check has no mutants"
    ids = [str(mutant["id"]) for mutant in mutation_runner.MUTANTS]
    assert len(ids) == len(set(ids)), f"duplicate mutant ids: {ids!r}"
    for mutant in mutation_runner.MUTANTS:
        assert str(mutant.get("target", "summary.py")) in {
            "summary.py",
            "summary.sh",
        }, f"unknown mutation target in {mutant['id']}"
        assert str(mutant["description"]).strip(), (
            f"mutant {mutant['id']} has no description"
        )
        assert mutant.get("edits"), f"mutant {mutant['id']} has no edits"


def test_mutation_report_has_the_documented_shape() -> None:
    report_path = ROOT / "reports" / "mutation" / "mutation.json"
    if not report_path.is_file():
        # The report is produced by `bash tests/mutation.sh`, which the smoke
        # gate runs separately; there is nothing to validate in a fresh copy.
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(report, dict), "mutation report is not a JSON object"
    assert isinstance(report.get("total"), int), "mutation total is not an int"
    assert report["total"] > 0, "mutation total must be greater than zero"
    assert isinstance(report.get("survivors"), list), (
        "mutation survivors is not a list"
    )
    for survivor in report["survivors"]:
        assert isinstance(survivor, dict), "survivor entry is not an object"
        assert isinstance(survivor.get("file"), str)
        assert isinstance(survivor.get("line"), int)
        assert isinstance(survivor.get("description"), str)
    assert report["survivors"] == [], (
        f"the delivered suite left mutants alive: {report['survivors']!r}"
    )


def test_mutation_report_path_matches_the_requirement() -> None:
    assert mutation_runner.REPORT == (
        ROOT / "reports" / "mutation" / "mutation.json"
    )


# --- REQ-007: the documented decisions -------------------------------------


def test_readme_names_every_ambiguity_and_its_status() -> None:
    readme = read_text("README.md")
    for ambiguity in AMBIGUITIES:
        assert ambiguity in readme, f"README does not name {ambiguity}"
    lowered = readme.lower()
    assert "pending human sign-off" in lowered, (
        "README must state that the decisions are pending human sign-off"
    )
    assert "no judge checks" in lowered, (
        "README must state that no judge checks the pending decisions"
    )


def test_readme_records_the_default_taken_for_each_ambiguity() -> None:
    readme = read_text("README.md")
    for ambiguity, chosen in AMBIGUITIES.items():
        token = chosen.split(":", 1)[0]
        assert token in readme, (
            f"README does not record the `{token}` default for {ambiguity}"
        )


def test_decisions_document_maps_every_ambiguity_to_source() -> None:
    decisions = read_text("docs/decisions.md")
    for ambiguity in AMBIGUITIES:
        assert ambiguity in decisions, f"docs/decisions.md omits {ambiguity}"
    assert "summary.py:" in decisions, (
        "docs/decisions.md must anchor the decisions in summary.py"
    )
    assert "DEFAULTED" in decisions, (
        "docs/decisions.md must state the provenance of the decisions"
    )


def test_requirement_records_the_implemented_chosen_answers() -> None:
    requirement = read_text("docs/requirements/intake.yaml")
    for ambiguity, chosen in AMBIGUITIES.items():
        assert chosen in requirement, (
            f"the confirmed requirement does not record {ambiguity}'s answer"
        )
        assert requirement.count(chosen) >= 2, (
            f"{ambiguity}'s answer should appear in both confirmation and "
            "ambiguities sections"
        )


def test_test_plan_covers_every_requirement_and_ambiguity() -> None:
    plan = read_text("docs/test-plan.md")
    for number in range(1, 8):
        assert f"REQ-00{number}" in plan, f"test plan omits REQ-00{number}"
    for ambiguity in AMBIGUITIES:
        assert ambiguity in plan, f"test plan omits {ambiguity}"


def test_requirement_deliverable_matches_the_shipped_commands() -> None:
    requirement = read_text("docs/requirements/intake.yaml")
    assert 'run: "bash summary.sh {csv}"' in requirement
    assert 'run: "bash run-tests.sh"' in requirement
    assert 'report_path: "reports/tests.tap"' in requirement
    assert 'run: "bash tests/mutation.sh"' in requirement
    assert 'report_path: "reports/mutation/mutation.json"' in requirement


TESTS = [
    test_run_tests_entry_point_runs_the_delivered_suites,
    test_acceptance_tap_report_is_readable_and_has_no_failures,
    test_acceptance_report_has_ok_lines_for_each_required_behaviour,
    test_default_acceptance_report_path_is_reports_tests_tap,
    test_unit_tap_report_is_readable_and_has_no_failures,
    test_mutation_harness_declares_mutants,
    test_mutation_report_has_the_documented_shape,
    test_mutation_report_path_matches_the_requirement,
    test_readme_names_every_ambiguity_and_its_status,
    test_readme_records_the_default_taken_for_each_ambiguity,
    test_decisions_document_maps_every_ambiguity_to_source,
    test_requirement_records_the_implemented_chosen_answers,
    test_test_plan_covers_every_requirement_and_ambiguity,
    test_requirement_deliverable_matches_the_shipped_commands,
]


def main() -> int:
    results = []
    for test in TESTS:
        try:
            test()
            results.append((test.__name__, True, ""))
        except Exception as exc:  # noqa: BLE001 - every failure is a TAP result
            detail = str(exc) or exc.__class__.__name__
            results.append((test.__name__, False, detail))

    out = ["TAP version 13"]
    for number, (name, passed, detail) in enumerate(results, start=1):
        out.append(("ok" if passed else "not ok") + f" {number} - {name}")
        if not passed:
            for detail_line in detail.splitlines():
                out.append(f"  # {detail_line}")
    out.append(f"1..{len(results)}")
    passed_count = sum(1 for _, passed, _ in results if passed)
    out.append(f"# tests {len(results)}")
    out.append(f"# pass {passed_count}")
    out.append(f"# fail {len(results) - passed_count}")
    text = "\n".join(out) + "\n"

    tap_path = resolve(
        os.environ.get("CONTRACT_TAP_OUT", "reports/tests-contract.tap")
    )
    tap_path.parent.mkdir(parents=True, exist_ok=True)
    tap_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
