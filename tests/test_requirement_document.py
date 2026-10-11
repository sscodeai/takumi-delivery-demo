"""REQ-002: the confirmed requirement document keeps the service contract.

A judge is forged from ``docs/requirements/service-station-summary.yaml``, so the
document itself is part of the delivery's test surface. These checks pin the
declarations the acceptance criteria name: how the service is started, how one
invocation is bounded, that no unread ``build``/``tests`` key is declared, and
that every ambiguity records the confirmed ``checkedAs`` option.
"""

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCUMENT = os.path.join(ROOT, "docs", "requirements", "service-station-summary.yaml")


def read_document():
    with open(DOCUMENT, "r", encoding="utf-8") as handle:
        return handle.read()


class DeliverableDeclarationTests(unittest.TestCase):
    """REQ-002: the start command, its bound and the refused keys."""

    @classmethod
    def setUpClass(cls):
        cls.text = read_document()

    def test_the_service_declares_how_it_is_started(self):
        self.assertIn('run: "bash serve.sh {csv} {port}"', self.text)

    def test_the_service_declares_its_url_and_read_command(self):
        self.assertIn('url: "http://127.0.0.1:{port}/summary"', self.text)
        self.assertIn('read: "curl -fsS {url}"', self.text)

    def test_one_invocation_is_bounded_by_a_positive_timeout(self):
        match = re.search(r"(?m)^\s*timeoutMs:\s*(\d+)\s*$", self.text)
        self.assertIsNotNone(match, "the deliverable declares no timeoutMs")
        self.assertGreater(int(match.group(1)), 0)
        # A start-and-serve command never exits, so the declared bound must be
        # large enough to start and read, and finite.
        self.assertLessEqual(int(match.group(1)), 600000)

    def test_the_document_declares_no_build_or_tests_key(self):
        # REQ-002: the delivered project's tests are run from the workflow, so a
        # `build` or `tests` key here would be a declaration nothing reads.
        self.assertNotRegex(self.text, r"(?m)^\s*build:")
        self.assertNotRegex(self.text, r"(?m)^\s*tests:")

    def test_the_scenario_reaches_the_surface_and_asserts_the_body(self):
        self.assertIn("SCN-001", self.text)
        self.assertIn('start: "bash serve.sh {csv} {port}"', self.text)
        self.assertIn("expect_status: 200", self.text)
        self.assertIn("""expect_body: '"total"'""", self.text)


class OutputFormatTests(unittest.TestCase):
    """REQ-001: the declared output shapes are the JSON objects served."""

    @classmethod
    def setUpClass(cls):
        cls.text = read_document()

    def _shapes(self):
        return re.findall(r"(?m)^\s*shape:\s*'(\{.*\})'\s*$", self.text)

    def test_all_three_declared_shapes_are_json(self):
        shapes = self._shapes()
        self.assertEqual(len(shapes), 3, shapes)
        for shape in shapes:
            with self.subTest(shape=shape):
                payload = (
                    shape.replace("<station>", "ALPHA")
                    .replace("<skipped-count>", "0")
                    .replace("<count>", "1")
                    .replace("<min>", "1.0")
                    .replace("<max>", "1.0")
                    .replace("<mean>", "1.0")
                )
                self.assertIsInstance(json.loads(payload), dict)

    def test_the_declared_fields_are_the_reported_fields(self):
        self.assertIn("fields: [id, count, min, max, mean]", self.text)
        self.assertIn("fields: [skipped-count]", self.text)
        self.assertIn("fields: [count]", self.text)


class ConfirmedDecisionTests(unittest.TestCase):
    """Every ambiguity records the confirmed choice and how it is checked."""

    @classmethod
    def setUpClass(cls):
        text = read_document()
        cls.blocks = {}
        # re.split with a capture returns [prefix, id1, body1, id2, body2, ...]
        parts = re.split(r"(?m)^  - id: (AMB-\d+)\s*$", text)
        for index in range(1, len(parts), 2):
            cls.blocks[parts[index]] = parts[index + 1]

    EXPECTED = {
        "AMB-001": "skip-count: skipped, excluded from every aggregate, and counted in the response",
        "AMB-002": "merge: each occurrence remains a separate valid reading and all contribute to the aggregate",
        "AMB-003": "half-up: round half away from zero",
        "AMB-004": "ascending station id, byte-wise lexicographic",
        "AMB-005": "valid readings only: the sum of the per-station counts",
    }

    CHECKED = {
        "AMB-001": "skip-count",
        "AMB-002": "merge",
        "AMB-003": "half-up",
    }

    def test_every_ambiguity_is_present_and_has_a_chosen_option(self):
        for identifier in self.EXPECTED:
            with self.subTest(ambiguity=identifier):
                self.assertIn(identifier, self.blocks)
                self.assertIn("chosen:", self.blocks[identifier])

    def test_each_chosen_option_is_the_document_default(self):
        for identifier, chosen in self.EXPECTED.items():
            with self.subTest(ambiguity=identifier):
                body = self.blocks[identifier]
                self.assertIn('default: "%s"' % chosen, body)
                self.assertIn('chosen: "%s"' % chosen, body)

    def test_each_checked_behaviour_is_recorded(self):
        for identifier, checked in self.CHECKED.items():
            with self.subTest(ambiguity=identifier):
                self.assertIn("checkedAs: %s" % checked, self.blocks[identifier])


class RelationTests(unittest.TestCase):
    """The declared relations and differential match the checked decisions."""

    @classmethod
    def setUpClass(cls):
        cls.text = read_document()

    def test_relations_cover_order_additivity_duplicates_and_malformed_rows(self):
        for relation in ("REL-001", "REL-002", "REL-003", "REL-004"):
            with self.subTest(relation=relation):
                self.assertIn(relation, self.text)

    def test_differential_decides_the_rounding_ambiguity(self):
        self.assertIn("DIFF-001", self.text)
        self.assertIn("independent-aggregation", self.text)
        self.assertIn("decides: AMB-003", self.text)

    def test_relations_decide_the_blocking_ambiguities(self):
        self.assertIn("decides: AMB-005", self.text)
        self.assertIn("decides: AMB-002", self.text)
        self.assertIn("decides: AMB-001", self.text)

    def test_additivity_relation_decides_the_total(self):
        self.assertRegex(
            self.text,
            r"id: REL-002[\s\S]*?decides: AMB-005",
        )


if __name__ == "__main__":
    unittest.main()
