"""Generated-world differential suite for ``bash summary.sh <csv>``.

The fixed fixtures elsewhere pin the exact reports the forged judge builds from
``docs/requirements/intake.yaml``.  This module adds the complementary evidence:
a deterministic, seeded generator builds many different worlds -- header-less
and header-led, ordered and shuffled, with duplicate ``(date, station)`` keys
and every kind of malformed row -- and the delivered tool's whole stdout is
compared byte for byte against the independent ``Fraction`` recomputation in
``tests/reference.py``.

  * REL-001 row-order-invariance     a shuffled copy is byte-identical
  * REL-002 additivity               per-station counts sum to TOTAL
  * REL-003 duplicate-resolution     repeated keys each count (AMB-002)
  * REL-004 malformed accounting     bad rows are excluded and counted (AMB-001)
  * DIFF-001 independent aggregation the reference agrees, half away from zero
                                     (AMB-003)

Seeded rather than random so a failure is reproducible, and bounded so the
suite stays fast.
"""

import random
import unittest

from helpers import HEADER, counts_sum, run_csv, skipped_of, station_lines, total_of
from reference import reference_output

# Deterministic seed: the same worlds on every run, so a failure is a bug in the
# implementation rather than in the generator.
SEED = 20261012
WORLDS = 60

STATIONS = ["ALPHA", "BRAVO", "charlie", "Delta-1", "Z", "a"]
GOOD_DATES = ["2024-01-01", "2024-01-31", "2024-02-29", "2023-12-31", "2024-07-04"]
BAD_DATES = ["", "2023-02-29", "2024-13-01", "2024-1-1", "not-a-date", "2024-01-01x"]
# Enough decimals that min/max, not just the mean, exercises the rounding rule.
GOOD_TEMPS = [
    "10.4", "-2.5", "0", "0.0", "-0.0", "7", "3.25", "-3.25", "1.05", "-1.05",
    "0.05", "-0.05", "12.345", "-12.345", "100.95", "-100.95",
]
BAD_TEMPS = ["", "abc", "NaN", "Infinity", "1e3", " 5", "+5", ".5", "5.", "1,000"]


def generate(rng):
    """Build one fixture as (text, has_header) from the seeded generator."""
    rows = []
    for _ in range(rng.randint(0, 50)):
        roll = rng.random()
        if roll < 0.7:
            # A well-formed reading, sometimes re-using a (date, station) key.
            rows.append(
                "%s,%s,%s"
                % (
                    rng.choice(GOOD_DATES),
                    rng.choice(STATIONS),
                    rng.choice(GOOD_TEMPS),
                )
            )
        elif roll < 0.82:
            rows.append("%s,%s,%s" % (rng.choice(BAD_DATES), rng.choice(STATIONS), rng.choice(GOOD_TEMPS)))
        elif roll < 0.9:
            rows.append("%s,%s,%s" % (rng.choice(GOOD_DATES), rng.choice(STATIONS), rng.choice(BAD_TEMPS)))
        elif roll < 0.95:
            rows.append("%s,,%s" % (rng.choice(GOOD_DATES), rng.choice(GOOD_TEMPS)))
        else:
            # A wrong field count: too many or too few fields.
            width = rng.choice([0, 1, 2, 4])
            rows.append(",".join(rng.choice(GOOD_TEMPS) for _ in range(width)))
    # Permute the data rows first: the declared header, when present, always
    # stays the first line, while the readings below it are in random order.
    rng.shuffle(rows)
    has_header = rng.random() < 0.7
    if has_header:
        rows = ["date,station,temperature_c"] + rows
    return "\n".join(rows) + "\n", has_header


def seeded_worlds():
    rng = random.Random(SEED)
    return [generate(rng) for _ in range(WORLDS)]


