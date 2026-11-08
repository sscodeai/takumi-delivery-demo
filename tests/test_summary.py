#!/usr/bin/env python3
"""TAP suite for the delivered ``bash summary.sh``.

The contract under test is ``docs/requirements/intake.yaml``:

    run:          bash summary.sh {csv}
    region line:  <region> <count> <sum> <mean>
    total line:   TOTAL <count> <sum>
    skipped line: SKIPPED <skipped-count>

Every check drives the real entry point in a subprocess (or a function of
``summary.py`` directly), so what is asserted is behaviour a caller sees. The
report is written to ``reports/tests.tap`` (override with ``TAP_OUT``) and
echoed to stdout; the process exits 0 only when every check passes.
"""

import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_UP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "summary.sh")
TAP_OUT = os.environ.get("TAP_OUT", os.path.join(ROOT, "reports", "tests.tap"))
TIMEOUT = 30

sys.path.insert(0, ROOT)
import summary  # noqa: E402 - the implementation under test

REGION_LINE = re.compile(r"^(.+) ([0-9]+) (-?[0-9]+\.[0-9]{2}) (-?[0-9]+\.[0-9]{2})$")
TOTAL_LINE = re.compile(r"^TOTAL ([0-9]+) (-?[0-9]+\.[0-9]{2})$")
SKIPPED_LINE = re.compile(r"^SKIPPED ([0-9]+)$")
NUMBER = re.compile(r"^-?[0-9]+\.[0-9]{2}$")

