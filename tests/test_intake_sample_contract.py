"""The acceptance fixture is the one the requirement document declares.

The external judge for this delivery is forged from
``docs/requirements/intake.yaml`` (ADR-026/ADR-033).  It does not read the
implementation: it takes the rows under ``deliverable.input_format.sample`` as
the world, adds the declared header, and derives a reshuffled copy, two
duplicate fixtures and a malformed fixture from them.  It then recomputes every
expectation itself.

``tests/test_forged_judge_contract.py`` hard-codes one copy of that sample.  This
module removes the copy: it parses ``input_format.sample`` out of the confirmed
document at test time, builds the same fixtures the forge builds, and checks the
delivered CLI against ``tests/reference.py`` -- an independent implementation
that shares no code with ``summary.sh``.  A change to the document's declared
world therefore reaches the delivered suite instead of silently invalidating a
stale constant.
"""

import datetime
import os
import unittest

from helpers import HEADER, ROOT, run_csv
from reference import reference_output

DOC = os.path.join(ROOT, "docs", "requirements", "intake.yaml")


def declared_sample():
    """Return the data rows under ``deliverable.input_format.sample``."""
    with open(DOC, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "sample: |":
            continue
        indent = len(line) - len(line.lstrip())
        rows = []
        for following in lines[index + 1:]:
            if following.strip() == "":
                continue
            if len(following) - len(following.lstrip()) <= indent:
                break
            rows.append(following[indent + 2:].rstrip())
        return rows
    raise AssertionError("%s declares no input_format.sample" % DOC)


def _max_measure(rows):
    return max(float(row.split(",")[2]) for row in rows)


def _render(rows, header=True):
    body = "\n".join(rows) + "\n"
    return (HEADER + body) if header else body


def _set_field(row, column, value):
    fields = row.split(",")
    fields[column] = value
    return ",".join(fields)


class DeclaredSampleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = declared_sample()
        cls.base = _render(cls.sample, header=True)
        # The forge builds the duplicate from the sample's first row with a
        # measure one whole degree above the sample's maximum, dated one day
        # outside the sample's range on either side.
        dup_row = _set_field(cls.sample[0], 2, "%.1f" % (_max_measure(cls.sample) + 1.0))
        dates = sorted(row.split(",")[0] for row in cls.sample)
        first_date = datetime.date.fromisoformat(dates[0])
        last_date = datetime.date.fromisoformat(dates[-1])
        cls.dup_late = cls.base + _set_field(
            dup_row, 0, (last_date + datetime.timedelta(days=1)).isoformat()
        ) + "\n"
        cls.dup_early = cls.base + _set_field(
            dup_row, 0, (first_date - datetime.timedelta(days=1)).isoformat()
        ) + "\n"
        # The forge's three malformed shapes: a short row, a non-numeric
        # measure and an unparseable date, each derived from the first row.
        first = cls.sample[0]
        cls.malformed = cls.base + "\n".join(
            (
                ",".join(first.split(",")[:-1]),
                _set_field(first, 2, "abc"),
                _set_field(first, 0, "not-a-date"),
            )
        ) + "\n"

    def test_the_document_still_declares_a_usable_sample(self):
        self.assertGreaterEqual(len(self.sample), 3)
        for row in self.sample:
            self.assertEqual(len(row.split(",")), 3)

    def test_header_less_sample_is_the_declared_world(self):
        # The document's own sample carries no header line.
        result = run_csv(_render(self.sample, header=False))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference_output(_render(self.sample, header=False)))

    def test_declared_sample_prints_the_exact_report(self):
        result = run_csv(self.base)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 3 9.5 11.6 10.5\n"
            "BRAVO 2 -2.5 -1.5 -2.0\n"
            "SKIPPED 0\n"
            "TOTAL 5\n",
        )

    def test_reshuffled_sample_agrees_with_the_reference(self):
        fixture = _render(list(reversed(self.sample)), header=True)
        result = run_csv(fixture)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference_output(fixture))

    def test_duplicate_fixtures_agree_with_the_reference(self):
        for name, fixture in (("late", self.dup_late), ("early", self.dup_early)):
            with self.subTest(fixture=name):
                result = run_csv(fixture)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, reference_output(fixture))

    def test_malformed_fixture_agrees_with_the_reference(self):
        result = run_csv(self.malformed)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference_output(self.malformed))
        self.assertIn("SKIPPED 3\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