class GeneratedWorldDifferentialTests(unittest.TestCase):
    """REL-001/REL-002/REL-004/DIFF-001 over generated worlds."""

    @classmethod
    def setUpClass(cls):
        cls.worlds = seeded_worlds()

    def test_every_generated_world_matches_the_independent_reference(self):
        # DIFF-001: the tool's exact report equals an independent Fraction
        # recomputation (half away from zero) for every generated world.
        for index, (text, _has_header) in enumerate(self.worlds):
            with self.subTest(world=index):
                result = run_csv(text)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, reference_output(text))

    def test_shuffling_each_world_is_byte_identical(self):
        # REL-001: only the multiset of rows matters, never their order.
        rng = random.Random(SEED + 1)
        for index, (text, _has_header) in enumerate(self.worlds):
            lines = text.splitlines()
            body, header = lines, []
            if lines and lines[0] == "date,station,temperature_c":
                header, body = lines[:1], lines[1:]
            rng.shuffle(body)
            shuffled = "\n".join(header + body) + "\n"
            with self.subTest(world=index):
                forward = run_csv(text)
                reordered = run_csv(shuffled)
                self.assertEqual(forward.returncode, 0)
                self.assertEqual(reordered.returncode, 0)
                self.assertEqual(forward.stdout, reordered.stdout)

    def test_counts_sum_to_total_and_skipped_is_reported(self):
        # REL-002 additivity and REL-004 malformed accounting (AMB-001).
        for index, (text, _has_header) in enumerate(self.worlds):
            with self.subTest(world=index):
                result = run_csv(text)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))
                # The reference knows exactly how many rows are malformed.
                expected = [
                    line for line in reference_output(text).splitlines()
                    if line.startswith("SKIPPED ")
                ]
                self.assertEqual(
                    ["SKIPPED %d" % skipped_of(result.stdout)], expected
                )

    def test_station_lines_are_ascending_bytewise(self):
        # AMB-004: byte-wise lexicographic station id order.
        for index, (text, _has_header) in enumerate(self.worlds):
            with self.subTest(world=index):
                names = [line.split(" ")[0] for line in station_lines(run_csv(text).stdout)]
                self.assertEqual(names, sorted(names, key=lambda name: name.encode("utf-8")))


class HalfAwayFromZeroBoundaryTests(unittest.TestCase):
    """AMB-003/DIFF-001: exact half values round away from zero."""

    def test_positive_and_negative_half_means_round_away_from_zero(self):
        text = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,1.5\n"
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 2 1.0 1.5 1.3\nSKIPPED 0\nTOTAL 2\n")
        text = HEADER + "2024-01-01,BRAVO,-1.0\n2024-01-02,BRAVO,-1.5\n"
        result = run_csv(text)
        self.assertEqual(result.stdout, "BRAVO 2 -1.5 -1.0 -1.3\nSKIPPED 0\nTOTAL 2\n")

    def test_min_and_max_with_extra_decimals_round_half_away_from_zero(self):
        text = HEADER + "2024-01-01,ALPHA,1.25\n2024-01-02,ALPHA,-1.25\n"
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 2 -1.3 1.3 0.0\nSKIPPED 0\nTOTAL 2\n")

    def test_rounded_values_agree_with_the_reference(self):
        text = HEADER + "\n".join(
            "2024-01-%02d,ALPHA,%s" % (day, value)
            for day, value in enumerate(["0.05", "-0.05", "1.15", "-1.15", "2.25"], start=1)
        ) + "\n"
        result = run_csv(text)
        self.assertEqual(result.stdout, reference_output(text))


class DuplicateKeyMergeTests(unittest.TestCase):
    """AMB-002 merge: every occurrence of a repeated key is its own reading."""

    def test_repeated_keys_all_contribute(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA,2.0\n"
            + "2024-01-01,ALPHA,3.0\n"
            + "2024-01-01,BRAVO,4.0\n"
            + "2024-01-01,BRAVO,4.0\n"
        )
        result = run_csv(text)
        self.assertEqual(
            result.stdout,
            "ALPHA 3 1.0 3.0 2.0\nBRAVO 2 4.0 4.0 4.0\nSKIPPED 0\nTOTAL 5\n",
        )
        self.assertEqual(counts_sum(result.stdout), 5)


if __name__ == "__main__":
    unittest.main()
