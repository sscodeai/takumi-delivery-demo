#!/usr/bin/env python3
"""Contract tests for the delivery as a whole.

These checks cover the acceptance criteria that are about the *delivery*
rather than about one invocation of the tool:

  REQ-011  ``bash run-tests.sh`` writes readable TAP with no failures, the
           report asserts the per-region totals, averages, TOTAL, SKIPPED and
           rounding behaviour, and a deliberately wrong aggregate makes the
           delivered suite fail;
  ADR-060  ``docs/decisions.md`` anchors every AMB-nnn answer in the source,
           and the source carries greppable ``AMB-00n`` comments;
  REQ-001  the declared deliverable commands and the shipped files agree.

They run after the acceptance and unit suites in ``run-tests.sh`` so the TAP
reports they read already exist.  This suite's own report is written to
``reports/tests-contract.tap`` (or ``$CONTRACT_TAP_OUT``).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tap import ROOT, run_tests  # noqa: E402  (path is set up above)

AMBIGUITIES = ("AMB-001", "AMB-002", "AMB-003", "AMB-004")
REQUIREMENTS = tuple(f"REQ-{number:03d}" for number in range(1, 12))

# Names that must appear as passing checks in reports/tests.tap.
REQUIRED_ACCEPTANCE_CHECKS = (
    "test_declared_sample_without_a_header_produces_the_required_report",
    "test_per_region_count_sum_and_mean_are_printed",
    "test_total_line_is_printed_exactly_once_after_the_region_lines",
    "test_total_count_and_sum_are_additive_over_the_region_lines",
    "test_skipped_line_is_always_last_and_zero_for_a_clean_file",
    "test_malformed_rows_are_skipped_counted_and_excluded_from_totals",
    "test_identical_rows_are_merged_into_the_aggregates",
    "test_mean_with_more_than_two_decimals_rounds_half_up",
    "test_mean_at_an_exact_half_rounds_away_from_zero",
    "test_negative_amount_is_included_as_a_refund",
    "test_columns_are_located_by_header_name_not_position",
    "test_blank_lines_are_neither_records_nor_skipped_rows",
    "test_shuffling_data_rows_does_not_change_stdout_bytes",
    "test_header_only_file_prints_only_total_and_skipped",
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


def copy_delivery(destination: Path) -> None:
    """Copy the files a delivered-suite run needs into a throwaway tree."""
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "reports")
    for name in (
        "summary.py",
        "summary.sh",
        "run-tests.sh",
        "tests",
        "docs",
        "sample",
        "mutation",
        "README.md",
    ):
        source = ROOT / name
        target = destination / name
        if source.is_dir():
            shutil.copytree(source, target, ignore=ignore)
        elif source.is_file():
            shutil.copy2(source, target)


# --- REQ-011: the delivered test entry point --------------------------------


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


def test_a_wrong_aggregate_makes_the_delivered_suite_fail() -> None:
    # REQ-011: replace the per-region mean with the region sum in a throwaway
    # copy and prove the delivered acceptance suite fails.
    anchor = 'f"{format_amount(_mean(total, count))}"'
    replacement = 'f"{format_amount(total)}"'
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "delivery"
        work.mkdir()
        copy_delivery(work)
        source = (work / "summary.py").read_text(encoding="utf-8")
        assert source.count(anchor) == 1, "cannot apply the wrong-aggregate mutant"
        (work / "summary.py").write_text(
            source.replace(anchor, replacement), encoding="utf-8"
        )
        environment = dict(os.environ)
        environment["TAP_OUT"] = str(work / "reports" / "tests.tap")
        completed = subprocess.run(
            [sys.executable, "tests/test_summary.py"],
            cwd=str(work),
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        report = (work / "reports" / "tests.tap").read_text(encoding="utf-8")
    assert completed.returncode != 0, (
        "a mean replaced by a sum must make the delivered suite fail"
    )
    assert "not ok " in report, f"no failing TAP line: {report!r}"


def test_tool_uses_no_network_client() -> None:
    source = read_text("summary.py")
    for client in (
        "import socket",
        "import urllib",
        "import http",
        "import requests",
        "from socket",
        "from urllib",
        "from http",
    ):
        assert client not in source, f"summary.py imports a network client: {client}"


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
    assert "sample/sales.csv" in readme
    assert "SKIPPED" in readme
    assert "TOTAL" in readme
    assert "mutation/run.sh" in readme


def test_requirement_deliverable_matches_the_shipped_commands() -> None:
    requirement = read_text("docs/requirements/intake.yaml")
    for expected in (
        'run: "bash summary.sh {csv}"',
        'run: "bash run-tests.sh"',
        'report_path: "reports/tests.tap"',
        "region:id,amount:measure",
    ):
        assert expected in requirement, f"requirement omits {expected}"


def test_test_plan_covers_every_requirement_and_ambiguity() -> None:
    plan = read_text("docs/test-plan.md")
    for requirement in REQUIREMENTS:
        assert requirement in plan, f"test plan omits {requirement}"
    for ambiguity in AMBIGUITIES:
        assert ambiguity in plan, f"test plan omits {ambiguity}"


def test_sample_input_is_shipped_and_headerless_as_declared() -> None:
    sample = ROOT / "sample" / "sales.csv"
    assert sample.is_file(), "sample/sales.csv is missing"
    text = sample.read_text(encoding="utf-8")
    assert text == (
        "North,120.50\n"
        "South,80.25\n"
        "North,99.50\n"
        "East,45.00\n"
    ), text


# --- REQ-011: the mutation harness -----------------------------------------


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


def test_mutation_report_path_matches_the_documented_shape() -> None:
    module = load_mutation_harness()
    assert Path(module.REPORT) == ROOT / "reports" / "mutation" / "mutation.json"
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


def test_mutation_harness_fails_and_reports_a_surviving_mutant() -> None:
    # The harness must exit nonzero and list the survivor when a mutant is not
    # killed.  run_mutant is stubbed so this check does not recurse into the
    # suite that is currently running.
    module = load_mutation_harness()
    original_mutants = module.MUTANTS
    original_run_mutant = module.run_mutant
    original_report = module.REPORT
    survivor = {
        "id": "deliberate-survivor",
        "target": "summary.py",
        "description": "a deliberately surviving mutant",
        "edits": [("REQ-003", "REQ-003")],
    }
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "mutation.json"
        module.MUTANTS = [survivor]
        module.run_mutant = lambda mutant, sources: (1, 0)
        module.REPORT = report_path
        try:
            import contextlib
            import io

            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    returncode = module.main()
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        finally:
            module.MUTANTS = original_mutants
            module.run_mutant = original_run_mutant
            module.REPORT = original_report
    assert returncode != 0, "a surviving mutant must make the harness fail"
    assert payload["total"] == 1, payload
    assert len(payload["survivors"]) == 1, payload
    assert payload["survivors"][0]["description"] == survivor["description"]


TESTS = [
    test_run_tests_entry_point_runs_the_delivered_suites,
    test_acceptance_tap_report_is_readable_and_has_no_failures,
    test_acceptance_report_has_ok_lines_for_each_required_behaviour,
    test_default_acceptance_report_path_is_reports_tests_tap,
    test_unit_tap_report_is_readable_and_has_no_failures,
    test_a_wrong_aggregate_makes_the_delivered_suite_fail,
    test_tool_uses_no_network_client,
    test_decisions_document_maps_every_ambiguity_to_source,
    test_every_ambiguity_has_a_greppable_source_comment,
    test_readme_documents_the_shipped_behaviour,
    test_requirement_deliverable_matches_the_shipped_commands,
    test_test_plan_covers_every_requirement_and_ambiguity,
    test_sample_input_is_shipped_and_headerless_as_declared,
    test_mutation_entry_point_and_mutants_exist,
    test_mutation_report_path_matches_the_documented_shape,
    test_mutation_harness_fails_and_reports_a_surviving_mutant,
]


if __name__ == "__main__":
    sys.exit(
        run_tests(
            TESTS,
            "reports/tests-contract.tap",
            env_var="CONTRACT_TAP_OUT",
        )
    )
