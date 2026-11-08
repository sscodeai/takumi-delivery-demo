#!/usr/bin/env python3
"""Contract tests for the delivery as a whole.

These checks cover the acceptance criteria that are about the *delivery*
rather than about one invocation of the tool:

  REQ-006  ``bash run-tests.sh`` writes readable TAP with no failures, and the
           report asserts the counting, single-status, shuffling, header-only
           and AMB-nnn cases;
  REQ-007  ``mutation/run.sh`` declares mutants, and its report has the
           documented survivors shape with no survivor;
  ADR-060  ``docs/decisions.md`` anchors every AMB-nnn answer in the source,
           and the source carries greppable ``AMB-00n`` comments.

They run after the acceptance and unit suites in ``run-tests.sh`` so the TAP
reports they read already exist.  This suite's own report is written to
``reports/tests-contract.tap`` (or ``$CONTRACT_TAP_OUT``).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tap import ROOT, run_tests  # noqa: E402  (path is set up above)

AMBIGUITIES = ("AMB-001", "AMB-002", "AMB-003", "AMB-004")

REQUIRED_ACCEPTANCE_CHECKS = (
    "test_mixed_per_assignee_open_and_closed_counts",
    "test_assignee_with_only_one_status_prints_a_zero",
    "test_shuffling_data_rows_does_not_change_the_output",
    "test_header_only_file_prints_nothing_and_exits_zero",
    "test_status_is_trimmed_and_case_insensitive",
    "test_one_line_per_assignee_with_both_counts_and_nothing_else",
    "test_skipped_rows_are_counted_on_stderr_and_do_not_change_counts",
    "test_header_without_required_columns_stops_the_run",
    "test_assignee_is_trimmed_but_case_is_preserved",
)


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def acceptance_tap_path() -> Path:
    return resolve(os.environ.get("TAP_OUT", "reports/tests.tap"))


def unit_tap_path() -> Path:
    tap = acceptance_tap_path()
    return tap.with_name(tap.name[: -len(".tap")] + "-units.tap")


def read_text(relative: str) -> str:
    path = ROOT / relative
    assert path.is_file(), f"missing required file: {relative}"
    return path.read_text(encoding="utf-8")


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


def load_mutation_harness():
    path = ROOT / "mutation" / "run.py"
    assert path.is_file(), "mutation/run.py is missing"
    spec = importlib.util.spec_from_file_location("mutation_run", path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- REQ-006: the delivered test entry point -------------------------------


def test_run_tests_entry_point_runs_the_delivered_suites() -> None:
    script = read_text("run-tests.sh")
    for name in (
        "tests/test_summary.py",
        "tests/test_summary_units.py",
        "tests/test_contract.py",
        "reports/tests.tap",
    ):
        assert name in script, f"run-tests.sh does not mention {name}"


def test_acceptance_tap_report_is_readable_and_has_no_failures() -> None:
    lines = read_tap(acceptance_tap_path())
    failures = [line for line in lines if line.startswith("not ok ")]
    assert not failures, f"acceptance report contains failures: {failures!r}"


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


# --- REQ-007: the mutation check -------------------------------------------


def test_mutation_entry_point_and_mutants_exist() -> None:
    script = read_text("mutation/run.sh")
    assert "mutation/run.py" in script, "mutation/run.sh must run mutation/run.py"
    module = load_mutation_harness()
    assert len(module.MUTANTS) > 0, "the mutation harness has no mutants"
    ids = [str(mutant["id"]) for mutant in module.MUTANTS]
    assert len(ids) == len(set(ids)), f"duplicate mutant ids: {ids!r}"
    for mutant in module.MUTANTS:
        assert str(mutant.get("target")) in {"summary.py", "summary.sh"}, (
            f"unknown mutation target in {mutant['id']}"
        )
        assert str(mutant["description"]).strip(), (
            f"mutant {mutant['id']} has no description"
        )
        assert mutant.get("edits"), f"mutant {mutant['id']} has no edits"


def test_mutation_report_path_matches_the_requirement() -> None:
    module = load_mutation_harness()
    assert Path(module.REPORT) == ROOT / "reports" / "mutation" / "mutation.json"


def test_mutation_report_has_the_documented_shape() -> None:
    report_path = ROOT / "reports" / "mutation" / "mutation.json"
    if not report_path.is_file():
        # Produced by `bash mutation/run.sh`, which the pipeline runs
        # separately; a fresh copy has nothing to validate yet.
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


# --- ADR-060: the decision record ------------------------------------------


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


def test_every_ambiguity_has_a_greppable_source_comment() -> None:
    source = read_text("summary.py")
    for ambiguity in AMBIGUITIES:
        assert ambiguity in source, (
            f"summary.py has no greppable {ambiguity} comment"
        )


def test_readme_documents_the_shipped_behaviour() -> None:
    readme = read_text("README.md")
    for ambiguity in AMBIGUITIES:
        assert ambiguity in readme, f"README does not name {ambiguity}"
    assert "sample/tickets.csv" in readme
    assert "skipped" in readme.lower()
    assert "mutation/run.sh" in readme


def test_requirement_deliverable_matches_the_shipped_commands() -> None:
    requirement = read_text("docs/requirements/intake.yaml")
    for expected in (
        'run: "bash summary.sh {csv}"',
        'run: "bash run-tests.sh"',
        'report_path: "reports/tests.tap"',
        'run: "bash mutation/run.sh"',
        'report_path: "reports/mutation/mutation.json"',
    ):
        assert expected in requirement, f"requirement omits {expected}"


def test_test_plan_covers_every_requirement_and_ambiguity() -> None:
    plan = read_text("docs/test-plan.md")
    for number in range(1, 8):
        assert f"REQ-00{number}" in plan, f"test plan omits REQ-00{number}"
    for ambiguity in AMBIGUITIES:
        assert ambiguity in plan, f"test plan omits {ambiguity}"


def test_sample_input_is_shipped() -> None:
    sample = ROOT / "sample" / "tickets.csv"
    assert sample.is_file(), "sample/tickets.csv is missing"
    text = sample.read_text(encoding="utf-8")
    assert text.splitlines()[0].strip() == "assignee,status"


TESTS = [
    test_run_tests_entry_point_runs_the_delivered_suites,
    test_acceptance_tap_report_is_readable_and_has_no_failures,
    test_acceptance_report_has_ok_lines_for_each_required_behaviour,
    test_default_acceptance_report_path_is_reports_tests_tap,
    test_unit_tap_report_is_readable_and_has_no_failures,
    test_mutation_entry_point_and_mutants_exist,
    test_mutation_report_path_matches_the_requirement,
    test_mutation_report_has_the_documented_shape,
    test_decisions_document_maps_every_ambiguity_to_source,
    test_every_ambiguity_has_a_greppable_source_comment,
    test_readme_documents_the_shipped_behaviour,
    test_requirement_deliverable_matches_the_shipped_commands,
    test_test_plan_covers_every_requirement_and_ambiguity,
    test_sample_input_is_shipped,
]


if __name__ == "__main__":
    sys.exit(run_tests(TESTS, "reports/tests-contract.tap"))
