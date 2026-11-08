#!/usr/bin/env python3
"""TAP suite for the delivered ``bash summary.sh``.

The contract under test is ``docs/requirements/intake.yaml``:

    run:          bash summary.sh {csv}
    region line:  <region> <revenue> <average_order_value>
    skipped line: SKIPPED <skipped-count>
    total line:   TOTAL <revenue> <orders>

Every check drives the real entry point in a subprocess, so what is asserted is
behaviour a caller sees. The report is written to ``reports/tests.tap``
(override with ``TAP_OUT``) and echoed to stdout; the process exits 0 only when
every check passes.
"""

import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from decimal import Decimal, ROUND_HALF_UP, localcontext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "summary.sh")
TAP_OUT = os.environ.get("TAP_OUT", os.path.join(ROOT, "reports", "tests.tap"))
TIMEOUT = 30

NUMBER = re.compile(r"^-?[0-9]+\.[0-9]{2}$")
SKIPPED_LINE = re.compile(r"^SKIPPED ([0-9]+)$")
TOTAL_LINE = re.compile(r"^TOTAL (-?[0-9]+\.[0-9]{2}) ([0-9]+)$")

SAMPLE = (
    "region,amount\n"
    "north,100.00\n"
    "south,50.00\n"
    "north,25.50\n"
    "east,10.25\n"
)
SAMPLE_REPORT = [
    "east 10.25 10.25",
    "north 125.50 62.75",
    "south 50.00 50.00",
    "SKIPPED 0",
    "TOTAL 185.75 4",
]

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


