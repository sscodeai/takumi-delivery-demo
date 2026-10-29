#!/usr/bin/env python3
"""TAP integration suite for the delivered ``bash summary.sh``.

The contract under test is ``docs/requirements/intake.yaml``:

    run:          bash summary.sh {csv}
    region line:  <region> <count> <sum> <mean>
    total line:   TOTAL <count> <sum>
    skipped line: SKIPPED <skipped-count>

The checks here drive the real entry point in a subprocess, so what is asserted
is the behaviour a caller (and the delivery's reviewer) sees. The unit checks
live in ``tests/test_units.py`` and are pulled into the same TAP report. The
report is written to ``reports/tests.tap`` (override with ``TAP_OUT``) and
echoed to stdout; the process exits 0 only when every check passes.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_units import UNIT_TESTS  # noqa: E402 - unit checks share this report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "summary.sh")
TAP_OUT = os.environ.get("TAP_OUT", os.path.join(ROOT, "reports", "tests.tap"))
TIMEOUT = 30

MONEY = re.compile(r"^-?[0-9]+\.[0-9]{2}$")
TOTAL_LINE = re.compile(r"^TOTAL ([0-9]+) (-?[0-9]+\.[0-9]{2})$")
SKIPPED_LINE = re.compile(r"^SKIPPED ([0-9]+)$")

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


def run(args=None, cwd=None, stdin=None, env=None):
    command = ["bash", SCRIPT] + ([] if args is None else list(args))
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env=env,
    )


def lines_of(output):
    stripped = output.rstrip("\n")
    return stripped.split("\n") if stripped else []


def region_lines(output):
    return [
        line
        for line in lines_of(output)
        if not line.startswith("TOTAL ") and not line.startswith("SKIPPED ")
    ]


def report(text):
    proc = run([csv_file(text)])
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert proc.stderr == "", "unexpected stderr %r" % proc.stderr
    return lines_of(proc.stdout)


def expect(text, expected):
    got = report(text)
    assert got == expected, "got %r, want %r" % (got, expected)


def fail_report(text):
    """Run a file that must be a fatal error and return the process."""
    proc = run([csv_file(text)])
    assert proc.returncode != 0, "a fatal error must exit non-zero: %r" % proc.stdout
    assert proc.stdout == "", "no report line may be printed: %r" % proc.stdout
    assert proc.stderr.strip(), "a diagnostic on stderr is expected"
    return proc


def fields_of(line):
    """Split ``<region> <count> <sum> <mean>`` from the right."""
    parts = line.rsplit(" ", 3)
    assert len(parts) == 4, "not the declared shape: %r" % line
    return parts


SAMPLE = (
    "region,amount\n"
    "north,120.50\n"
    "south,80.00\n"
    "north,99.50\n"
    "east,45.25\n"
)
SAMPLE_REPORT = [
    "east 1 45.25 45.25",
    "north 2 220.00 110.00",
    "south 1 80.00 80.00",
    "TOTAL 4 345.25",
    "SKIPPED 0",
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
    proc = run([csv_file(SAMPLE)])
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)


def req_001_report_goes_to_stdout_not_stderr():
    proc = run([csv_file(SAMPLE)])
    assert proc.stdout == "\n".join(SAMPLE_REPORT) + "\n", "stdout %r" % proc.stdout
    assert proc.stderr == "", "stderr %r" % proc.stderr


def req_001_process_terminates_on_its_own():
    # `run` enforces TIMEOUT; a hung process raises TimeoutExpired and fails here.
    proc = run([csv_file(SAMPLE)])
    assert proc.returncode == 0


def req_001_runs_from_another_working_directory():
    path = csv_file(SAMPLE)
    proc = run([path], cwd=SANDBOX)
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert lines_of(proc.stdout) == SAMPLE_REPORT, "got %r" % lines_of(proc.stdout)


def req_001_relative_input_path_resolves_from_cwd():
    workdir = os.path.join(SANDBOX, "relative")
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "records.csv"), "w", encoding="utf-8") as handle:
        handle.write(SAMPLE)
    proc = run(["records.csv"], cwd=workdir)
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert lines_of(proc.stdout) == SAMPLE_REPORT, "got %r" % lines_of(proc.stdout)


def req_001_runs_without_an_install_or_build_step():
    # Only the interpreter and a shell are on PATH: no virtualenv, no node_modules.
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": SANDBOX,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    proc = run([csv_file(SAMPLE, "minimal-env.csv")], env=env)
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert lines_of(proc.stdout) == SAMPLE_REPORT, "got %r" % lines_of(proc.stdout)


def req_001_input_path_may_contain_spaces():
    proc = run([csv_file(SAMPLE, "records with spaces.csv")])
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert lines_of(proc.stdout) == SAMPLE_REPORT, "got %r" % lines_of(proc.stdout)


def req_001_missing_argument_is_a_usage_error():
    proc = run([])
    assert proc.returncode != 0, "a missing argument must not look like a success"
    assert proc.stdout == "", "no result line may be printed: %r" % proc.stdout
    assert "usage" in proc.stderr.lower(), "stderr %r" % proc.stderr


def req_001_extra_argument_is_rejected():
    proc = run([csv_file(SAMPLE), "stray"])
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


def req_001_undecodable_input_is_a_stop_error():
    path = os.path.join(SANDBOX, "undecodable.csv")
    with open(path, "wb") as handle:
        handle.write(b"region,amount\nnorth,\xff\n")
    proc = run([path])
    assert proc.returncode != 0, "an undecodable input must not look like a success"
    assert proc.stdout == "", "no result line may be printed: %r" % proc.stdout
    assert proc.stderr.strip(), "a diagnostic on stderr is expected"


def req_001_stdin_is_not_consulted():
    proc = run([csv_file(SAMPLE)], stdin="region,amount\nghost,1.00\n")
    assert lines_of(proc.stdout) == SAMPLE_REPORT, "got %r" % lines_of(proc.stdout)


# --- REQ-002: exactly region,amount; a wrong or missing header is fatal ------


def req_002_header_row_is_not_a_data_row():
    out = report(SAMPLE)
    assert all(fields_of(line)[0] != "region" for line in region_lines("\n".join(out))), out


def req_002_declared_header_is_accepted():
    expect(SAMPLE, SAMPLE_REPORT)


def req_002_header_is_trimmed_and_case_insensitive():
    variant = (
        " Region ,\tAMOUNT \n"
        "north,120.50\n"
        "south,80.00\n"
        "north,99.50\n"
        "east,45.25\n"
    )
    expect(variant, SAMPLE_REPORT)


def req_002_quoted_header_is_read_normally():
    expect('"region","amount"\nnorth,1.00\n', ["north 1 1.00 1.00", "TOTAL 1 1.00", "SKIPPED 0"])


def req_002_a_missing_header_is_fatal():
    # The deliverable sample is written without the header; REQ-002 makes a
    # headerless file fatal rather than guessing the columns.
    fail_report("north,120.50\nsouth,80.00\nnorth,99.50\neast,45.25\n")
    fail_report("")


def req_002_a_wrong_header_is_fatal():
    for text in (
        "amount,region\n120.50,north\n",
        "region,total\nnorth,120.50\n",
        "region,amount,note\nnorth,120.50,x\n",
        "region\nnorth\n",
    ):
        fail_report(text)


def req_002_header_only_file_is_an_empty_report():
    expect("region,amount\n", ["TOTAL 0 0.00", "SKIPPED 0"])


def req_002_a_quoted_comma_region_is_one_record():
    expect(
        'region,amount\n"North, East",100.00\n',
        ["North, East 1 100.00 100.00", "TOTAL 1 100.00", "SKIPPED 0"],
    )


def req_002_crlf_line_endings_are_accepted():
    expect(
        "region,amount\r\nnorth,1.00\r\nsouth,2.00\r\n",
        [
            "north 1 1.00 1.00",
            "south 1 2.00 2.00",
            "TOTAL 2 3.00",
            "SKIPPED 0",
        ],
    )


def req_002_utf8_bom_before_the_header_is_ignored():
    expect("\ufeffregion,amount\nnorth,1.00\n", ["north 1 1.00 1.00", "TOTAL 1 1.00", "SKIPPED 0"])


def req_002_a_missing_final_newline_is_accepted():
    expect("region,amount\nnorth,1.00", ["north 1 1.00 1.00", "TOTAL 1 1.00", "SKIPPED 0"])


# --- REQ-003: one sorted line per region -------------------------------------


def req_003_sample_report():
    expect(SAMPLE, SAMPLE_REPORT)


def req_003_three_distinct_regions_yield_three_lines():
    out = report("region,amount\nc,1\na,2\nb,3\n")
    assert len(region_lines("\n".join(out))) == 3, out


def req_003_exactly_one_line_per_region():
    out = report("region,amount\nnorth,1\nsouth,2\nnorth,3\n")
    names = [fields_of(line)[0] for line in region_lines("\n".join(out))]
    assert names == ["north", "south"], names
    assert len(names) == len(set(names)), names


def req_003_regions_are_sorted_by_utf8_bytes():
    out = report("region,amount\nb,1\nA,2\na,3\nB,4\n")
    names = [fields_of(line)[0] for line in region_lines("\n".join(out))]
    assert names == ["A", "B", "a", "b"], names
    # Byte 0xD0 sorts after every ASCII byte, so a Cyrillic region is last.
    out = report("region,amount\n\u0414,1\nz,2\n\u00c1,3\n")
    names = [fields_of(line)[0] for line in region_lines("\n".join(out))]
    assert names == ["z", "\u00c1", "\u0414"], names


def req_003_regions_are_trimmed_before_grouping_and_printing():
    expect(
        "region,amount\n  north\t,1.00\nnorth ,2.00\n",
        ["north 2 3.00 1.50", "TOTAL 2 3.00", "SKIPPED 0"],
    )


def req_003_regions_are_case_sensitive():
    out = report("region,amount\nNorth,10.00\nnorth,20.00\n")
    names = [fields_of(line)[0] for line in region_lines("\n".join(out))]
    assert names == ["North", "north"], names


def req_003_non_ascii_regions_survive():
    expect(
        "region,amount\ncaf\u00e9,1.00\n",
        ["caf\u00e9 1 1.00 1.00", "TOTAL 1 1.00", "SKIPPED 0"],
    )


def req_003_count_is_the_number_of_accepted_rows_in_the_group():
    out = report("region,amount\na,1\na,2\na,3\nb,4\n")
    counts = {fields_of(line)[0]: int(fields_of(line)[1]) for line in region_lines("\n".join(out))}
    assert counts == {"a": 3, "b": 1}, counts


def req_003_sum_and_mean_have_exactly_two_decimals():
    out = report(SAMPLE)
    for line in region_lines("\n".join(out)):
        region, count, total, mean = fields_of(line)
        assert count.isdigit(), line
        assert MONEY.match(total), line
        assert MONEY.match(mean), line


def req_003_mean_is_sum_over_count():
    out = report("region,amount\na,1.00\na,2.00\na,4.00\n")
    region, count, total, mean = fields_of(region_lines("\n".join(out))[0])
    assert (region, count, total, mean) == ("a", "3", "7.00", "2.33"), [region, count, total, mean]


# --- REQ-004: exactly one totals line, always printed ------------------------


def req_004_there_is_exactly_one_total_line():
    out = report(SAMPLE)
    totals = [line for line in out if line.startswith("TOTAL ")]
    assert len(totals) == 1, out


def req_004_total_line_shape_and_value():
    out = report(SAMPLE)
    assert out[-2] == "TOTAL 4 345.25", out
    match = TOTAL_LINE.match(out[-2])
    assert match, out[-2]
    assert match.group(1) == "4"
    assert MONEY.match(match.group(2))


def req_004_header_only_file_totals_zero():
    assert report("region,amount\n") == ["TOTAL 0 0.00", "SKIPPED 0"]


def req_004_total_count_is_the_sum_of_region_counts():
    out = report("region,amount\na,1\na,2\nb,3\nc,4\n")
    counts = [int(fields_of(line)[1]) for line in region_lines("\n".join(out))]
    total = TOTAL_LINE.match(out[-2])
    assert total and int(total.group(1)) == sum(counts), out


def req_004_total_sum_is_the_sum_of_the_accepted_amounts():
    text = "region,amount\na,10.25\nb,-2.50\na,1.00\nb,4.75\n"
    out = report(text)
    expected = Decimal("10.25") + Decimal("-2.50") + Decimal("1.00") + Decimal("4.75")
    total = TOTAL_LINE.match(out[-2])
    assert total, out
    assert Decimal(total.group(2)) == expected, (out, expected)


def req_004_total_includes_every_duplicate_row():
    out = report("region,amount\nsouth,50.00\nsouth,50.00\n")
    assert out == ["south 2 100.00 50.00", "TOTAL 2 100.00", "SKIPPED 0"], out


# --- REQ-005 / AMB-001: malformed rows are skipped and counted ---------------


def req_005_a_non_numeric_amount_is_counted_and_excluded():
    clean = "region,amount\nnorth,120.50\nsouth,80.00\n"
    dirty = "region,amount\nnorth,120.50\nsouth,abc\nsouth,80.00\n"
    assert report(dirty) == report(clean)[:-1] + ["SKIPPED 1"], report(dirty)


def req_005_every_malformed_shape_is_counted():
    text = (
        "region,amount\n"
        "ok,1.00\n"
        "short\n"                 # one field
        "ok,2.00,extra\n"         # three fields
        ",5.00\n"                 # empty region
        "   ,5.00\n"              # blank region after trimming
        "ok,\n"                   # empty amount
        "ok,abc\n"                # not a number
        "ok,1e3\n"                # exponent notation
        'ok,"1,000"\n'            # thousands separator (quoted)
        "ok,$5\n"                 # currency symbol
        "ok,5.\n"                 # no digits after the point
        "ok,.5\n"                 # no digits before the point
        "\n"                      # blank line: no fields
    )
    out = report(text)
    assert out[0] == "ok 1 1.00 1.00", out
    assert out[1] == "TOTAL 1 1.00", out
    assert out[2] == "SKIPPED 12", out


def req_005_clean_file_prints_skipped_zero():
    assert report(SAMPLE)[-1] == "SKIPPED 0"


def req_005_skipped_line_is_last_and_appears_once():
    out = report("region,amount\nok,1.00\nbad,abc\n")
    skipped = [line for line in out if line.startswith("SKIPPED ")]
    assert skipped == ["SKIPPED 1"], out
    assert out[-1].startswith("SKIPPED "), out


def req_005_all_rows_malformed_still_exits_zero():
    assert report("region,amount\nbad,abc\nalso-bad\n") == [
        "TOTAL 0 0.00",
        "SKIPPED 2",
    ]


def req_005_malformed_rows_do_not_change_any_aggregate():
    clean = report("region,amount\nnorth,10.00\nsouth,20.00\n")
    dirty = report(
        "region,amount\n"
        "north,10.00\n"
        "broken,abc\n"
        "broken\n"
        ",20.00\n"
        "south,20.00\n"
    )
    assert dirty[:-1] == clean[:-1], (dirty, clean)
    assert dirty[-1] == "SKIPPED 3", dirty


# --- REQ-006 / AMB-002: identical rows are independent orders ----------------


def req_006_identical_rows_each_count():
    expect(
        "region,amount\nsouth,50.00\nsouth,50.00\n",
        ["south 2 100.00 50.00", "TOTAL 2 100.00", "SKIPPED 0"],
    )


def req_006_three_identical_rows_each_count():
    expect(
        "region,amount\nsouth,50.00\nsouth,50.00\nsouth,50.00\n",
        ["south 3 150.00 50.00", "TOTAL 3 150.00", "SKIPPED 0"],
    )


def req_006_no_de_duplication():
    out = report("region,amount\na,1.00\na,1.00\n")
    assert fields_of(out[0])[1] == "2", out


# --- REQ-007 / AMB-003: two decimals, half-up, reproducible -----------------


def req_007_mean_of_ten_thirds_is_three_point_three_three():
    out = report("region,amount\nx,10.00\nx,0.00\nx,0.00\n")
    assert out[0] == "x 3 10.00 3.33", out


def req_007_two_point_zero_zero_five_rounds_up():
    out = report("region,amount\nx,2.005\n")
    assert out[0] == "x 1 2.01 2.01", out


def req_007_trailing_zeros_are_always_printed():
    out = report("region,amount\nx,100\n")
    assert out[0] == "x 1 100.00 100.00", out


def req_007_half_up_at_the_second_decimal():
    out = report("region,amount\nx,1.005\ny,1.015\nz,1.004\n")
    by_region = {fields_of(line)[0]: fields_of(line)[2] for line in region_lines("\n".join(out))}
    assert by_region == {"x": "1.01", "y": "1.02", "z": "1.00"}, by_region


def req_007_negative_halves_round_away_from_zero():
    out = report("region,amount\nx,-1.005\n")
    assert out[0] == "x 1 -1.01 -1.01", out


def req_007_repeated_runs_are_byte_identical():
    path = csv_file(SAMPLE)
    first = run([path])
    second = run([path])
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout


# --- REQ-008: zero and negative amounts are valid; regions are case-sensitive


def req_008_zero_and_negative_amounts_are_included():
    expect(
        "region,amount\neast,-10.00\neast,30.00\n",
        ["east 2 20.00 10.00", "TOTAL 2 20.00", "SKIPPED 0"],
    )


def req_008_zero_amount_counts():
    expect(
        "region,amount\nwest,0.00\n",
        ["west 1 0.00 0.00", "TOTAL 1 0.00", "SKIPPED 0"],
    )


def req_008_region_case_is_significant():
    out = report("region,amount\nNorth,10.00\nnorth,20.00\n")
    names = [fields_of(line)[0] for line in region_lines("\n".join(out))]
    assert names == ["North", "north"], names


# --- REQ-009: the report does not depend on row order ------------------------


def req_009_shuffled_rows_give_the_same_report():
    rows = ["north,120.50", "south,80.00", "north,99.50", "east,45.25"]
    ordered = report("region,amount\n" + "\n".join(rows) + "\n")
    shuffled = report("region,amount\n" + "\n".join(reversed(rows)) + "\n")
    assert ordered == shuffled, (ordered, shuffled)


def req_009_permutations_with_duplicates_and_bad_rows():
    rows = ["a,1.00", "b,2.00", "a,3.00", "bad,abc", "b,2.00"]
    first = report("region,amount\n" + "\n".join(rows) + "\n")
    second = report("region,amount\n" + "\n".join(rows[3:] + rows[:3]) + "\n")
    assert first == second, (first, second)


# --- REQ-010: the delivered suite runs from one documented command -----------


def req_010_run_tests_entry_point_exists():
    assert os.path.isfile(os.path.join(ROOT, "run-tests.sh")), "run-tests.sh is missing"


# --- additional contract checks ----------------------------------------------


def req_001_report_uses_only_the_declared_line_shapes():
    lines = report("region,amount\nnorth,1.00\nnorth,2.00\nbad,abc\n")
    assert len(lines) == 3, lines
    assert fields_of(lines[0])[1] == "2", lines
    assert TOTAL_LINE.match(lines[1]), lines
    assert SKIPPED_LINE.match(lines[2]), lines
    assert "" not in lines, lines


def req_002_a_two_field_data_row_is_accepted_not_mistaken_for_a_header():
    expect("region,amount\nnorth,1.00\n", ["north 1 1.00 1.00", "TOTAL 1 1.00", "SKIPPED 0"])


def req_003_region_with_inner_spaces_stays_one_group():
    expect(
        "region,amount\n  New York ,1.00\nNew York,2.00\n",
        ["New York 2 3.00 1.50", "TOTAL 2 3.00", "SKIPPED 0"],
    )


def req_003_a_numeric_region_is_still_a_region():
    expect("region,amount\n123,1.00\n007,2.00\n", ["007 1 2.00 2.00", "123 1 1.00 1.00", "TOTAL 2 3.00", "SKIPPED 0"])


def req_004_total_line_precedes_the_skipped_line():
    lines = report("region,amount\nnorth,1.00\nbad,abc\n")
    assert lines[-2].startswith("TOTAL "), lines
    assert lines[-1] == "SKIPPED 1", lines


def req_005_amount_with_a_surrounding_blank_is_malformed():
    expect("region,amount\nnorth, 1.00\n", ["TOTAL 0 0.00", "SKIPPED 1"])


def req_005_a_quoted_empty_amount_is_malformed():
    expect('region,amount\nnorth,""\n', ["TOTAL 0 0.00", "SKIPPED 1"])


def req_005_a_comma_only_row_is_malformed():
    expect("region,amount\n,\n", ["TOTAL 0 0.00", "SKIPPED 1"])


def req_006_repeated_rows_with_negative_amounts_each_count():
    expect(
        "region,amount\neast,-2.50\neast,-2.50\neast,-2.50\n",
        ["east 3 -7.50 -2.50", "TOTAL 3 -7.50", "SKIPPED 0"],
    )


def req_007_mean_uses_the_exact_sum():
    # Exact sum 1.005 prints as 1.01, but the mean is 0.5025 -> 0.50.
    expect("region,amount\nx,1.005\nx,0\n", ["x 2 1.01 0.50", "TOTAL 2 1.01", "SKIPPED 0"])


def req_007_sum_rounding_carries_into_the_whole():
    expect("region,amount\nx,0.995\n", ["x 1 1.00 1.00", "TOTAL 1 1.00", "SKIPPED 0"])


def req_007_a_large_amount_keeps_its_cents_exact():
    expect(
        "region,amount\nx,123456789.125\n",
        ["x 1 123456789.13 123456789.13", "TOTAL 1 123456789.13", "SKIPPED 0"],
    )


def req_008_a_negative_mean_keeps_its_sign():
    expect("region,amount\nwest,-9.00\n", ["west 1 -9.00 -9.00", "TOTAL 1 -9.00", "SKIPPED 0"])


def req_009_three_permutations_give_the_same_report():
    rows = ["north,1.00", "south,2.00", "north,3.00", "east,4.00"]
    reports = {
        tuple(report("region,amount\n" + "\n".join(order) + "\n"))
        for order in (rows, rows[2:] + rows[:2], list(reversed(rows)))
    }
    assert len(reports) == 1, reports


# --- independent recomputation (DIFF-001) ------------------------------------


def req_003_printed_aggregates_match_an_independent_recomputation():
    # DIFF-001: rebuild every region's count, sum and mean from the fixture
    # rows with decimal.Decimal, independently of summary.py's Fraction
    # arithmetic, and compare against what the tool printed (REQ-003).
    from decimal import Decimal, ROUND_HALF_UP

    rows = [
        ("north", "120.50"),
        ("north", "99.50"),
        ("south", "80.00"),
        ("east", "45.25"),
        ("North", "10.00"),
        ("east", "-10.00"),
        ("east", "30.00"),
        ("north", "0.005"),
    ]
    malformed = ["north,abc", "short", "   ,1.00", "ok,1e3"]
    text = (
        "region,amount\n"
        + "\n".join("%s,%s" % row for row in rows)
        + "\n"
        + "\n".join(malformed)
        + "\n"
    )

    expected = {}
    for region, amount in rows:
        count, total = expected.get(region, (0, Decimal(0)))
        expected[region] = (count + 1, total + Decimal(amount))

    want = []
    for region in sorted(expected, key=lambda name: name.encode("utf-8")):
        count, total = expected[region]
        mean = total / count
        want.append(
            "%s %d %s %s"
            % (
                region,
                count,
                total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                mean.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )
        )

    out = report(text)
    printed = region_lines("\n".join(out))
    assert printed == want, (printed, want)
    assert out[-1] == "SKIPPED %d" % len(malformed), out


def req_004_printed_region_sums_add_up_to_the_total_line():
    # REL-003 / REQ-004: adding the printed per-region counts and sums must
    # reproduce the printed TOTAL line (every amount here is exact at 2dp, so
    # no rounding slack is needed).
    from decimal import Decimal

    out = report(
        "region,amount\n"
        "north,120.50\n"
        "south,80.00\n"
        "north,99.50\n"
        "east,45.25\n"
        "east,-10.00\n"
        "North,10.00\n"
        "bad,abc\n"
    )
    groups = region_lines("\n".join(out))
    total = TOTAL_LINE.match(out[-2])
    assert total, out
    printed_sum = sum((Decimal(fields_of(line)[2]) for line in groups), Decimal(0))
    printed_count = sum(int(fields_of(line)[1]) for line in groups)
    assert Decimal(total.group(2)) == printed_sum, (out, printed_sum)
    assert int(total.group(1)) == printed_count, out


def req_009_all_permutations_of_a_small_fixture_are_identical():
    # REL-004 / REQ-009: every ordering of the same multiset, malformed row
    # included, must produce byte-identical stdout.
    from itertools import permutations

    rows = ["north,1.00", "south,2.00", "north,3.00", "bad,abc"]
    expected = None
    for order in permutations(rows):
        printed = tuple(report("region,amount\n" + "\n".join(order) + "\n"))
        if expected is None:
            expected = printed
        assert printed == expected, (order, printed, expected)


# --- the suite ---------------------------------------------------------------


TESTS = [
    ("req_001_entry_point_exists", req_001_entry_point_exists),
    ("req_001_entry_point_is_executable_with_shebang", req_001_entry_point_is_executable_with_shebang),
    ("req_001_valid_csv_exits_zero", req_001_valid_csv_exits_zero),
    ("req_001_report_goes_to_stdout_not_stderr", req_001_report_goes_to_stdout_not_stderr),
    ("req_001_process_terminates_on_its_own", req_001_process_terminates_on_its_own),
    ("req_001_runs_from_another_working_directory", req_001_runs_from_another_working_directory),
    ("req_001_relative_input_path_resolves_from_cwd", req_001_relative_input_path_resolves_from_cwd),
    ("req_001_runs_without_an_install_or_build_step", req_001_runs_without_an_install_or_build_step),
    ("req_001_input_path_may_contain_spaces", req_001_input_path_may_contain_spaces),
    ("req_001_missing_argument_is_a_usage_error", req_001_missing_argument_is_a_usage_error),
    ("req_001_extra_argument_is_rejected", req_001_extra_argument_is_rejected),
    ("req_001_missing_file_is_a_stop_error", req_001_missing_file_is_a_stop_error),
    ("req_001_directory_argument_is_a_stop_error", req_001_directory_argument_is_a_stop_error),
    ("req_001_undecodable_input_is_a_stop_error", req_001_undecodable_input_is_a_stop_error),
    ("req_001_stdin_is_not_consulted", req_001_stdin_is_not_consulted),
    ("req_002_header_row_is_not_a_data_row", req_002_header_row_is_not_a_data_row),
    ("req_002_declared_header_is_accepted", req_002_declared_header_is_accepted),
    ("req_002_header_is_trimmed_and_case_insensitive", req_002_header_is_trimmed_and_case_insensitive),
    ("req_002_quoted_header_is_read_normally", req_002_quoted_header_is_read_normally),
    ("req_002_a_missing_header_is_fatal", req_002_a_missing_header_is_fatal),
    ("req_002_a_wrong_header_is_fatal", req_002_a_wrong_header_is_fatal),
    ("req_002_header_only_file_is_an_empty_report", req_002_header_only_file_is_an_empty_report),
    ("req_002_a_quoted_comma_region_is_one_record", req_002_a_quoted_comma_region_is_one_record),
    ("req_002_crlf_line_endings_are_accepted", req_002_crlf_line_endings_are_accepted),
    ("req_002_utf8_bom_before_the_header_is_ignored", req_002_utf8_bom_before_the_header_is_ignored),
    ("req_002_a_missing_final_newline_is_accepted", req_002_a_missing_final_newline_is_accepted),
    ("req_003_sample_report", req_003_sample_report),
    ("req_003_three_distinct_regions_yield_three_lines", req_003_three_distinct_regions_yield_three_lines),
    ("req_003_exactly_one_line_per_region", req_003_exactly_one_line_per_region),
    ("req_003_regions_are_sorted_by_utf8_bytes", req_003_regions_are_sorted_by_utf8_bytes),
    ("req_003_regions_are_trimmed_before_grouping_and_printing", req_003_regions_are_trimmed_before_grouping_and_printing),
    ("req_003_regions_are_case_sensitive", req_003_regions_are_case_sensitive),
    ("req_003_non_ascii_regions_survive", req_003_non_ascii_regions_survive),
    ("req_003_count_is_the_number_of_accepted_rows_in_the_group", req_003_count_is_the_number_of_accepted_rows_in_the_group),
    ("req_003_sum_and_mean_have_exactly_two_decimals", req_003_sum_and_mean_have_exactly_two_decimals),
    ("req_003_mean_is_sum_over_count", req_003_mean_is_sum_over_count),
    ("req_004_there_is_exactly_one_total_line", req_004_there_is_exactly_one_total_line),
    ("req_004_total_line_shape_and_value", req_004_total_line_shape_and_value),
    ("req_004_header_only_file_totals_zero", req_004_header_only_file_totals_zero),
    ("req_004_total_count_is_the_sum_of_region_counts", req_004_total_count_is_the_sum_of_region_counts),
    ("req_004_total_sum_is_the_sum_of_the_accepted_amounts", req_004_total_sum_is_the_sum_of_the_accepted_amounts),
    ("req_004_total_includes_every_duplicate_row", req_004_total_includes_every_duplicate_row),
    ("req_005_a_non_numeric_amount_is_counted_and_excluded", req_005_a_non_numeric_amount_is_counted_and_excluded),
    ("req_005_every_malformed_shape_is_counted", req_005_every_malformed_shape_is_counted),
    ("req_005_clean_file_prints_skipped_zero", req_005_clean_file_prints_skipped_zero),
    ("req_005_skipped_line_is_last_and_appears_once", req_005_skipped_line_is_last_and_appears_once),
    ("req_005_all_rows_malformed_still_exits_zero", req_005_all_rows_malformed_still_exits_zero),
    ("req_005_malformed_rows_do_not_change_any_aggregate", req_005_malformed_rows_do_not_change_any_aggregate),
    ("req_006_identical_rows_each_count", req_006_identical_rows_each_count),
    ("req_006_three_identical_rows_each_count", req_006_three_identical_rows_each_count),
    ("req_006_no_de_duplication", req_006_no_de_duplication),
    ("req_007_mean_of_ten_thirds_is_three_point_three_three", req_007_mean_of_ten_thirds_is_three_point_three_three),
    ("req_007_two_point_zero_zero_five_rounds_up", req_007_two_point_zero_zero_five_rounds_up),
    ("req_007_trailing_zeros_are_always_printed", req_007_trailing_zeros_are_always_printed),
    ("req_007_half_up_at_the_second_decimal", req_007_half_up_at_the_second_decimal),
    ("req_007_negative_halves_round_away_from_zero", req_007_negative_halves_round_away_from_zero),
    ("req_007_repeated_runs_are_byte_identical", req_007_repeated_runs_are_byte_identical),
    ("req_008_zero_and_negative_amounts_are_included", req_008_zero_and_negative_amounts_are_included),
    ("req_008_zero_amount_counts", req_008_zero_amount_counts),
    ("req_008_region_case_is_significant", req_008_region_case_is_significant),
    ("req_009_shuffled_rows_give_the_same_report", req_009_shuffled_rows_give_the_same_report),
    ("req_009_permutations_with_duplicates_and_bad_rows", req_009_permutations_with_duplicates_and_bad_rows),
    ("req_010_run_tests_entry_point_exists", req_010_run_tests_entry_point_exists),
    ("req_001_report_uses_only_the_declared_line_shapes", req_001_report_uses_only_the_declared_line_shapes),
    ("req_002_a_two_field_data_row_is_accepted_not_mistaken_for_a_header", req_002_a_two_field_data_row_is_accepted_not_mistaken_for_a_header),
    ("req_003_region_with_inner_spaces_stays_one_group", req_003_region_with_inner_spaces_stays_one_group),
    ("req_003_a_numeric_region_is_still_a_region", req_003_a_numeric_region_is_still_a_region),
    ("req_004_total_line_precedes_the_skipped_line", req_004_total_line_precedes_the_skipped_line),
    ("req_005_amount_with_a_surrounding_blank_is_malformed", req_005_amount_with_a_surrounding_blank_is_malformed),
    ("req_005_a_quoted_empty_amount_is_malformed", req_005_a_quoted_empty_amount_is_malformed),
    ("req_005_a_comma_only_row_is_malformed", req_005_a_comma_only_row_is_malformed),
    ("req_006_repeated_rows_with_negative_amounts_each_count", req_006_repeated_rows_with_negative_amounts_each_count),
    ("req_007_mean_uses_the_exact_sum", req_007_mean_uses_the_exact_sum),
    ("req_007_sum_rounding_carries_into_the_whole", req_007_sum_rounding_carries_into_the_whole),
    ("req_007_a_large_amount_keeps_its_cents_exact", req_007_a_large_amount_keeps_its_cents_exact),
    ("req_008_a_negative_mean_keeps_its_sign", req_008_a_negative_mean_keeps_its_sign),
    ("req_009_three_permutations_give_the_same_report", req_009_three_permutations_give_the_same_report),
    ("req_003_printed_aggregates_match_an_independent_recomputation", req_003_printed_aggregates_match_an_independent_recomputation),
    ("req_004_printed_region_sums_add_up_to_the_total_line", req_004_printed_region_sums_add_up_to_the_total_line),
    ("req_009_all_permutations_of_a_small_fixture_are_identical", req_009_all_permutations_of_a_small_fixture_are_identical),
] + UNIT_TESTS


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
