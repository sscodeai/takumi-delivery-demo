#!/usr/bin/env python3
"""TAP test suite for the delivered ``bash summary.sh``.

The contract under test is ``docs/requirements/intake.yaml``:

    run:         bash summary.sh {csv}
    suite line:  <suite> <passed> <total> <percentage>
    total line:  TOTAL <tests>

Every check drives the real entry point in a subprocess, so what is asserted is
the behaviour a caller (and the delivery's reviewer) sees, not an internal
function. The report is written to ``reports/tests.tap`` (override with
``TAP_OUT``) and echoed to stdout; the process exits 0 only when every check
passes.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "summary.sh")
TAP_OUT = os.environ.get("TAP_OUT", os.path.join(ROOT, "reports", "tests.tap"))
TIMEOUT = 30

SUITE_LINE = re.compile(r"^([^ ]+) ([^ ]+) ([^ ]+) ([^ ]+)$")
ONE_DECIMAL = re.compile(r"^-?[0-9]+\.[0-9]$")

RESULTS = []
SANDBOX = tempfile.mkdtemp(prefix="summary-tests-")


def check(name, function):
    """Run one check and record its TAP point."""
    try:
        function()
    except AssertionError as exc:
        RESULTS.append((False, name, str(exc)))
    except Exception as exc:  # noqa: BLE001 - a crashing check is a failing check
        RESULTS.append((False, name, "%s: %s" % (type(exc).__name__, exc)))
    else:
        RESULTS.append((True, name, ""))


def csv_file(text, name="input.csv"):
    path = os.path.join(SANDBOX, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def run(args=None, cwd=None, stdin=None):
    command = ["bash", SCRIPT] + ([] if args is None else list(args))
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def lines_of(output):
    stripped = output.rstrip("\n")
    return stripped.split("\n") if stripped else []


def suite_lines(output):
    return [line for line in lines_of(output) if not line.startswith("TOTAL ")]


def total_lines(output):
    return [line for line in lines_of(output) if line.startswith("TOTAL ")]


def report(text):
    proc = run([csv_file(text)])
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert proc.stderr == "", "unexpected stderr %r" % proc.stderr
    return lines_of(proc.stdout)


def expect(text, expected):
    got = report(text)
    assert got == expected, "got %r, want %r" % (got, expected)


def percentage_of(text, suite):
    for line in suite_lines("\n".join(report(text))):
        fields = line.split(" ")
        if fields[0] == suite:
            return fields[3]
    raise AssertionError("no suite line for %r in %r" % (suite, text))


# The document's own sample rows, with the declared header. auth-service spans
# two rows: 48+2 passes out of 50+4 tests = 92.592...% -> 92.6.
BASE = (
    "suite,passed,total\n"
    "auth-service,48,50\n"
    "billing,12,12\n"
    "search,7,9\n"
    "auth-service,2,4\n"
)
BASE_REPORT = [
    "auth-service 50 54 92.6",
    "billing 12 12 100.0",
    "search 7 9 77.8",
    "TOTAL 75",
]


# --- REQ-001: the shell script is the single entry point -----------------------


def req_001_entry_point_exists():
    assert os.path.isfile(SCRIPT), "%s is not a file" % SCRIPT


def req_001_entry_point_is_executable_with_shebang():
    assert os.access(SCRIPT, os.X_OK), "%s is not executable" % SCRIPT
    with open(SCRIPT, encoding="utf-8") as handle:
        first = handle.readline().rstrip("\n")
    assert first.startswith("#!"), "no shebang: %r" % first


def req_001_valid_csv_exits_zero():
    proc = run([csv_file(BASE)])
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)


def req_001_report_goes_to_stdout_not_stderr():
    proc = run([csv_file(BASE)])
    assert proc.stdout == "\n".join(BASE_REPORT) + "\n", "stdout %r" % proc.stdout
    assert proc.stderr == "", "stderr %r" % proc.stderr


def req_001_process_terminates_on_its_own():
    # `run` enforces TIMEOUT; a hung process raises TimeoutExpired and fails here.
    proc = run([csv_file(BASE)])
    assert proc.returncode == 0


def req_001_runs_from_another_working_directory():
    path = csv_file(BASE)
    proc = run([path], cwd=SANDBOX)
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert lines_of(proc.stdout) == BASE_REPORT, "got %r" % lines_of(proc.stdout)


def req_001_relative_input_path_resolves_from_cwd():
    workdir = os.path.join(SANDBOX, "relative")
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "records.csv"), "w", encoding="utf-8") as handle:
        handle.write(BASE)
    proc = run(["records.csv"], cwd=workdir)
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert lines_of(proc.stdout) == BASE_REPORT, "got %r" % lines_of(proc.stdout)


def req_001_missing_argument_is_a_usage_error():
    proc = run([])
    assert proc.returncode != 0, "a missing argument must not look like a success"
    assert proc.stdout == "", "no result line may be printed: %r" % proc.stdout
    assert "usage" in proc.stderr.lower(), "stderr %r" % proc.stderr


def req_001_extra_argument_is_rejected():
    proc = run([csv_file(BASE), "stray"])
    assert proc.returncode != 0, "an extra argument must not look like a success"
    assert proc.stdout == "", "no result line may be printed: %r" % proc.stdout


def req_001_missing_file_is_a_stop_error():
    proc = run([os.path.join(SANDBOX, "does-not-exist.csv")])
    assert proc.returncode != 0, "a missing input must not exit 0"
    assert proc.stdout == "", "no result line may be printed: %r" % proc.stdout
    assert proc.stderr.strip(), "a diagnostic on stderr is expected"


def req_001_directory_argument_is_a_stop_error():
    proc = run([SANDBOX])
    assert proc.returncode != 0, "a directory is not a readable CSV"
    assert proc.stdout == "", "no result line may be printed: %r" % proc.stdout


def req_001_stdin_is_not_consulted():
    proc = run([csv_file(BASE)], stdin="suite,passed,total\nghost,1,1\n")
    assert lines_of(proc.stdout) == BASE_REPORT, "got %r" % lines_of(proc.stdout)


# --- REQ-002: the header is consumed and columns are located by name ----------


def req_002_header_row_is_not_a_data_row():
    out = report(BASE)
    assert all(line.split(" ")[0] != "suite" for line in suite_lines("\n".join(out))), out


def req_002_declared_column_order_is_the_report():
    expect(BASE, BASE_REPORT)


def req_002_reordered_columns_yield_the_same_report():
    reordered = (
        "total,suite,passed\n"
        "50,auth-service,48\n"
        "12,billing,12\n"
        "9,search,7\n"
        "4,auth-service,2\n"
    )
    expect(reordered, BASE_REPORT)


def req_002_header_cells_may_carry_blanks():
    spaced = (
        " suite , passed , total \n"
        "auth-service,48,50\n"
        "billing,12,12\n"
        "search,7,9\n"
        "auth-service,2,4\n"
    )
    expect(spaced, BASE_REPORT)


def req_002_header_names_are_case_insensitive():
    shouted = (
        "Suite,Passed,Total\n"
        "auth-service,48,50\n"
        "billing,12,12\n"
        "search,7,9\n"
        "auth-service,2,4\n"
    )
    expect(shouted, BASE_REPORT)


def req_002_headerless_sample_is_read_in_declared_order():
    # The document's input_format.sample carries no header row.
    sample = "auth-service,48,50\nbilling,12,12\nsearch,7,9\nauth-service,2,4\n"
    expect(sample, BASE_REPORT)


def req_002_header_only_file_reports_an_empty_total():
    expect("suite,passed,total\n", ["TOTAL 0"])


def req_002_a_data_row_is_not_mistaken_for_a_header():
    expect("suite,3,4\n", ["suite 3 4 75.0", "TOTAL 4"])


def req_002_extra_columns_after_the_declared_ones_are_ignored():
    expect(
        "suite,passed,total,note\n"
        "alpha,1,2,hello\n",
        ["alpha 1 2 50.0", "TOTAL 2"],
    )


# --- REQ-003: one line per distinct suite, first-appearance order -------------


def req_003_three_distinct_suites_yield_three_lines():
    out = report("suite,passed,total\nalpha,1,1\nbeta,1,1\ngamma,1,1\n")
    assert len(suite_lines("\n".join(out))) == 3, out


def req_003_a_repeated_suite_yields_one_line():
    out = report(BASE)
    tokens = [line.split(" ")[0] for line in suite_lines("\n".join(out))]
    assert tokens == ["auth-service", "billing", "search"], tokens
    assert len(tokens) == len(set(tokens)), tokens


def req_003_suites_are_in_first_appearance_order():
    out = report("suite,passed,total\nzeta,1,2\nalpha,1,2\nmu,1,2\n")
    tokens = [line.split(" ")[0] for line in suite_lines("\n".join(out))]
    assert tokens == ["zeta", "alpha", "mu"], tokens


def req_003_suite_names_are_not_case_folded():
    out = report("suite,passed,total\nAuth-Service,1,1\n")
    assert suite_lines("\n".join(out))[0].split(" ")[0] == "Auth-Service", out


def req_003_suite_names_are_echoed_verbatim():
    out = report("suite,passed,total\nsvc.api_v2-x,1,1\n")
    assert suite_lines("\n".join(out))[0].split(" ")[0] == "svc.api_v2-x", out


def req_003_non_ascii_suite_names_survive():
    out = report("suite,passed,total\ncaf\u00e9-\u00dcnit,1,1\n")
    assert suite_lines("\n".join(out))[0].split(" ")[0] == "caf\u00e9-\u00dcnit", out


def req_003_each_suite_line_carries_four_fields():
    for line in suite_lines("\n".join(report(BASE))):
        assert SUITE_LINE.match(line), "not the declared shape: %r" % line


def req_003_the_report_has_no_other_lines():
    for line in report(BASE):
        assert SUITE_LINE.match(line) or line.startswith("TOTAL "), "unexpected line %r" % line


def req_003_suite_lines_are_emitted_before_the_total():
    out = report(BASE)
    assert out[-1].startswith("TOTAL "), out
    assert all(not line.startswith("TOTAL ") for line in out[:-1]), out


# --- REQ-004: percentage in points, one decimal, half away from zero ----------


def req_004_declared_examples():
    out = report("suite,passed,total\na,48,50\nb,12,12\nc,1,3\n")
    assert out == ["a 48 50 96.0", "b 12 12 100.0", "c 1 3 33.3", "TOTAL 65"], out


def req_004_percentage_always_has_exactly_one_decimal():
    out = report("suite,passed,total\na,0,5\nb,5,5\nc,2,3\nd,1,8\n")
    for line in suite_lines("\n".join(out)):
        token = line.split(" ")[3]
        assert ONE_DECIMAL.match(token), "token %r is not one decimal" % token


def req_004_percentage_is_in_points_not_a_fraction():
    assert percentage_of(BASE, "auth-service") == "92.6"


def req_004_zero_percent_is_zero_point_zero():
    assert percentage_of("suite,passed,total\na,0,5\n", "a") == "0.0"


def req_004_a_full_pass_is_one_hundred():
    assert percentage_of("suite,passed,total\na,7,7\n", "a") == "100.0"


def req_004_thirds_round_to_one_decimal():
    assert percentage_of("suite,passed,total\na,2,3\n", "a") == "66.7"
    assert percentage_of("suite,passed,total\na,1,6\n", "a") == "16.7"


# AMB-001: exact halves round away from zero, at the one-decimal boundary.
def amb_001_exact_half_rounds_up():
    assert percentage_of("suite,passed,total\na,1,16\n", "a") == "6.3"  # 6.25
    assert percentage_of("suite,passed,total\na,127,2000\n", "a") == "6.4"  # 6.35
    assert percentage_of("suite,passed,total\na,123,2000\n", "a") == "6.2"  # 6.15
    assert percentage_of("suite,passed,total\na,9,400\n", "a") == "2.3"  # 2.25


def amb_001_exact_half_rounds_up_near_one_hundred():
    assert percentage_of("suite,passed,total\na,1999,2000\n", "a") == "100.0"  # 99.95


def amb_001_exact_half_rounds_up_near_zero():
    assert percentage_of("suite,passed,total\na,1,2000\n", "a") == "0.1"  # 0.05


def amb_001_non_half_values_round_normally():
    assert percentage_of("suite,passed,total\na,1,32\n", "a") == "3.1"  # 3.125
    assert percentage_of("suite,passed,total\na,1,8\n", "a") == "12.5"
    assert percentage_of("suite,passed,total\na,3,8\n", "a") == "37.5"
    assert percentage_of("suite,passed,total\na,1,3\n", "a") == "33.3"


def req_004_large_counts_keep_the_exact_ratio():
    assert percentage_of("suite,passed,total\na,1000000,2000000\n", "a") == "50.0"


# --- REQ-005: exactly one TOTAL line, the summed denominator ------------------


def req_005_total_is_the_sum_of_printed_denominators():
    out = report(BASE)
    denominators = [int(line.split(" ")[2]) for line in suite_lines("\n".join(out))]
    assert sum(denominators) == 75, denominators
    assert total_lines("\n".join(out)) == ["TOTAL 75"], out


def req_005_there_is_exactly_one_total_line():
    assert len(total_lines("\n".join(report(BASE)))) == 1


def req_005_total_is_the_last_line():
    assert report(BASE)[-1] == "TOTAL 75"


def req_005_header_only_file_total_is_zero():
    assert report("suite,passed,total\n") == ["TOTAL 0"]


def req_005_single_suite_total():
    assert report("suite,passed,total\na,3,4\n") == ["a 3 4 75.0", "TOTAL 4"]


def req_005_total_sums_every_occurrence_of_a_merged_suite():
    out = report("suite,passed,total\na,1,2\na,1,2\n")
    assert out == ["a 2 4 50.0", "TOTAL 4"], out


# --- AMB-002: repeated suites merge into one summed line ---------------------


def amb_002_merge_sums_passed_and_total():
    assert report(BASE)[0] == "auth-service 50 54 92.6"


def amb_002_merge_is_not_the_last_row():
    out = report("suite,passed,total\ndup,9,10\ndup,1,10\n")
    assert out == ["dup 10 20 50.0", "TOTAL 20"], out


def amb_002_merge_is_not_the_first_row():
    out = report("suite,passed,total\ndup,1,10\ndup,9,10\n")
    assert out == ["dup 10 20 50.0", "TOTAL 20"], out


def amb_002_merge_over_three_occurrences():
    out = report("suite,passed,total\ndup,1,2\ndup,1,2\ndup,2,4\n")
    assert out == ["dup 4 8 50.0", "TOTAL 8"], out


def amb_002_merge_still_prints_one_line():
    lines = suite_lines("\n".join(report("suite,passed,total\ndup,1,2\ndup,1,2\ndup,2,4\n")))
    assert lines == ["dup 4 8 50.0"], lines


def amb_002_merge_keeps_first_appearance_order():
    out = report("suite,passed,total\nzeta,1,2\nalpha,1,2\nzeta,1,2\n")
    tokens = [line.split(" ")[0] for line in suite_lines("\n".join(out))]
    assert tokens == ["zeta", "alpha"], tokens


# --- AMB-003: a row that cannot yield a percentage is skipped silently -------


def amb_003_non_numeric_passed_row_is_skipped():
    out = report("suite,passed,total\nok,1,2\nbad,abc,10\n")
    assert out == ["ok 1 2 50.0", "TOTAL 2"], out


def amb_003_non_numeric_total_row_is_skipped():
    out = report("suite,passed,total\nok,1,2\nbad,5,xyz\n")
    assert out == ["ok 1 2 50.0", "TOTAL 2"], out


def amb_003_zero_total_row_is_skipped():
    out = report("suite,passed,total\nok,1,2\nbad,5,0\n")
    assert out == ["ok 1 2 50.0", "TOTAL 2"], out


def amb_003_short_row_is_skipped():
    out = report("suite,passed,total\nok,1,2\nbad,5\n")
    assert out == ["ok 1 2 50.0", "TOTAL 2"], out


def amb_003_blank_line_is_skipped():
    out = report("suite,passed,total\nok,1,2\n\n")
    assert out == ["ok 1 2 50.0", "TOTAL 2"], out


def amb_003_blank_suite_id_is_skipped():
    out = report("suite,passed,total\nok,1,2\n,5,10\n")
    assert out == ["ok 1 2 50.0", "TOTAL 2"], out


def amb_003_negative_counts_are_skipped():
    out = report("suite,passed,total\nok,1,2\nbad,-5,10\n")
    assert out == ["ok 1 2 50.0", "TOTAL 2"], out


def amb_003_skipped_rows_do_not_change_any_aggregate():
    clean = (
        "suite,passed,total\n"
        "auth-service,48,50\n"
        "billing,12,12\n"
        "search,7,9\n"
        "auth-service,2,4\n"
    )
    dirty = (
        "suite,passed,total\n"
        "auth-service,48,50\n"
        "billing,12,12\n"
        "search,7,9\n"
        "broken,abc,3\n"
        "broken,4\n"
        "auth-service,2,4\n"
        "zero,3,0\n"
    )
    assert report(dirty) == report(clean), report(dirty)


def amb_003_a_suite_with_only_bad_rows_is_absent():
    out = "\n".join(report("suite,passed,total\nok,1,2\nbad,abc,10\n"))
    assert "bad" not in out.split("\n")[0], out
    assert len(out.split("\n")) == 2, out


def amb_003_all_rows_bad_still_exits_zero_with_total_zero():
    assert report("suite,passed,total\nbad,abc,10\nalso-bad,1\n") == ["TOTAL 0"]


def amb_003_no_skipped_counter_is_printed():
    out = "\n".join(report("suite,passed,total\nok,1,2\nbad,abc,10\n"))
    assert "SKIPPED" not in out.upper(), out
    assert "skipped" not in out, out


# --- the suite -----------------------------------------------------------------


TESTS = [
    ("req_001_entry_point_exists", req_001_entry_point_exists),
    ("req_001_entry_point_is_executable_with_shebang", req_001_entry_point_is_executable_with_shebang),
    ("req_001_valid_csv_exits_zero", req_001_valid_csv_exits_zero),
    ("req_001_report_goes_to_stdout_not_stderr", req_001_report_goes_to_stdout_not_stderr),
    ("req_001_process_terminates_on_its_own", req_001_process_terminates_on_its_own),
    ("req_001_runs_from_another_working_directory", req_001_runs_from_another_working_directory),
    ("req_001_relative_input_path_resolves_from_cwd", req_001_relative_input_path_resolves_from_cwd),
    ("req_001_missing_argument_is_a_usage_error", req_001_missing_argument_is_a_usage_error),
    ("req_001_extra_argument_is_rejected", req_001_extra_argument_is_rejected),
    ("req_001_missing_file_is_a_stop_error", req_001_missing_file_is_a_stop_error),
    ("req_001_directory_argument_is_a_stop_error", req_001_directory_argument_is_a_stop_error),
    ("req_001_stdin_is_not_consulted", req_001_stdin_is_not_consulted),
    ("req_002_header_row_is_not_a_data_row", req_002_header_row_is_not_a_data_row),
    ("req_002_declared_column_order_is_the_report", req_002_declared_column_order_is_the_report),
    ("req_002_reordered_columns_yield_the_same_report", req_002_reordered_columns_yield_the_same_report),
    ("req_002_header_cells_may_carry_blanks", req_002_header_cells_may_carry_blanks),
    ("req_002_header_names_are_case_insensitive", req_002_header_names_are_case_insensitive),
    ("req_002_headerless_sample_is_read_in_declared_order", req_002_headerless_sample_is_read_in_declared_order),
    ("req_002_header_only_file_reports_an_empty_total", req_002_header_only_file_reports_an_empty_total),
    ("req_002_a_data_row_is_not_mistaken_for_a_header", req_002_a_data_row_is_not_mistaken_for_a_header),
    ("req_002_extra_columns_after_the_declared_ones_are_ignored", req_002_extra_columns_after_the_declared_ones_are_ignored),
    ("req_003_three_distinct_suites_yield_three_lines", req_003_three_distinct_suites_yield_three_lines),
    ("req_003_a_repeated_suite_yields_one_line", req_003_a_repeated_suite_yields_one_line),
    ("req_003_suites_are_in_first_appearance_order", req_003_suites_are_in_first_appearance_order),
    ("req_003_suite_names_are_not_case_folded", req_003_suite_names_are_not_case_folded),
    ("req_003_suite_names_are_echoed_verbatim", req_003_suite_names_are_echoed_verbatim),
    ("req_003_non_ascii_suite_names_survive", req_003_non_ascii_suite_names_survive),
    ("req_003_each_suite_line_carries_four_fields", req_003_each_suite_line_carries_four_fields),
    ("req_003_the_report_has_no_other_lines", req_003_the_report_has_no_other_lines),
    ("req_003_suite_lines_are_emitted_before_the_total", req_003_suite_lines_are_emitted_before_the_total),
    ("req_004_declared_examples", req_004_declared_examples),
    ("req_004_percentage_always_has_exactly_one_decimal", req_004_percentage_always_has_exactly_one_decimal),
    ("req_004_percentage_is_in_points_not_a_fraction", req_004_percentage_is_in_points_not_a_fraction),
    ("req_004_zero_percent_is_zero_point_zero", req_004_zero_percent_is_zero_point_zero),
    ("req_004_a_full_pass_is_one_hundred", req_004_a_full_pass_is_one_hundred),
    ("req_004_thirds_round_to_one_decimal", req_004_thirds_round_to_one_decimal),
    ("amb_001_exact_half_rounds_up", amb_001_exact_half_rounds_up),
    ("amb_001_exact_half_rounds_up_near_one_hundred", amb_001_exact_half_rounds_up_near_one_hundred),
    ("amb_001_exact_half_rounds_up_near_zero", amb_001_exact_half_rounds_up_near_zero),
    ("amb_001_non_half_values_round_normally", amb_001_non_half_values_round_normally),
    ("req_004_large_counts_keep_the_exact_ratio", req_004_large_counts_keep_the_exact_ratio),
    ("req_005_total_is_the_sum_of_printed_denominators", req_005_total_is_the_sum_of_printed_denominators),
    ("req_005_there_is_exactly_one_total_line", req_005_there_is_exactly_one_total_line),
    ("req_005_total_is_the_last_line", req_005_total_is_the_last_line),
    ("req_005_header_only_file_total_is_zero", req_005_header_only_file_total_is_zero),
    ("req_005_single_suite_total", req_005_single_suite_total),
    ("req_005_total_sums_every_occurrence_of_a_merged_suite", req_005_total_sums_every_occurrence_of_a_merged_suite),
    ("amb_002_merge_sums_passed_and_total", amb_002_merge_sums_passed_and_total),
    ("amb_002_merge_is_not_the_last_row", amb_002_merge_is_not_the_last_row),
    ("amb_002_merge_is_not_the_first_row", amb_002_merge_is_not_the_first_row),
    ("amb_002_merge_over_three_occurrences", amb_002_merge_over_three_occurrences),
    ("amb_002_merge_still_prints_one_line", amb_002_merge_still_prints_one_line),
    ("amb_002_merge_keeps_first_appearance_order", amb_002_merge_keeps_first_appearance_order),
    ("amb_003_non_numeric_passed_row_is_skipped", amb_003_non_numeric_passed_row_is_skipped),
    ("amb_003_non_numeric_total_row_is_skipped", amb_003_non_numeric_total_row_is_skipped),
    ("amb_003_zero_total_row_is_skipped", amb_003_zero_total_row_is_skipped),
    ("amb_003_short_row_is_skipped", amb_003_short_row_is_skipped),
    ("amb_003_blank_line_is_skipped", amb_003_blank_line_is_skipped),
    ("amb_003_blank_suite_id_is_skipped", amb_003_blank_suite_id_is_skipped),
    ("amb_003_negative_counts_are_skipped", amb_003_negative_counts_are_skipped),
    ("amb_003_skipped_rows_do_not_change_any_aggregate", amb_003_skipped_rows_do_not_change_any_aggregate),
    ("amb_003_a_suite_with_only_bad_rows_is_absent", amb_003_a_suite_with_only_bad_rows_is_absent),
    ("amb_003_all_rows_bad_still_exits_zero_with_total_zero", amb_003_all_rows_bad_still_exits_zero_with_total_zero),
    ("amb_003_no_skipped_counter_is_printed", amb_003_no_skipped_counter_is_printed),
]


def emit_tap():
    lines = ["TAP version 13", "1..%d" % len(RESULTS)]
    passed = failed = 0
    for index, (ok, name, detail) in enumerate(RESULTS, 1):
        if ok:
            passed += 1
            lines.append("ok %d - %s" % (index, name))
        else:
            failed += 1
            lines.append("not ok %d - %s" % (index, name))
            for part in (detail or "assertion failed").splitlines():
                lines.append("# %s" % part)
    lines.append("# tests %d" % len(RESULTS))
    lines.append("# pass %d" % passed)
    lines.append("# fail %d" % failed)
    text = "\n".join(lines) + "\n"
    directory = os.path.dirname(TAP_OUT)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(TAP_OUT, "w", encoding="utf-8") as handle:
        handle.write(text)
    sys.stdout.write(text)
    return 1 if failed else 0


def main():
    try:
        for name, function in TESTS:
            check(name, function)
        return emit_tap()
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