def write_text(text, name="input.csv"):
    path = os.path.join(SANDBOX, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def write_bytes(data, name="input.bin"):
    path = os.path.join(SANDBOX, name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def run_path(path, *extra):
    return subprocess.run(
        ["bash", SCRIPT, path, *extra],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def run_text(text, name="input.csv"):
    return run_path(write_text(text, name))


def parse_report(stdout):
    """Split report lines into (regions, skipped, total, raw_lines)."""
    regions = {}
    skipped = None
    total = None
    lines = stdout.splitlines()
    for line in lines:
        match = SKIPPED_LINE.match(line)
        if match:
            assert skipped is None, "more than one SKIPPED line"
            skipped = int(match.group(1))
            continue
        match = TOTAL_LINE.match(line)
        if match:
            assert total is None, "more than one TOTAL line"
            total = (match.group(1), int(match.group(2)))
            continue
        parts = line.rsplit(" ", 2)
        assert len(parts) == 3, "unexpected report line: %r" % line
        region, revenue, average = parts
        assert region not in regions, "region printed twice: %r" % region
        assert NUMBER.match(revenue), "bad revenue: %r" % revenue
        assert NUMBER.match(average), "bad average: %r" % average
        regions[region] = (revenue, average)
    return regions, skipped, total, lines


def report_of(text):
    proc = run_text(text)
    assert proc.returncode == 0, "exit %d: %s" % (proc.returncode, proc.stderr)
    assert proc.stderr == "", "stderr was not empty: %r" % proc.stderr
    return parse_report(proc.stdout)


def header(*names):
    return ",".join(names) + "\n"


# --------------------------------------------------------------------------
# REQ-001: entry point
# --------------------------------------------------------------------------


def req_001_declared_sample_report_is_exact():
    proc = run_text(SAMPLE)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == SAMPLE_REPORT, proc.stdout
    assert proc.stderr == ""


def req_001_entry_point_sits_at_the_repository_root():
    assert os.path.isfile(SCRIPT), SCRIPT
    assert os.access(SCRIPT, os.R_OK)


def req_001_reads_the_csv_named_by_the_first_argument():
    first = write_text(SAMPLE, "first.csv")
    second = write_text(header("region", "amount") + "west,3.00\n", "second.csv")
    proc = run_path(first)
    assert proc.returncode == 0, proc.stderr
    assert "north 125.50 62.75" in proc.stdout
    assert "west" not in proc.stdout
    assert os.path.isfile(second)


def req_001_relative_path_works_from_the_repository_root():
    handle, path = tempfile.mkstemp(dir=ROOT, suffix=".csv")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(SAMPLE)
        proc = subprocess.run(
            ["bash", "summary.sh", os.path.basename(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.splitlines() == SAMPLE_REPORT
    finally:
        os.unlink(path)


def req_001_missing_argument_is_a_usage_error():
    proc = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, timeout=TIMEOUT
    )
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


def req_001_extra_argument_is_rejected():
    path = write_text(SAMPLE)
    proc = run_path(path, "extra")
    assert proc.returncode != 0
    assert proc.stdout == ""


def req_001_a_well_formed_run_writes_nothing_to_stderr():
    proc = run_text(SAMPLE)
    assert proc.returncode == 0
    assert proc.stderr == ""


# --------------------------------------------------------------------------
# REQ-002: header mapping
# --------------------------------------------------------------------------


def req_002_swapped_header_columns_produce_the_same_report():
    swapped = (
        "amount,region\n"
        "100.00,north\n"
        "50.00,south\n"
        "25.50,north\n"
        "10.25,east\n"
    )
    left = run_text(SAMPLE, "a.csv")
    right = run_text(swapped, "b.csv")
    assert left.returncode == 0 and right.returncode == 0
    assert left.stdout == right.stdout


def req_002_extra_header_columns_are_followed_by_name():
    text = (
        "note,amount,region\n"
        "x,100.00,north\n"
        "y,5.50,north\n"
    )
    regions, skipped, total, _ = report_of(text)
    assert regions == {"north": ("105.50", "52.75")}
    assert skipped == 0
    assert total == ("105.50", 2)


def req_002_header_names_tolerate_blank_and_case_variation():
    text = " Region , AMOUNT \nnorth,4.00\n"
    regions, skipped, total, _ = report_of(text)
    assert regions == {"north": ("4.00", "4.00")}
    assert skipped == 0
    assert total == ("4.00", 1)


def req_002_missing_region_header_is_fatal():
    proc = run_text("amount\n1.00\n")
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


def req_002_missing_amount_header_is_fatal():
    proc = run_text("region\nnorth\n")
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


# --------------------------------------------------------------------------
# REQ-003: per-region lines
# --------------------------------------------------------------------------


def req_003_one_line_per_present_region_and_no_absent_region():
    regions, _, _, _ = report_of(SAMPLE)
    assert set(regions) == {"east", "north", "south"}


def req_003_revenue_is_the_region_sum():
    text = header("region", "amount") + "north,12.34\nnorth,0.66\nnorth,-3.00\n"
    regions, _, _, _ = report_of(text)
    assert regions["north"][0] == "10.00"


def req_003_average_divides_the_region_sum_by_its_count():
    text = header("region", "amount") + "north,1.00\nnorth,2.00\nnorth,4.00\n"
    regions, _, _, _ = report_of(text)
    assert regions["north"] == ("7.00", "2.33")


# --------------------------------------------------------------------------
# REQ-004: totals line
# --------------------------------------------------------------------------


def req_004_exactly_one_totals_line():
    proc = run_text(SAMPLE)
    assert proc.stdout.count("TOTAL ") == 1


def req_004_totals_revenue_equals_the_sum_of_printed_region_revenues():
    text = header("region", "amount") + "a,0.005\nb,0.005\nc,1.10\n"
    regions, _, total, _ = report_of(text)
    cents = sum(int(round(float(value[0]) * 100)) for value in regions.values())
    assert Decimal(total[0]) == Decimal(cents) / 100
    assert total[0] == "1.12"  # 0.01 + 0.01 + 1.10, the printed values


def req_004_order_count_equals_counted_rows():
    text = header("region", "amount") + "a,1\nb,2\na,3\nbad,x\n"
    regions, skipped, total, _ = report_of(text)
    assert skipped == 1
    assert total[1] == 3
    assert total[1] == 2 + 1


def req_004_totals_line_is_printed_after_skipped():
    _, _, _, lines = report_of(SAMPLE)
    assert lines[-2].startswith("SKIPPED ")
    assert lines[-1].startswith("TOTAL ")


# --------------------------------------------------------------------------
# REQ-005 / AMB-001: skip and count malformed rows
# --------------------------------------------------------------------------


def req_005_three_valid_two_malformed_rows_are_aggregated_and_counted():
    text = (
        header("region", "amount")
        + "north,10.00\n"
        + "broken,not-a-number\n"
        + "south,5.00\n"
        + ",7.00\n"
        + "east,2.00\n"
    )
    regions, skipped, total, _ = report_of(text)
    assert regions == {
        "east": ("2.00", "2.00"),
        "north": ("10.00", "10.00"),
        "south": ("5.00", "5.00"),
    }
    assert skipped == 2
    assert total == ("17.00", 3)


def req_005_all_malformed_rows_exit_zero():
    text = header("region", "amount") + "only-one-field\n,1.00\nnorth,abc\n"
    proc = run_text(text)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["SKIPPED 3", "TOTAL 0.00 0"]


def req_005_clean_file_prints_skipped_zero():
    _, skipped, _, _ = report_of(SAMPLE)
    assert skipped == 0


def req_005_wrong_field_count_rows_are_malformed():
    text = header("region", "amount") + "north\nsouth,1.00,extra\neast,2.00\n"
    regions, skipped, total, _ = report_of(text)
    assert regions == {"east": ("2.00", "2.00")}
    assert skipped == 2
    assert total == ("2.00", 1)


def req_005_blank_region_rows_are_malformed():
    text = header("region", "amount") + ",1.00\n   ,2.00\neast,3.00\n"
    regions, skipped, _, _ = report_of(text)
    assert regions == {"east": ("3.00", "3.00")}
    assert skipped == 2


def req_005_non_numeric_amounts_are_malformed():
    bad = ["abc", "1e3", "$5.00", "5%", "", "1.2.3", "--1", " 5", "1 000"]
    text = header("region", "amount") + "".join("north,%s\n" % value for value in bad)
    regions, skipped, total, _ = report_of(text)
    assert regions == {}
    assert skipped == len(bad)
    assert total == ("0.00", 0)


def req_005_plain_decimal_shapes_are_accepted():
    text = (
        header("region", "amount")
        + "north,1\n"
        + "north,+1.5\n"
        + "north,-2\n"
        + "north,.5\n"
        + "north,3.\n"
        + "north,0.00\n"
    )
    regions, skipped, total, _ = report_of(text)
    assert skipped == 0
    assert total[1] == 6
    assert regions["north"][0] == "4.00"


def req_005_a_blank_physical_line_is_a_wrong_field_count_row():
    text = header("region", "amount") + "north,1.00\n\n"
    regions, skipped, total, _ = report_of(text)
    assert regions == {"north": ("1.00", "1.00")}
    assert skipped == 1
    assert total == ("1.00", 1)


# --------------------------------------------------------------------------
# REQ-006 / AMB-002: duplicates merge
# --------------------------------------------------------------------------


def req_006_duplicate_row_counts_twice():
    base = header("region", "amount") + "north,10.00\nsouth,4.00\n"
    doubled = header("region", "amount") + "north,10.00\nsouth,4.00\nnorth,10.00\n"
    base_regions, _, base_total, _ = report_of(base)
    dup_regions, _, dup_total, _ = report_of(doubled)
    assert base_regions["north"] == ("10.00", "10.00")
    assert dup_regions["north"] == ("20.00", "10.00")
    assert dup_total[1] == base_total[1] + 1


def req_006_repeated_region_is_one_line():
    text = header("region", "amount") + "".join(
        "north,%d.00\n" % index for index in range(20)
    )
    _, _, _, lines = report_of(text)
    assert sum(1 for line in lines if line.startswith("north ")) == 1


# --------------------------------------------------------------------------
# REQ-007 / AMB-003: formatting and half-up rounding
# --------------------------------------------------------------------------


def req_007_single_amount_0_125_rounds_up():
    text = header("region", "amount") + "north,0.125\n"
    regions, _, total, _ = report_of(text)
    assert regions["north"] == ("0.13", "0.13")
    assert total[0] == "0.13"


def req_007_single_amount_2_674_rounds_down():
    text = header("region", "amount") + "north,2.674\n"
    regions, _, _, _ = report_of(text)
    assert regions["north"][0] == "2.67"


def req_007_negative_half_rounds_away_from_zero():
    text = header("region", "amount") + "north,-0.125\n"
    regions, _, _, _ = report_of(text)
    assert regions["north"] == ("-0.13", "-0.13")


def req_007_average_rounds_from_the_unrounded_sum():
    text = header("region", "amount") + "north,0.01\nnorth,0.02\n"
    regions, _, _, _ = report_of(text)
    assert regions["north"] == ("0.03", "0.02")


def req_007_negative_average_half_rounds_away_from_zero():
    text = header("region", "amount") + "north,-0.01\nnorth,0.00\n"
    regions, _, _, _ = report_of(text)
    assert regions["north"] == ("-0.01", "-0.01")


def req_007_integer_and_one_decimal_amounts_print_two_decimals():
    text = header("region", "amount") + "north,5\nnorth,1.5\n"
    regions, _, total, _ = report_of(text)
    assert regions["north"] == ("6.50", "3.25")
    assert total[0] == "6.50"


def req_007_every_printed_number_matches_the_shape():
    text = header("region", "amount") + "north,1\nsouth,-2.5\neast,0\nbad,x\n"
    proc = run_text(text)
    assert proc.returncode == 0
    for line in proc.stdout.splitlines():
        if line.startswith("SKIPPED "):
            continue
        if line.startswith("TOTAL "):
            values = line.split()[1:2]  # the order count is an integer
        else:
            values = line.rsplit(" ", 2)[1:]
        for value in values:
            assert NUMBER.match(value), "bad number %r in %r" % (value, line)


def req_007_no_negative_zero_is_printed():
    text = header("region", "amount") + "north,-0.001\neast,-0.00\n"
    proc = run_text(text)
    assert proc.returncode == 0
    assert "-0.00" not in proc.stdout
    assert "north 0.00 0.00" in proc.stdout


# --------------------------------------------------------------------------
# REQ-008 / AMB-004: region key
# --------------------------------------------------------------------------


def req_008_case_differs_means_two_regions():
    text = header("region", "amount") + "north,1.00\nNorth,2.00\nNORTH,4.00\n"
    regions, _, _, _ = report_of(text)
    assert set(regions) == {"north", "North", "NORTH"}


def req_008_surrounding_whitespace_is_trimmed_and_merged():
    text = header("region", "amount") + " north ,1.00\nnorth\t,2.00\neast,3.00\n"
    regions, _, _, lines = report_of(text)
    assert "north" in regions
    assert " north " not in regions
    assert regions["north"] == ("3.00", "1.50")
    assert lines[0].startswith("east ") or lines[0].startswith("north ")


def req_008_printed_id_is_the_trimmed_first_seen_text():
    text = header("region", "amount") + "  north ,1.00\nnorth,2.00\n"
    _, _, _, lines = report_of(text)
    assert lines[0].startswith("north "), lines


def req_008_internal_spacing_is_significant():
    text = header("region", "amount") + "new york,1.00\nnewyork,2.00\n"
    regions, _, _, _ = report_of(text)
    assert set(regions) == {"new york", "newyork"}


# --------------------------------------------------------------------------
# REQ-009: negative and zero measures
# --------------------------------------------------------------------------


def req_009_negative_and_zero_amounts_are_valid():
    text = header("region", "amount") + "north,100.00\nnorth,-40.00\n"
    regions, skipped, total, _ = report_of(text)
    assert regions["north"] == ("60.00", "30.00")
    assert skipped == 0
    assert total == ("60.00", 2)


def req_009_zero_amount_is_valid():
    text = header("region", "amount") + "north,0.00\n"
    regions, skipped, total, _ = report_of(text)
    assert regions["north"] == ("0.00", "0.00")
    assert skipped == 0
    assert total == ("0.00", 1)


def req_009_negative_amounts_never_appear_in_skipped():
    text = header("region", "amount") + "north,-1\nnorth,-2\nnorth,-3\n"
    _, skipped, _, _ = report_of(text)
    assert skipped == 0


def req_009_a_negative_total_prints_a_leading_minus():
    text = header("region", "amount") + "north,-1.00\neast,-2.00\n"
    regions, _, total, _ = report_of(text)
    assert total[0] == "-3.00"
    assert regions["north"][0] == "-1.00"


# --------------------------------------------------------------------------
# REQ-010: header-only file
# --------------------------------------------------------------------------


def req_010_header_only_file_prints_only_skipped_and_total():
    proc = run_text(header("region", "amount"))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["SKIPPED 0", "TOTAL 0.00 0"]


def req_010_header_only_file_prints_no_region_line():
    regions, skipped, total, lines = report_of(header("region", "amount"))
    assert regions == {}
    assert skipped == 0
    assert total == ("0.00", 0)
    assert len(lines) == 2


# --------------------------------------------------------------------------
# REQ-011: order invariance and sorting
# --------------------------------------------------------------------------


def req_011_region_lines_are_sorted_by_bytes():
    text = header("region", "amount") + "".join(
        "%s,1.00\n" % name for name in ("z", "A", "a", "B", "0", "_")
    )
    _, _, _, lines = report_of(text)
    names = [line.rsplit(" ", 2)[0] for line in lines[:-2]]
    assert names == sorted(names, key=lambda name: name.encode("utf-8"))


def req_011_shuffled_rows_produce_identical_stdout():
    rows = ["north,1.00", "south,2.50", "north,3.25", "east,-1.00", "A,4.00"]
    baseline = run_text(header("region", "amount") + "\n".join(rows) + "\n")
    rng = random.Random(20261108)
    for _ in range(5):
        rng.shuffle(rows)
        shuffled = run_text(header("region", "amount") + "\n".join(rows) + "\n")
        assert shuffled.returncode == baseline.returncode == 0
        assert shuffled.stdout == baseline.stdout


def req_011_header_order_does_not_change_the_report():
    rows = ["north,1.00", "south,2.50"]
    plain = run_text(header("region", "amount") + "\n".join(rows) + "\n")
    swapped = run_text(
        header("amount", "region") + "\n".join(
            "%s,%s" % (row.split(",")[1], row.split(",")[0]) for row in rows
        )
        + "\n"
    )
    assert plain.stdout == swapped.stdout


# --------------------------------------------------------------------------
# REQ-012: fatal input errors
# --------------------------------------------------------------------------


def req_012_nonexistent_path_is_fatal_and_silent_on_stdout():
    proc = run_path(os.path.join(SANDBOX, "does-not-exist.csv"))
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


def req_012_empty_file_is_fatal():
    proc = run_path(write_text("", "empty.csv"))
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


def req_012_directory_path_is_fatal():
    proc = run_path(SANDBOX)
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


def req_012_non_utf8_input_is_fatal():
    path = write_bytes(b"region,amount\nnorth,\xff\xfe1.00\n", "bad.bin")
    proc = run_path(path)
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


# --------------------------------------------------------------------------
# CSV shape handling
# --------------------------------------------------------------------------


def csv_quoted_region_with_comma_is_one_field():
    text = header("region", "amount") + '"north, west",10.00\n'
    regions, skipped, _, _ = report_of(text)
    assert regions == {"north, west": ("10.00", "10.00")}
    assert skipped == 0


def csv_crlf_input_is_read_normally():
    text = "region,amount\r\nnorth,1.00\r\nsouth,2.00\r\n"
    regions, skipped, total, _ = report_of(text)
    assert regions == {"north": ("1.00", "1.00"), "south": ("2.00", "2.00")}
    assert skipped == 0
    assert total == ("3.00", 2)


def csv_utf8_bom_does_not_hide_the_header():
    path = write_bytes(b"\xef\xbb\xbfregion,amount\nnorth,1.00\n", "bom.csv")
    proc = run_path(path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["north 1.00 1.00", "SKIPPED 0", "TOTAL 1.00 1"]


# --------------------------------------------------------------------------
# REL-002 / REL-004 / DIFF-001: independent recomputation
# --------------------------------------------------------------------------


def _expected_cents(value):
    return int(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def _cents_text(cents, places=2):
    """Render signed cents without floor-division sign errors."""
    sign = "-" if cents < 0 else ""
    magnitude = abs(cents)
    scale = 10 ** places
    return "%s%d.%0*d" % (sign, magnitude // scale, places, magnitude % scale)


def _independent_report(records):
    """Recompute the report from (region, amount) records with Decimal."""
    groups = {}
    skipped = 0
    for region, amount in records:
        if region is None or amount is None:
            skipped += 1
            continue
        groups.setdefault(region, []).append(Decimal(amount))
    expected = {}
    total_cents = 0
    with localcontext() as context:
        context.prec = 60
        for region in sorted(groups, key=lambda name: name.encode("utf-8")):
            values = groups[region]
            raw = sum(values, Decimal(0))
            revenue = _expected_cents(raw)
            average = _expected_cents(raw / Decimal(len(values)))
            expected[region] = (_cents_text(revenue), _cents_text(average))
            total_cents += revenue
    total = (
        _cents_text(total_cents),
        sum(len(values) for values in groups.values()),
    )
    return expected, skipped, total


def diff_001_random_two_decimal_file_matches_recomputation():
    rng = random.Random(11)
    names = ["north", "south", "east", "west", " north ", "North"]
    records = []
    for _ in range(300):
        region = rng.choice(names)
        amount = rng.randint(-50000, 50000)
        records.append((region.strip(), _cents_text(amount)))
    text = header("region", "amount") + "".join(
        "%s,%s\n" % record for record in records
    )
    regions, skipped, total, _ = report_of(text)
    expected, expected_skipped, expected_total = _independent_report(records)
    assert regions == expected
    assert skipped == expected_skipped
    assert total == expected_total


def diff_001_random_three_decimal_file_matches_recomputation():
    rng = random.Random(22)
    records = []
    for _ in range(200):
        region = rng.choice(["a", "b", "c", " a "])
        value = rng.randint(-20000, 20000)
        records.append((region.strip(), _cents_text(value, places=3)))
    text = header("region", "amount") + "".join(
        "%s,%s\n" % record for record in records
    )
    regions, skipped, total, _ = report_of(text)
    expected, _, expected_total = _independent_report(records)
    assert regions == expected
    assert skipped == 0
    assert total[0] == expected_total[0]  # printed region revenues add up
    assert total[1] == expected_total[1]


def rel_002_region_revenues_and_counts_add_up_to_the_total():
    text = (
        header("region", "amount")
        + "a,0.005\nb,0.005\nc,10.10\nd,-20.20\n"
    )
    regions, _, total, _ = report_of(text)
    region_cents = sum(
        int(Decimal(value[0]) * 100) for value in regions.values()
    )
    assert Decimal(total[0]) == Decimal(region_cents) / 100
    assert total[1] == len(regions)


# --------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------


def req_001_a_few_thousand_rows_finish_well_inside_the_bound():
    rows = ["region,amount"]
    for index in range(6000):
        rows.append("r%d,%d.%02d" % (index % 50, index % 1000, index % 100))
    path = write_text("\n".join(rows) + "\n", "large.csv")
    started = time.monotonic()
    proc = run_path(path)
    elapsed = time.monotonic() - started
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[-1] == "TOTAL 2999970.00 6000"
    assert elapsed < 10.0, "took %.1fs" % elapsed


TESTS = [
    ("req_001_declared_sample_report_is_exact", req_001_declared_sample_report_is_exact),
    ("req_001_entry_point_sits_at_the_repository_root", req_001_entry_point_sits_at_the_repository_root),
    ("req_001_reads_the_csv_named_by_the_first_argument", req_001_reads_the_csv_named_by_the_first_argument),
    ("req_001_relative_path_works_from_the_repository_root", req_001_relative_path_works_from_the_repository_root),
    ("req_001_missing_argument_is_a_usage_error", req_001_missing_argument_is_a_usage_error),
    ("req_001_extra_argument_is_rejected", req_001_extra_argument_is_rejected),
    ("req_001_a_well_formed_run_writes_nothing_to_stderr", req_001_a_well_formed_run_writes_nothing_to_stderr),
    ("req_001_a_few_thousand_rows_finish_well_inside_the_bound", req_001_a_few_thousand_rows_finish_well_inside_the_bound),
    ("req_002_swapped_header_columns_produce_the_same_report", req_002_swapped_header_columns_produce_the_same_report),
    ("req_002_extra_header_columns_are_followed_by_name", req_002_extra_header_columns_are_followed_by_name),
    ("req_002_header_names_tolerate_blank_and_case_variation", req_002_header_names_tolerate_blank_and_case_variation),
    ("req_002_missing_region_header_is_fatal", req_002_missing_region_header_is_fatal),
    ("req_002_missing_amount_header_is_fatal", req_002_missing_amount_header_is_fatal),
    ("req_003_one_line_per_present_region_and_no_absent_region", req_003_one_line_per_present_region_and_no_absent_region),
    ("req_003_revenue_is_the_region_sum", req_003_revenue_is_the_region_sum),
    ("req_003_average_divides_the_region_sum_by_its_count", req_003_average_divides_the_region_sum_by_its_count),
    ("req_004_exactly_one_totals_line", req_004_exactly_one_totals_line),
    ("req_004_totals_revenue_equals_the_sum_of_printed_region_revenues", req_004_totals_revenue_equals_the_sum_of_printed_region_revenues),
    ("req_004_order_count_equals_counted_rows", req_004_order_count_equals_counted_rows),
    ("req_004_totals_line_is_printed_after_skipped", req_004_totals_line_is_printed_after_skipped),
    ("req_005_three_valid_two_malformed_rows_are_aggregated_and_counted", req_005_three_valid_two_malformed_rows_are_aggregated_and_counted),
    ("req_005_all_malformed_rows_exit_zero", req_005_all_malformed_rows_exit_zero),
    ("req_005_clean_file_prints_skipped_zero", req_005_clean_file_prints_skipped_zero),
    ("req_005_wrong_field_count_rows_are_malformed", req_005_wrong_field_count_rows_are_malformed),
    ("req_005_blank_region_rows_are_malformed", req_005_blank_region_rows_are_malformed),
    ("req_005_non_numeric_amounts_are_malformed", req_005_non_numeric_amounts_are_malformed),
    ("req_005_plain_decimal_shapes_are_accepted", req_005_plain_decimal_shapes_are_accepted),
    ("req_005_a_blank_physical_line_is_a_wrong_field_count_row", req_005_a_blank_physical_line_is_a_wrong_field_count_row),
    ("req_006_duplicate_row_counts_twice", req_006_duplicate_row_counts_twice),
    ("req_006_repeated_region_is_one_line", req_006_repeated_region_is_one_line),
    ("req_007_single_amount_0_125_rounds_up", req_007_single_amount_0_125_rounds_up),
    ("req_007_single_amount_2_674_rounds_down", req_007_single_amount_2_674_rounds_down),
    ("req_007_negative_half_rounds_away_from_zero", req_007_negative_half_rounds_away_from_zero),
    ("req_007_average_rounds_from_the_unrounded_sum", req_007_average_rounds_from_the_unrounded_sum),
    ("req_007_negative_average_half_rounds_away_from_zero", req_007_negative_average_half_rounds_away_from_zero),
    ("req_007_integer_and_one_decimal_amounts_print_two_decimals", req_007_integer_and_one_decimal_amounts_print_two_decimals),
    ("req_007_every_printed_number_matches_the_shape", req_007_every_printed_number_matches_the_shape),
    ("req_007_no_negative_zero_is_printed", req_007_no_negative_zero_is_printed),
    ("req_008_case_differs_means_two_regions", req_008_case_differs_means_two_regions),
    ("req_008_surrounding_whitespace_is_trimmed_and_merged", req_008_surrounding_whitespace_is_trimmed_and_merged),
    ("req_008_printed_id_is_the_trimmed_first_seen_text", req_008_printed_id_is_the_trimmed_first_seen_text),
    ("req_008_internal_spacing_is_significant", req_008_internal_spacing_is_significant),
    ("req_009_negative_and_zero_amounts_are_valid", req_009_negative_and_zero_amounts_are_valid),
    ("req_009_zero_amount_is_valid", req_009_zero_amount_is_valid),
    ("req_009_negative_amounts_never_appear_in_skipped", req_009_negative_amounts_never_appear_in_skipped),
    ("req_009_a_negative_total_prints_a_leading_minus", req_009_a_negative_total_prints_a_leading_minus),
    ("req_010_header_only_file_prints_only_skipped_and_total", req_010_header_only_file_prints_only_skipped_and_total),
    ("req_010_header_only_file_prints_no_region_line", req_010_header_only_file_prints_no_region_line),
    ("req_011_region_lines_are_sorted_by_bytes", req_011_region_lines_are_sorted_by_bytes),
    ("req_011_shuffled_rows_produce_identical_stdout", req_011_shuffled_rows_produce_identical_stdout),
    ("req_011_header_order_does_not_change_the_report", req_011_header_order_does_not_change_the_report),
    ("req_012_nonexistent_path_is_fatal_and_silent_on_stdout", req_012_nonexistent_path_is_fatal_and_silent_on_stdout),
    ("req_012_empty_file_is_fatal", req_012_empty_file_is_fatal),
    ("req_012_directory_path_is_fatal", req_012_directory_path_is_fatal),
    ("req_012_non_utf8_input_is_fatal", req_012_non_utf8_input_is_fatal),
    ("csv_quoted_region_with_comma_is_one_field", csv_quoted_region_with_comma_is_one_field),
    ("csv_crlf_input_is_read_normally", csv_crlf_input_is_read_normally),
    ("csv_utf8_bom_does_not_hide_the_header", csv_utf8_bom_does_not_hide_the_header),
    ("diff_001_random_two_decimal_file_matches_recomputation", diff_001_random_two_decimal_file_matches_recomputation),
    ("diff_001_random_three_decimal_file_matches_recomputation", diff_001_random_three_decimal_file_matches_recomputation),
    ("rel_002_region_revenues_and_counts_add_up_to_the_total", rel_002_region_revenues_and_counts_add_up_to_the_total),
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
