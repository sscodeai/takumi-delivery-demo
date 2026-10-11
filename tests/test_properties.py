"""REQ-006 and REL-001: the summary depends only on the multiset of rows."""

import random
import unittest

from helpers import HEADER, run_csv, skipped_of, station_lines, total_of
from reference import reference_output


def build_rows(seed, rows=80):
    rng = random.Random(seed)
    stations = ["ALPHA", "BRAVO", "Charlie", "delta-9", "E1", "zeta"]
    out = []
    for _ in range(rows):
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        station = rng.choice(stations)
        value = rng.choice(
            [
                "%.1f" % rng.uniform(-40, 45),
                "%.2f" % rng.uniform(-40, 45),
                "1.25",
                "-1.25",
                "%d" % rng.randint(-40, 45),
            ]
        )
        out.append("2024-%02d-%02d,%s,%s" % (month, day, station, value))
    return out


class RowOrderTests(unittest.TestCase):
    def test_permuting_the_data_rows_does_not_change_the_output(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                rows = build_rows(seed)
                base = HEADER + "\n".join(rows) + "\n"
                baseline = run_csv(base)
                self.assertEqual(baseline.returncode, 0)
                for attempt in range(4):
                    shuffled = list(rows)
                    random.Random(seed * 100 + attempt).shuffle(shuffled)
                    result = run_csv(HEADER + "\n".join(shuffled) + "\n")
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, baseline.stdout)

    def test_permuting_rows_with_malformed_rows_keeps_skipped_and_total(self):
        rows = build_rows(7, rows=30)
        rows += [
            "2024-01-01,ALPHA",
            "not-a-date,BRAVO,1.0",
            "2024-01-01,ALPHA,abc",
        ]
        baseline = run_csv(HEADER + "\n".join(rows) + "\n")
        self.assertEqual(skipped_of(baseline.stdout), 3)
        for attempt in range(4):
            shuffled = list(rows)
            random.Random(attempt).shuffle(shuffled)
            result = run_csv(HEADER + "\n".join(shuffled) + "\n")
            self.assertEqual(result.stdout, baseline.stdout)

    def test_reversed_rows_match_the_forward_output(self):
        rows = build_rows(3)
        forward = run_csv(HEADER + "\n".join(rows) + "\n")
        backward = run_csv(HEADER + "\n".join(reversed(rows)) + "\n")
        self.assertEqual(forward.stdout, backward.stdout)

    def test_output_is_independent_of_station_first_appearance(self):
        rows_a = [
            "2024-01-01,BETA,1.0",
            "2024-01-02,ALPHA,2.0",
            "2024-01-03,GAMMA,3.0",
        ]
        rows_b = list(reversed(rows_a))
        first = run_csv(HEADER + "\n".join(rows_a) + "\n")
        second = run_csv(HEADER + "\n".join(rows_b) + "\n")
        self.assertEqual(first.stdout, second.stdout)

    def test_header_less_input_is_aggregated_like_the_declared_world(self):
        # A header-less document (the pipeline's own sample) is the same
        # multiset of readings; the tool and the reference must agree on it.
        rows = build_rows(13)
        text = "\n".join(rows) + "\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference_output(text))

    def test_permutations_agree_with_the_reference_implementation(self):
        rows = build_rows(11)
        for attempt in range(5):
            shuffled = list(rows)
            random.Random(attempt).shuffle(shuffled)
            text = HEADER + "\n".join(shuffled) + "\n"
            result = run_csv(text)
            self.assertEqual(result.stdout, reference_output(text))


class StabilityTests(unittest.TestCase):
    def test_repeated_runs_are_byte_identical(self):
        text = HEADER + "\n".join(build_rows(5)) + "\n"
        outputs = {run_csv(text).stdout for _ in range(3)}
        self.assertEqual(len(outputs), 1)

    def test_station_lines_and_totals_stay_consistent_after_shuffling(self):
        rows = build_rows(21)
        baseline = run_csv(HEADER + "\n".join(rows) + "\n")
        shuffled = list(rows)
        random.Random(42).shuffle(shuffled)
        result = run_csv(HEADER + "\n".join(shuffled) + "\n")
        self.assertEqual(station_lines(result.stdout), station_lines(baseline.stdout))
        self.assertEqual(total_of(result.stdout), total_of(baseline.stdout))
        self.assertEqual(skipped_of(result.stdout), skipped_of(baseline.stdout))