# The sample the requirement document declares: it carries NO header line.
SAMPLE = (
    "North,120.50\n"
    "South,80.00\n"
    "North,99.50\n"
    "East,45.25\n"
)
SAMPLE_REPORT = [
    "East 1 45.25 45.25",
    "North 2 220.00 110.00",
    "South 1 80.00 80.00",
    "TOTAL 4 345.25",
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


def csv_file(text, name="input.csv"):
    path = os.path.join(SANDBOX, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def csv_bytes(data, name="input.csv"):
    path = os.path.join(SANDBOX, name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def run(args=None, cwd=ROOT):
    command = ["bash", SCRIPT] + ([] if args is None else list(args))
    return subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=TIMEOUT,
        text=True,
    )


def report(text):
    """Run the tool on CSV text and return (stdout lines, CompletedProcess)."""
    result = run([csv_file(text)])
    return result.stdout.splitlines(), result


def region_lines(lines):
    return [line for line in lines if REGION_LINE.match(line)]


def total_lines(lines):
    return [line for line in lines if line.startswith("TOTAL ")]


def skipped_lines(lines):
    return [line for line in lines if line.startswith("SKIPPED ")]


def parsed_regions(lines):
    out = {}
    for line in lines:
        match = REGION_LINE.match(line)
        if match:
            out[match.group(1)] = (
                int(match.group(2)),
                Decimal(match.group(3)),
                Decimal(match.group(4)),
            )
    return out


def assert_report(text, expected):
    lines, result = report(text)
    assert result.returncode == 0, (result.returncode, result.stderr)
    assert lines == expected, "expected %r, got %r" % (expected, lines)


def assert_shapes(lines):
    for line in lines:
        assert (
            REGION_LINE.match(line)
            or TOTAL_LINE.match(line)
            or SKIPPED_LINE.match(line)
        ), "unexpected stdout line: %r" % line


# ---------------------------------------------------------------------------
# REQ-001 -- the CSV summarising entry point
# ---------------------------------------------------------------------------


def req_001_declared_sample_report_is_exact():
    # The declared sample has no header, so all four lines are data rows.
    assert_report(SAMPLE, SAMPLE_REPORT)


def req_001_entry_point_sits_at_the_repository_root():
    assert os.path.isfile(SCRIPT), SCRIPT
    text = open(SCRIPT, encoding="utf-8").read()
    assert "summary.py" in text


def req_001_reads_the_path_substituted_as_the_first_argument():
    first = csv_file("North,1.00\n", "first.csv")
    second = csv_file("South,2.00\n", "second.csv")
    first_out = run([first])
    second_out = run([second])
    assert first_out.returncode == 0 and second_out.returncode == 0
    assert first_out.stdout.splitlines() == ["North 1 1.00 1.00", "TOTAL 1 1.00"]
    assert second_out.stdout.splitlines() == ["South 1 2.00 2.00", "TOTAL 1 2.00"]


def req_001_a_relative_path_is_resolved_from_the_repository_root():
    path = csv_file("North,1.00\n", "relative.csv")
    relative = os.path.relpath(path, ROOT)
    result = run([relative])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["North 1 1.00 1.00", "TOTAL 1 1.00"]


def req_001_header_row_is_never_a_data_row():
    # Header names differ in case and surrounding whitespace (REQ-001).
    lines, result = report(" REGION ,\tAmount \nNorth,120.50\nNorth,99.50\n")
    assert result.returncode == 0, result.stderr
    assert lines == ["North 2 220.00 110.00", "TOTAL 2 220.00"], lines


def req_001_header_only_file_is_exactly_one_line():
    lines, result = report("region,amount\n")
    assert result.returncode == 0, result.stderr
    assert lines == ["TOTAL 0 0.00"], lines


def req_001_stdout_carries_only_declared_shapes():
    lines, result = report(
        "region,amount\nNorth,1.00\nbad\nSouth,abc\nEast,2.005\n"
    )
    assert result.returncode == 0, result.stderr
    assert_shapes(lines)


def req_001_a_well_formed_run_writes_nothing_to_stderr():
    result = run([csv_file(SAMPLE, "clean.csv")])
    assert result.returncode == 0
    assert result.stderr == "", result.stderr


def req_001_no_argument_is_a_usage_error():
    result = run([])
    assert result.returncode != 0
    assert result.stdout == ""
    assert "usage" in result.stderr.lower()


def req_001_a_missing_path_is_a_fatal_error_on_stderr():
    result = run([os.path.join(SANDBOX, "does-not-exist.csv")])
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr != ""


def req_001_a_quoted_region_containing_a_comma_stays_one_field():
    lines, result = report('region,amount\n"North, West",10.00\n')
    assert result.returncode == 0, result.stderr
    assert lines == ['North, West 1 10.00 10.00', "TOTAL 1 10.00"], lines


def req_001_crlf_input_is_read_normally():
    path = csv_bytes(b"region,amount\r\nNorth,1.50\r\nSouth,2.50\r\n", "crlf.csv")
    result = run([path])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "North 1 1.50 1.50",
        "South 1 2.50 2.50",
        "TOTAL 2 4.00",
    ]


def req_001_a_utf8_bom_does_not_hide_the_header():
    path = csv_bytes(
        b"\xef\xbb\xbfregion,amount\nNorth,1.50\n", "bom.csv"
    )
    result = run([path])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["North 1 1.50 1.50", "TOTAL 1 1.50"]


def req_001_non_utf8_input_is_a_fatal_error_on_stderr():
    path = csv_bytes(b"\xff\xfe\n", "nonutf8.csv")
    result = run([path])
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr != ""


# ---------------------------------------------------------------------------
# REQ-002 -- total revenue and average order value per region
# ---------------------------------------------------------------------------


def req_002_acceptance_example_is_exact():
    assert_report(
        "region,amount\nNorth,120.50\nNorth,99.50\nSouth,80.00\n",
        [
            "North 2 220.00 110.00",
            "South 1 80.00 80.00",
            "TOTAL 3 300.00",
        ],
    )


def req_002_count_is_an_integer_and_numbers_have_two_decimals():
    lines, _ = report("region,amount\nNorth,120.50\nNorth,99.50\nSouth,80.00\n")
    match = REGION_LINE.match(lines[0])
    assert match, lines[0]
    assert match.group(2) == "2" and "." not in match.group(2)
    assert NUMBER.match(match.group(3)) and NUMBER.match(match.group(4))


def req_002_one_line_per_distinct_region_and_no_absent_region():
    lines, _ = report(
        "region,amount\nNorth,1.00\nSouth,2.00\nNorth,3.00\nEast,4.00\n"
    )
    regions = parsed_regions(lines)
    assert set(regions) == {"North", "South", "East"}, regions
    assert len(region_lines(lines)) == 3, lines


def req_002_fields_are_positional_region_count_sum_mean():
    lines, _ = report("region,amount\nNorth,120.50\nNorth,99.50\n")
    assert lines[0] == "North 2 220.00 110.00", lines[0]
    assert lines[0].split(" ") == ["North", "2", "220.00", "110.00"]


# ---------------------------------------------------------------------------
# REQ-003 -- the whole-report totals line
# ---------------------------------------------------------------------------


def req_003_exactly_one_totals_line_and_it_is_last_aggregate():
    lines, _ = report(SAMPLE)
    totals = total_lines(lines)
    assert len(totals) == 1, lines
    assert lines[-1] == totals[0] or skipped_lines(lines), lines
    assert lines.index(totals[0]) > max(
        index for index, line in enumerate(lines) if REGION_LINE.match(line)
    )


def req_003_declared_sample_total_is_345_25():
    assert_report(SAMPLE, SAMPLE_REPORT)
    assert SAMPLE_REPORT[-1] == "TOTAL 4 345.25"


def req_003_header_only_file_prints_total_zero():
    assert_report("region,amount\n", ["TOTAL 0 0.00"])


def req_003_empty_file_prints_total_zero():
    assert_report("", ["TOTAL 0 0.00"])


def req_003_totals_follow_region_lines_even_with_skips():
    lines, _ = report("region,amount\nNorth,1.00\nbad\nSouth,2.00\n")
    assert lines == [
        "North 1 1.00 1.00",
        "South 1 2.00 2.00",
        "TOTAL 2 3.00",
        "SKIPPED 1",
    ], lines


# ---------------------------------------------------------------------------
# REQ-004 / AMB-001 -- unusable rows are skipped and counted
# ---------------------------------------------------------------------------


def req_004_non_numeric_amount_is_skipped_and_excluded():
    assert_report(
        "region,amount\nNorth,10.00\nSouth,abc\n",
        ["North 1 10.00 10.00", "TOTAL 1 10.00", "SKIPPED 1"],
    )


def req_004_every_unusable_shape_is_skipped_once():
    text = (
        "region,amount\n"
        "North,10.00\n"  # usable
        "lonely\n"  # wrong field count
        "South,1.00,extra\n"  # wrong field count
        ",5.00\n"  # empty region
        "   ,5.00\n"  # whitespace-only region
        "West,\n"  # missing amount
        "West,nan\n"  # not a plain decimal
        "West,$5.00\n"  # currency symbol
        'West,"1,200.50"\n'  # thousands separator
        "West,50%\n"  # percent sign
        "West, 5.00\n"  # surrounding blank is not plain decimal
        "West,1e3\n"  # scientific notation
        "West,.5\n"  # no integer digits
        "West,5.\n"  # empty fractional part
        "\n"  # no fields at all
    )
    assert_report(
        text,
        ["North 1 10.00 10.00", "TOTAL 1 10.00", "SKIPPED 14"],
    )


def req_004_plain_decimals_are_accepted():
    assert_report(
        "region,amount\nA,5\nB,5.0\nC,+5.00\nD,-5.00\nE,005.50\n",
        [
            "A 1 5.00 5.00",
            "B 1 5.00 5.00",
            "C 1 5.00 5.00",
            "D 1 -5.00 -5.00",
            "E 1 5.50 5.50",
            "TOTAL 5 15.50",
        ],
    )


def req_004_skipped_rows_never_reach_any_aggregate():
    lines, _ = report(
        "region,amount\nNorth,10.00\nNorth,oops\nSouth,abc\n"
    )
    regions = parsed_regions(lines)
    assert regions["North"][0] == 1 and regions["North"][1] == Decimal("10.00")
    assert total_lines(lines) == ["TOTAL 1 10.00"], lines


def req_004_skipped_count_equals_unusable_rows():
    lines, _ = report("North,1\n,\nEast,bad\nNorth,2\n")
    assert skipped_lines(lines) == ["SKIPPED 2"], lines


def req_004_a_clean_file_prints_no_skipped_line():
    lines, _ = report("region,amount\nNorth,1.00\n")
    assert skipped_lines(lines) == [], lines


def req_004_the_header_is_not_counted_as_skipped():
    lines, _ = report("region,amount\nNorth,1.00\n")
    assert skipped_lines(lines) == [], lines


# ---------------------------------------------------------------------------
# REQ-005 / AMB-002 / AMB-005 -- duplicate resolution and ordering
# ---------------------------------------------------------------------------


def req_005_repeated_region_merges_into_one_line():
    lines, _ = report("region,amount\nNorth,10.00\nNorth,20.00\n")
    assert region_lines(lines) == ["North 2 30.00 15.00"], lines


def req_005_region_lines_are_sorted_by_utf8_bytes():
    rows = ["zulu,1", "Alpha,2", "alpha,3", "Beta,4", "á,5", "0,6"]
    lines, _ = report("region,amount\n" + "\n".join(rows) + "\n")
    got = [REGION_LINE.match(line).group(1) for line in region_lines(lines)]
    expected = sorted(
        ["zulu", "Alpha", "alpha", "Beta", "á", "0"], key=lambda s: s.encode("utf-8")
    )
    assert got == expected, got


def req_005_differently_spelled_keys_are_not_merged():
    # AMB-005 (exact): no trimming or case folding of the region key.
    lines, _ = report("region,amount\nNorth,1.00\nnorth,2.00\nNorth ,4.00\n")
    regions = parsed_regions(lines)
    assert set(regions) == {"North", "north", "North "}, regions
    assert all(regions[key][0] == 1 for key in regions), regions
    assert len(region_lines(lines)) == 3, lines


def req_005_internal_spacing_is_significant():
    lines, _ = report("region,amount\nN orth,1.00\nNorth,2.00\n")
    regions = parsed_regions(lines)
    assert set(regions) == {"N orth", "North"}, regions


# ---------------------------------------------------------------------------
# REQ-006 / AMB-003 -- rounding and number formatting
# ---------------------------------------------------------------------------


def req_006_positive_half_rounds_away_from_zero():
    lines, _ = report("region,amount\nA,0.005\n")
    assert lines[0] == "A 1 0.01 0.01", lines


def req_006_negative_half_rounds_away_from_zero():
    lines, _ = report("region,amount\nA,-0.005\n")
    assert lines[0] == "A 1 -0.01 -0.01", lines


def req_006_below_half_rounds_down_and_never_prints_negative_zero():
    lines, _ = report("region,amount\nA,0.004\nB,-0.004\n")
    assert "A 1 0.00 0.00" in lines, lines
    assert "B 1 0.00 0.00" in lines, lines
    for line in lines:
        assert "-0.00" not in line, line


def req_006_mean_is_rounded_from_the_unrounded_sum():
    # 10.00 / 3 = 3.333... -> 3.33; 0.01 / 2 = 0.005 -> 0.01 (half-up).
    lines, _ = report(
        "region,amount\nA,10.00\nA,0\nA,0\nB,0.01\nB,0\n"
    )
    assert "A 3 10.00 3.33" in lines, lines
    assert "B 2 0.01 0.01" in lines, lines


def req_006_mean_negative_half_rounds_away_from_zero():
    lines, _ = report("region,amount\nA,-0.01\nA,0\n")
    assert lines[0] == "A 2 -0.01 -0.01", lines


def req_006_integer_and_one_decimal_inputs_still_print_two_decimals():
    lines, _ = report("region,amount\nA,3\nA,4.5\n")
    assert lines[0] == "A 2 7.50 3.75", lines


def req_006_every_printed_number_matches_the_shape():
    lines, _ = report(
        "region,amount\nA,1\nB,1.2\nC,-0.005\nD,1000000.999\n"
    )
    for line in region_lines(lines):
        match = REGION_LINE.match(line)
        assert match, line
        assert NUMBER.match(match.group(3)) and NUMBER.match(match.group(4)), line
        assert "," not in line and "e" not in line.lower().split(" ")[0], line
    total = TOTAL_LINE.match(total_lines(lines)[0])
    assert total, lines
    assert NUMBER.match(total.group(2)), total.group(2)


def req_006_sum_is_the_rounded_total_of_raw_amounts():
    lines, _ = report("region,amount\nA,0.004\nA,0.004\n")
    assert lines[0] == "A 2 0.01 0.00", lines


# ---------------------------------------------------------------------------
# REQ-007 / REL-003 / REL-004 -- row-order invariance and additivity
# ---------------------------------------------------------------------------


def req_007_shuffled_rows_produce_identical_stdout():
    rows = [
        "North,10.00",
        "South,3.33",
        "North,0.01",
        "East,7.77",
        "South,1.00",
        "East,0.005",
    ]
    text = "region,amount\n" + "\n".join(rows) + "\n"
    baseline = run([csv_file(text, "ordered.csv")]).stdout
    generator = random.Random(7)
    for index in range(5):
        shuffled = rows[:]
        generator.shuffle(shuffled)
        shuffled_text = "region,amount\n" + "\n".join(shuffled) + "\n"
        got = run([csv_file(shuffled_text, "shuffled%d.csv" % index)]).stdout
        assert got == baseline, (shuffled, got, baseline)


def req_007_repeating_decimal_mean_is_order_independent():
    rows = ["A,10.00", "A,0", "A,0"]
    baseline = run([csv_file("region,amount\n" + "\n".join(rows) + "\n")]).stdout
    reversed_stdout = run(
        [csv_file("region,amount\n" + "\n".join(reversed(rows)) + "\n")]
    ).stdout
    assert baseline == reversed_stdout


def rel_003_region_counts_and_sums_add_up_to_the_total():
    lines, _ = report(
        "region,amount\nA,0.005\nB,0.005\nC,10.00\nD,-0.005\n"
    )
    regions = parsed_regions(lines)
    total = TOTAL_LINE.match(total_lines(lines)[0])
    assert sum(value[0] for value in regions.values()) == int(total.group(1)), lines
    summed = sum(value[1] for value in regions.values())
    assert summed == Decimal(total.group(2)), (summed, total.group(2), lines)


# ---------------------------------------------------------------------------
# DIFF-001 -- independent recomputation (Decimal, half-up)
# ---------------------------------------------------------------------------


def independent_cents_text(cents):
    """Format an integer cent count without using summary.py's formatter."""
    sign = "-" if cents < 0 else ""
    magnitude = abs(cents)
    return "%s%d.%02d" % (sign, magnitude // 100, magnitude % 100)


def independent_report(text):
    """Recompute the expected report without using summary.py's arithmetic."""
    rows = text.splitlines()
    if rows and [field.strip().lower() for field in rows[0].split(",")] == [
        "region",
        "amount",
    ]:
        rows = rows[1:]
    groups = {}
    skipped = 0
    for row in rows:
        fields = row.split(",")
        if len(fields) != 2:
            skipped += 1
            continue
        region, amount = fields
        if region.strip() == "" or not re.match(r"^[+-]?[0-9]+(\.[0-9]+)?$", amount):
            skipped += 1
            continue
        group = groups.setdefault(region, [0, Decimal(0)])
        group[0] += 1
        group[1] += Decimal(amount)
    lines = []
    total_count = 0
    total_cents = 0
    for region in sorted(groups, key=lambda name: name.encode("utf-8")):
        count, raw = groups[region]
        cents = int((raw * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        mean = (raw / count) * 100
        mean_cents = int(mean.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        lines.append(
            "%s %d %s %s"
            % (
                region,
                count,
                independent_cents_text(cents),
                independent_cents_text(mean_cents),
            )
        )
        total_count += count
        total_cents += cents
    lines.append("TOTAL %d %s" % (total_count, independent_cents_text(total_cents)))
    if skipped:
        lines.append("SKIPPED %d" % skipped)
    return lines


def diff_001_random_two_decimal_files_match_an_independent_recomputation():
    generator = random.Random(20261108)
    regions = ["North", "South", "East", "West", "north", "N orth"]
    for trial in range(8):
        rows = ["region,amount"]
        for _ in range(generator.randint(0, 15)):
            rows.append(
                "%s,%d.%02d"
                % (
                    generator.choice(regions),
                    generator.randint(0, 500),
                    generator.randint(0, 99),
                )
            )
        text = "\n".join(rows) + "\n"
        lines, result = report(text)
        assert result.returncode == 0, result.stderr
        assert lines == independent_report(text), (text, lines)


def diff_001_random_three_decimal_files_match_an_independent_recomputation():
    generator = random.Random(314159)
    regions = ["North", "South", "East", "West", "north", "N orth"]
    for trial in range(8):
        rows = ["region,amount"]
        for _ in range(generator.randint(1, 12)):
            sign = generator.choice(["", "", "-"])
            rows.append(
                "%s,%s%d.%03d"
                % (
                    generator.choice(regions),
                    sign,
                    generator.randint(0, 200),
                    generator.randint(0, 999),
                )
            )
        text = "\n".join(rows) + "\n"
        lines, result = report(text)
        assert result.returncode == 0, result.stderr
        assert lines == independent_report(text), (text, lines)


# ---------------------------------------------------------------------------
# Unit-level checks of summary.py helpers
# ---------------------------------------------------------------------------


def unit_parse_amount_accepts_plain_decimals():
    for text in ("0", "5", "+5", "-5", "5.0", "005.50", "-0.005"):
        assert summary.parse_amount(text) is not None, text


def unit_parse_amount_rejects_everything_else():
    for text in ("", " ", "$5", "1,000", "5%", "1e3", ".5", "5.", " 5", "5 "):
        assert summary.parse_amount(text) is None, text


def unit_parse_region_keeps_the_key_verbatim():
    # AMB-005 (exact): no trim, no case folding.
    assert summary.parse_region(" North ") == " North "
    assert summary.parse_region("North") == "North"


def unit_parse_region_rejects_blank_values():
    for text in ("", " ", "\t", "   "):
        assert summary.parse_region(text) is None, text


def unit_looks_like_header_matches_case_and_blanks():
    assert summary.looks_like_header(["REGION", " Amount "])
    assert not summary.looks_like_header(["North", "1.00"])
    assert not summary.looks_like_header(["region", "amount", "extra"])


def unit_rounded_cents_rounds_halves_away_from_zero():
    from fractions import Fraction

    assert summary.rounded_cents(Fraction(5, 1000)) == 1
    assert summary.rounded_cents(Fraction(-5, 1000)) == -1
    assert summary.rounded_cents(Fraction(4, 1000)) == 0
    assert summary.rounded_cents(Fraction(-4, 1000)) == 0
    assert summary.rounded_cents(Fraction(1, 3)) == 33


def unit_format_cents_never_prints_negative_zero():
    assert summary.format_cents(0) == "0.00"
    assert summary.format_cents(-0) == "0.00"
    assert summary.format_cents(-1) == "-0.01"


def unit_parse_row_accepts_usable_records():
    from fractions import Fraction

    assert summary.parse_row(["North", "1.005"]) == ("North", Fraction(201, 200))
    assert summary.parse_row([" North ", "5"]) == (" North ", Fraction(5))
    assert summary.parse_row(["A", "-0.00"]) == ("A", Fraction(0))


def unit_parse_row_rejects_unusable_records():
    for record in (
        summary.MALFORMED,
        ["only-one-field"],
        ["A", "1", "extra"],
        ["", "1"],
        ["   ", "1"],
        ["A", "abc"],
    ):
        assert summary.parse_row(record) is None, record


def unit_format_value_rounds_halves_away_from_zero():
    from fractions import Fraction

    assert summary.format_value(Fraction(5, 1000)) == "0.01"
    assert summary.format_value(Fraction(-5, 1000)) == "-0.01"
    assert summary.format_value(Fraction(4, 1000)) == "0.00"
    assert summary.format_value(Fraction(1, 3)) == "0.33"


def unit_summarise_emits_skipped_only_when_needed():
    assert summary.summarise([["region", "amount"], ["A", "1"]]) == [
        "A 1 1.00 1.00",
        "TOTAL 1 1.00",
    ]
    assert summary.summarise([["region", "amount"], ["A", "bad"]]) == [
        "TOTAL 0 0.00",
        "SKIPPED 1",
    ]


TESTS = [
    ("req_001_declared_sample_report_is_exact", req_001_declared_sample_report_is_exact),
    ("req_001_entry_point_sits_at_the_repository_root", req_001_entry_point_sits_at_the_repository_root),
    ("req_001_reads_the_path_substituted_as_the_first_argument", req_001_reads_the_path_substituted_as_the_first_argument),
    ("req_001_a_relative_path_is_resolved_from_the_repository_root", req_001_a_relative_path_is_resolved_from_the_repository_root),
    ("req_001_header_row_is_never_a_data_row", req_001_header_row_is_never_a_data_row),
    ("req_001_header_only_file_is_exactly_one_line", req_001_header_only_file_is_exactly_one_line),
    ("req_001_stdout_carries_only_declared_shapes", req_001_stdout_carries_only_declared_shapes),
    ("req_001_a_well_formed_run_writes_nothing_to_stderr", req_001_a_well_formed_run_writes_nothing_to_stderr),
    ("req_001_no_argument_is_a_usage_error", req_001_no_argument_is_a_usage_error),
    ("req_001_a_missing_path_is_a_fatal_error_on_stderr", req_001_a_missing_path_is_a_fatal_error_on_stderr),
    ("req_001_a_quoted_region_containing_a_comma_stays_one_field", req_001_a_quoted_region_containing_a_comma_stays_one_field),
    ("req_001_crlf_input_is_read_normally", req_001_crlf_input_is_read_normally),
    ("req_001_a_utf8_bom_does_not_hide_the_header", req_001_a_utf8_bom_does_not_hide_the_header),
    ("req_001_non_utf8_input_is_a_fatal_error_on_stderr", req_001_non_utf8_input_is_a_fatal_error_on_stderr),
    ("req_002_acceptance_example_is_exact", req_002_acceptance_example_is_exact),
    ("req_002_count_is_an_integer_and_numbers_have_two_decimals", req_002_count_is_an_integer_and_numbers_have_two_decimals),
    ("req_002_one_line_per_distinct_region_and_no_absent_region", req_002_one_line_per_distinct_region_and_no_absent_region),
    ("req_002_fields_are_positional_region_count_sum_mean", req_002_fields_are_positional_region_count_sum_mean),
    ("req_003_exactly_one_totals_line_and_it_is_last_aggregate", req_003_exactly_one_totals_line_and_it_is_last_aggregate),
    ("req_003_declared_sample_total_is_345_25", req_003_declared_sample_total_is_345_25),
    ("req_003_header_only_file_prints_total_zero", req_003_header_only_file_prints_total_zero),
    ("req_003_empty_file_prints_total_zero", req_003_empty_file_prints_total_zero),
    ("req_003_totals_follow_region_lines_even_with_skips", req_003_totals_follow_region_lines_even_with_skips),
    ("req_004_non_numeric_amount_is_skipped_and_excluded", req_004_non_numeric_amount_is_skipped_and_excluded),
    ("req_004_every_unusable_shape_is_skipped_once", req_004_every_unusable_shape_is_skipped_once),
    ("req_004_plain_decimals_are_accepted", req_004_plain_decimals_are_accepted),
    ("req_004_skipped_rows_never_reach_any_aggregate", req_004_skipped_rows_never_reach_any_aggregate),
    ("req_004_skipped_count_equals_unusable_rows", req_004_skipped_count_equals_unusable_rows),
    ("req_004_a_clean_file_prints_no_skipped_line", req_004_a_clean_file_prints_no_skipped_line),
    ("req_004_the_header_is_not_counted_as_skipped", req_004_the_header_is_not_counted_as_skipped),
    ("req_005_repeated_region_merges_into_one_line", req_005_repeated_region_merges_into_one_line),
    ("req_005_region_lines_are_sorted_by_utf8_bytes", req_005_region_lines_are_sorted_by_utf8_bytes),
    ("req_005_differently_spelled_keys_are_not_merged", req_005_differently_spelled_keys_are_not_merged),
    ("req_005_internal_spacing_is_significant", req_005_internal_spacing_is_significant),
    ("req_006_positive_half_rounds_away_from_zero", req_006_positive_half_rounds_away_from_zero),
    ("req_006_negative_half_rounds_away_from_zero", req_006_negative_half_rounds_away_from_zero),
    ("req_006_below_half_rounds_down_and_never_prints_negative_zero", req_006_below_half_rounds_down_and_never_prints_negative_zero),
    ("req_006_mean_is_rounded_from_the_unrounded_sum", req_006_mean_is_rounded_from_the_unrounded_sum),
    ("req_006_mean_negative_half_rounds_away_from_zero", req_006_mean_negative_half_rounds_away_from_zero),
    ("req_006_integer_and_one_decimal_inputs_still_print_two_decimals", req_006_integer_and_one_decimal_inputs_still_print_two_decimals),
    ("req_006_every_printed_number_matches_the_shape", req_006_every_printed_number_matches_the_shape),
    ("req_006_sum_is_the_rounded_total_of_raw_amounts", req_006_sum_is_the_rounded_total_of_raw_amounts),
    ("req_007_shuffled_rows_produce_identical_stdout", req_007_shuffled_rows_produce_identical_stdout),
    ("req_007_repeating_decimal_mean_is_order_independent", req_007_repeating_decimal_mean_is_order_independent),
    ("rel_003_region_counts_and_sums_add_up_to_the_total", rel_003_region_counts_and_sums_add_up_to_the_total),
    ("diff_001_random_two_decimal_files_match_an_independent_recomputation", diff_001_random_two_decimal_files_match_an_independent_recomputation),
    ("diff_001_random_three_decimal_files_match_an_independent_recomputation", diff_001_random_three_decimal_files_match_an_independent_recomputation),
    ("unit_parse_amount_accepts_plain_decimals", unit_parse_amount_accepts_plain_decimals),
    ("unit_parse_amount_rejects_everything_else", unit_parse_amount_rejects_everything_else),
    ("unit_parse_region_keeps_the_key_verbatim", unit_parse_region_keeps_the_key_verbatim),
    ("unit_parse_region_rejects_blank_values", unit_parse_region_rejects_blank_values),
    ("unit_looks_like_header_matches_case_and_blanks", unit_looks_like_header_matches_case_and_blanks),
    ("unit_rounded_cents_rounds_halves_away_from_zero", unit_rounded_cents_rounds_halves_away_from_zero),
    ("unit_format_cents_never_prints_negative_zero", unit_format_cents_never_prints_negative_zero),
    ("unit_parse_row_accepts_usable_records", unit_parse_row_accepts_usable_records),
    ("unit_parse_row_rejects_unusable_records", unit_parse_row_rejects_unusable_records),
    ("unit_format_value_rounds_halves_away_from_zero", unit_format_value_rounds_halves_away_from_zero),
    ("unit_summarise_emits_skipped_only_when_needed", unit_summarise_emits_skipped_only_when_needed),
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
