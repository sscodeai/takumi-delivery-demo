#!/usr/bin/env python3
"""Contract tests for the delivery as a whole.

These checks cover the acceptance criteria that are about the *delivery*
rather than one invocation of the tool:

  REQ-001  ``bash summary.sh`` is the repository-root entry point;
  REQ-005  the non-mechanised policies are documented;
  ADR-060  ``docs/decisions.md`` anchors every AMB-nnn answer in the source,
           and the source carries greppable ``AMB-00n`` comments.

They run after the acceptance and unit suites in ``run-tests.sh``.  This
suite's own report is written to ``reports/tests-contract.tap`` (or
``$CONTRACT_TAP_OUT``).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tap import ROOT, run_tests  # noqa: E402

AMBIGUITIES = ("AMB-001", "AMB-002", "AMB-003", "AMB-004")
SUMMARY = ROOT / "summary.py"
DECISIONS = ROOT / "docs" / "decisions.md"
README = ROOT / "README.md"
REQUIREMENT = ROOT / "docs" / "requirements" / "intake.yaml"

POLICY_MARKERS = {
    "AMB-002": ("merge", "sum"),
    "AMB-003": ("0.0",),
    "AMB-004": ("non-zero", "line"),
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_summary_sh_is_the_declared_entry_point() -> None:
    script = ROOT / "summary.sh"
    assert script.is_file()
    assert "summary.py" in read(script)
    result = subprocess.run(
        ["bash", "summary.sh"], cwd=str(ROOT), capture_output=True, text=True
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() != ""


def test_source_uses_the_suite_world_from_this_requirement() -> None:
    source = read(SUMMARY)
    for word in ("suite", "passed", "total"):
        assert word in source, word
    # The inherited deliverable in this reused repository was a region/amount
    # revenue summary; this request must not continue that input world.
    assert "region" not in source.lower()
    assert "amount" not in source.lower()


def test_every_ambiguity_has_a_greppable_source_comment() -> None:
    source = read(SUMMARY)
    for ambiguity in AMBIGUITIES:
        assert ambiguity in source, ambiguity


def test_decisions_document_has_a_row_for_every_ambiguity_with_an_anchor() -> None:
    document = read(DECISIONS)
    source_lines = read(SUMMARY).splitlines()
    for ambiguity in AMBIGUITIES:
        rows = [
            line
            for line in document.splitlines()
            if line.strip().startswith("| %s" % ambiguity)
        ]
        assert len(rows) == 1, (ambiguity, rows)
        anchors = [int(number) for number in re.findall(r"summary\.py:(\d+)", rows[0])]
        assert anchors, (ambiguity, rows[0])
        for number in anchors:
            assert 1 <= number <= len(source_lines), (ambiguity, number)
        assert any(ambiguity in source_lines[number - 1] for number in anchors), (
            ambiguity,
            rows[0],
        )


def test_decisions_document_marks_the_defaulted_answers() -> None:
    document = read(DECISIONS)
    assert "DEFAULTED" in document
    assert "default:" in document


def test_readme_documents_each_non_mechanised_policy() -> None:
    text = read(README)
    lines = text.splitlines()
    for ambiguity, markers in POLICY_MARKERS.items():
        # REQ-005: exactly one documented policy per non-mechanised ambiguity.
        assert text.count(ambiguity) == 1, ambiguity
        index = next(i for i, line in enumerate(lines) if ambiguity in line)
        block = "\n".join(lines[index : index + 3]).lower()
        for marker in markers:
            assert marker in block, (ambiguity, marker, block)


def test_no_declared_relation_claims_the_edge_case_policies() -> None:
    # REQ-005: only AMB-001 is mechanised (REL-001). The duplicate-suite,
    # zero-total and malformed-row policies are documented but not claimed as
    # checked by a declared relation.
    document = read(REQUIREMENT)
    assert "decides: AMB-001" in document
    for ambiguity in ("AMB-002", "AMB-003", "AMB-004"):
        assert "decides: %s" % ambiguity not in document, ambiguity


def test_run_tests_script_names_the_delivered_suites() -> None:
    script = read(ROOT / "run-tests.sh")
    assert "tests/test_summary.py" in script
    assert "tests/test_summary_units.py" in script
    assert "tests/test_contract.py" in script


def test_the_delivery_pipeline_is_kept_and_runs_the_deliverable() -> None:
    pipeline = ROOT / ".github" / "workflows" / "ci.yml"
    assert pipeline.is_file()
    text = read(pipeline)
    assert "bash summary.sh" in text
    assert "run-tests.sh" in text


def test_shipped_sample_is_the_declared_sample_under_a_header() -> None:
    sample = read(ROOT / "sample" / "suites.csv")
    assert sample == (
        "suite,passed,total\n"
        "login,45,50\n"
        "search,19,20\n"
        "billing,7,8\n"
    )


TESTS = (
    test_summary_sh_is_the_declared_entry_point,
    test_source_uses_the_suite_world_from_this_requirement,
    test_every_ambiguity_has_a_greppable_source_comment,
    test_decisions_document_has_a_row_for_every_ambiguity_with_an_anchor,
    test_decisions_document_marks_the_defaulted_answers,
    test_readme_documents_each_non_mechanised_policy,
    test_no_declared_relation_claims_the_edge_case_policies,
    test_run_tests_script_names_the_delivered_suites,
    test_the_delivery_pipeline_is_kept_and_runs_the_deliverable,
    test_shipped_sample_is_the_declared_sample_under_a_header,
)


if __name__ == "__main__":
    raise SystemExit(
        run_tests(
            TESTS,
            "reports/tests-contract.tap",
            env_var="CONTRACT_TAP_OUT",
        )
    )
