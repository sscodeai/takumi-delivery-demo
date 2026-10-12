"""DIFF-001 / REL-001: an independent decimal oracle and row-order invariance.

`tests/reference.py` re-derives the summary with exact ``Fraction`` arithmetic
and an integer half-up step. This module adds a second, deliberately different
oracle: it keeps values as :class:`decimal.Decimal` and rounds with the
standard library's ``ROUND_HALF_UP`` quantizer, which is defined as "round to
nearest with ties going away from zero" -- exactly the confirmed AMB-003 option.
Two independent rounding implementations agreeing with the tool on the same
fixtures is much stronger evidence than a single reference.

The fixtures are built from the world the requirement document declares
(``docs/requirements/intake.yaml``: ``date``, ``station``, ``temperature_c``):
the declared sample, duplicates of its rows, exact one-decimal place ties and
malformed rows, shuffled. Every fixture is also run twice in different row
orders, and the two reports must be byte-identical (REL-001).
"""

import datetime
import random
import unittest
from decimal import ROUND_HALF_UP, Decimal

from helpers import HEADER, run_csv, skipped_of, total_of

# The five data rows the requirement document declares in input_format.sample.
SAMPLE = [
    "2024-01-01,ALPHA,10.4",
    "2024-01-01,BRAVO,-2.5",
    "2024-01-02,ALPHA,11.6",
    "2024-01-02,BRAVO,-1.5",
    "2024-01-03,ALPHA,9.5",
]

# Rows the document's malformed-row world names: a short row, an empty station,
# a non-numeric measure and an unparseable date.
MALFORMED = [
    "2024-01-01,ALPHA",
    "2024-01-01,,7.0",
    "2024-01-01,ALPHA,abc",
    "not-a-date,ALPHA,10.4",
]

# Values that sit exactly on a rounding boundary, plus ordinary readings. None
# of them rounds to zero from below, so the sign of a rendered zero never needs
# a special case in the oracle.
BOUNDARY_VALUES = ["1.25", "-1.25", "0.05", "-0.05", "2.35", "-2.35", "9.95"]


def _one_decimal(value):
    """Render a Decimal with exactly one decimal place, half away from zero."""
    rendered = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    text = format(rendered, "f")
    return "0.0" if text == "-0.0" else text


def _valid_date(text):
    head = text.replace("T", " ").split(" ")[0]
    parts = head.split("-")
    if len(parts) != 3:
        return False
    if (len(parts[0]), len(parts[1]), len(parts[2])) != (4, 2, 2):
        return False
    if not all(part.isdigit() for part in parts):
        return False
    year, month, day = (int(part) for part in parts)
    try:
        datetime.date(year, month, day)
    except ValueError:
        return False
    return True


def _valid_temperature(text):
    try:
        Decimal(text)
    except Exception:
        return False
    # Match the tool's declared world: a plain optionally signed decimal.
    if text == "" or text.strip() != text:
        return False
    if text[0] in "+":
        return False
    body = text[1:] if text[0] == "-" else text
    parts = body.split(".")
    if len(parts) > 2 or any(part == "" for part in parts):
        return False
    return all(part.isdigit() for part in parts)


def decimal_report(text):
    """Compute the full expected report with a Decimal-based oracle."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    stations = {}
    skipped = 0
    total = 0
    header_seen = False
    date_i, station_i, temperature_i = 0, 1, 2

    for line in lines:
        fields = line.split(",")
        if not header_seen:
            header_seen = True
            names = [field.strip().lower() for field in fields]
            if all(name in names for name in ("date", "station", "temperature_c")):
                date_i = names.index("date")
                station_i = names.index("station")
                temperature_i = names.index("temperature_c")
                continue
        if len(fields) != 3:
            skipped += 1
            continue
        station = fields[station_i]
        if station == "":
            skipped += 1
            continue
        if not _valid_date(fields[date_i]):
            skipped += 1
            continue
        if not _valid_temperature(fields[temperature_i]):
            skipped += 1
            continue

        value = Decimal(fields[temperature_i])
        entry = stations.get(station)
        if entry is None:
            stations[station] = [1, value, value, value]
        else:
            entry[0] += 1
            entry[1] = min(entry[1], value)
            entry[2] = max(entry[2], value)
            entry[3] += value
        total += 1

    out = []
    for station in sorted(stations, key=lambda name: name.encode("utf-8")):
        count, minimum, maximum, accumulated = stations[station]
        out.append(
            "%s %d %s %s %s"
            % (
                station,
                count,
                _one_decimal(minimum),
                _one_decimal(maximum),
                _one_decimal(accumulated / count),
            )
        )
    out.append("SKIPPED %d" % skipped)
    out.append("TOTAL %d" % total)
    return "\n".join(out) + "\n"


def _parts(seed):
    """Return (with_header, data_rows) for a deterministic fixture."""
    rng = random.Random(seed)
    rows = list(SAMPLE)
    for _ in range(rng.randint(0, 5)):
        rows.append(rng.choice(SAMPLE))
    for _ in range(rng.randint(0, 2)):
        value = rng.choice(BOUNDARY_VALUES)
        date = "2024-%02d-%02d" % (rng.randint(1, 12), rng.randint(1, 28))
        rows.append("%s,%s,%s" % (date, rng.choice(["ALPHA", "BRAVO", "Charlie"]), value))
    if rng.random() < 0.7:
        rows += rng.sample(MALFORMED, rng.randint(1, len(MALFORMED)))
    rng.shuffle(rows)
    return rng.random() < 0.5, rows


def _render(with_header, rows):
    body = "\n".join(rows) + "\n"
    return (HEADER + body) if with_header else body


def _fixture(seed):
    with_header, rows = _parts(seed)
    return _render(with_header, rows)


class DecimalDifferentialTests(unittest.TestCase):
    def test_tool_agrees_with_the_decimal_oracle(self):
        for seed in range(40):
            with self.subTest(seed=seed):
                text = _fixture(seed)
                result = run_csv(text)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, decimal_report(text))

    def test_shuffling_the_data_rows_is_byte_identical(self):
        # REL-001 speaks about the data rows: the header line keeps its place,
        # only the readings after it are permuted.
        for seed in range(20):
            with self.subTest(seed=seed):
                with_header, rows = _parts(seed)
                shuffled = rows[:]
                random.Random(seed + 10_000).shuffle(shuffled)
                first = _render(with_header, rows)
                second = _render(with_header, shuffled)
                self.assertEqual(run_csv(first).stdout, run_csv(second).stdout)

    def test_additivity_and_skipped_count_agree_with_the_oracle(self):
        for seed in range(20):
            with self.subTest(seed=seed):
                text = _fixture(seed)
                expected = decimal_report(text)
                result = run_csv(text)
                self.assertEqual(result.stdout, expected)
                self.assertEqual(total_of(result.stdout), total_of(expected))
                self.assertEqual(skipped_of(result.stdout), skipped_of(expected))


if __name__ == "__main__":
    unittest.main()
