"""Explicit acceptance-criteria traceability for docs/requirements/intake.yaml.

The declared TAP suite (tests/common_keys_tests.py) already pins the contract.
This module adds a second, independent pass in which every acceptance criterion
and every recorded ambiguity decision has a test whose name names it:

    REQ-001 AC1 .. AC2     the command-line entry point
    REQ-002 AC1 .. AC2     the intersection of the object keys
    REQ-003 AC1 .. AC2     one key per line, ascending code-point order
    REQ-004 AC1 .. AC2     the single word none when nothing is common
    REQ-005 AC1 .. AC2     the test runner and its TAP report
    REQ-006 AC1 .. AC2     the mutation harness and its report
    REQ-007 / AMB-001      an empty array prints none and exits zero
    REQ-007 / AMB-002      a non-object element is skipped
    REQ-007 / AMB-003      unusable input is a non-zero stop-error

The integration cases drive the delivered entry point across a process
boundary, exactly as the document declares it:

    bash common-keys.sh <json-file>

The unit cases exercise common_keys.parse() and common_keys.common_keys()
directly. run-tests.sh discovers this file with

    python3 -m unittest discover -s tests -p 'test_acceptance.py'

so the acceptance pass runs as part of the delivered gate; a failure here makes
the runner exit non-zero even though the TAP report is written by the other
suite. The legacy summary.sh unittest suite under tests/test_*.py is a separate
compatibility deliverable and is not part of this requirement's gate.
"""

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "common-keys.sh")
RUNNER = os.path.join(ROOT, "run-tests.sh")
MUTATION = os.path.join(ROOT, "mutation.sh")
MANIFEST = os.path.join(ROOT, "package.json")

NONE = "none\n"


def load_module(name, relative_path):
    """Load a project module by path without depending on sys.path order."""
    path = os.path.join(ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMMON_KEYS = load_module("acceptance_common_keys", "common_keys.py")
VERIFY_TAP = load_module("acceptance_verify_tap_report", os.path.join("tests", "verify_tap_report.py"))
MUTATION_HARNESS = load_module(
    "acceptance_mutation_harness", os.path.join("mutation", "common_keys_mutation.py")
)


def run_entry(content, timeout=30):
    """Run `bash common-keys.sh <file>` on a temporary fixture and capture it."""
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "input.json")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return subprocess.run(
            ["bash", ENTRY, path],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )


def run_path(path, timeout=30):
    return subprocess.run(
        ["bash", ENTRY, path],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )


def keys_output(keys):
    return "".join(key + "\n" for key in keys)


class EntryPointAcceptance(unittest.TestCase):
    """REQ-001: the common-keys.sh command-line entry point."""

    def assert_success(self, result, stdout):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", "a successful answer writes nothing to stderr")
        self.assertEqual(result.stdout, stdout)

    def test_req_001_ac1_valid_array_exits_zero(self):
        result = run_entry('[{"a": 1, "b": 2}, {"a": 3, "b": 4}]')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_req_001_ac2_result_is_on_stdout_and_the_process_terminates(self):
        started = time.monotonic()
        result = run_entry('[{"b": 1, "a": 2}, {"b": 3, "a": 4}]', timeout=30)
        elapsed = time.monotonic() - started
        self.assert_success(result, "a\nb\n")
        self.assertLess(elapsed, 10.0, "the process must terminate on its own")

    def test_req_001_entry_point_is_an_executable_script(self):
        self.assertTrue(os.path.isfile(ENTRY), "common-keys.sh must sit at the repository root")
        self.assertTrue(os.access(ENTRY, os.X_OK), "common-keys.sh must be executable")
        with open(ENTRY, encoding="utf-8") as handle:
            self.assertTrue(handle.readline().startswith("#!"), "common-keys.sh needs a shebang")

    def test_req_001_entry_point_runs_directly_via_its_shebang(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "input.json")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write('[{"b": 1, "a": 2}, {"b": 3, "a": 4}]')
            result = subprocess.run(
                [ENTRY, path],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=30,
            )
        self.assert_success(result, "a\nb\n")


class IntersectionAcceptance(unittest.TestCase):
    """REQ-002: the keys present in every object of the array."""

    def assert_keys(self, content, keys):
        result = run_entry(content)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, keys_output(keys))

    def test_req_002_ac1_declared_example_reports_only_a(self):
        self.assert_keys('[{"a": 1, "b": 2}, {"a": 3, "c": 4}, {"a": 5, "b": 6}]', ["a"])

    def test_req_002_ac2_key_missing_from_any_one_object_is_absent(self):
        cases = [
            '[{"a": 1, "b": 2}, {"a": 3, "c": 4}]',          # missing from the second
            '[{"a": 1, "b": 2}, {"a": 3}, {"a": 4, "b": 5}]',  # missing from the middle
            '[{"a": 1}, {"a": 2, "b": 3}, {"a": 4, "b": 5}]',  # missing from the first
        ]
        for content in cases:
            with self.subTest(content=content):
                self.assert_keys(content, ["a"])

    def test_req_002_exact_string_match_after_json_decoding(self):
        self.assert_keys('[{"\\u00e9": 1}, {"\u00e9": 2}]', ["\u00e9"])
        result = run_entry('[{"\u00e9": 1}, {"e\u0301": 2}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, NONE)
        self.assertEqual(result.stderr, "")

    def test_req_002_escaped_and_literal_spellings_are_the_same_key_name(self):
        self.assert_keys('[{"\\u0061": 1}, {"a": 2}]', ["a"])
        self.assert_keys('[{"\\u00e9": 1}, {"\\u00E9": 2}]', ["\u00e9"])
        self.assert_keys('[{"a\\tb": 1}, {"a\\tb": 2}]', ["a\tb"])


class OrderingAcceptance(unittest.TestCase):
    """REQ-003: one common key per line in ascending code-point order."""

    def test_req_003_ac1_one_line_per_common_key_and_nothing_else(self):
        result = run_entry('[{"a": 1, "b": 2, "c": 3}, {"c": 4, "a": 5, "b": 6}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines, ["a", "b", "c"])
        self.assertEqual(result.stdout, "a\nb\nc\n", "one newline-terminated line per key")
        self.assertEqual(result.stderr, "")

    def test_req_003_ac2_declared_example_is_ordered_a_b_c(self):
        result = run_entry('[{"b": 1, "a": 2, "c": 3}, {"b": 4, "a": 5, "c": 6}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "a\nb\nc\n")

    def test_req_003_code_point_order_is_strictly_ascending_and_unique(self):
        result = run_entry('[{"z": 1, "A": 2, "a": 3, "B": 4, "1": 5}, {"z": 1, "A": 2, "a": 3, "B": 4, "1": 5}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        keys = result.stdout.splitlines()
        self.assertEqual(keys, ["1", "A", "B", "a", "z"])
        self.assertEqual(keys, sorted(set(keys)), "no duplicates and no reordering")

    def test_req_003_code_point_order_includes_supplementary_plane_keys(self):
        shared = '{"\\uFFFF": 1, "\\ud83d\\ude00": 2}'
        result = run_entry("[%s, %s]" % (shared, shared))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "\uffff\n\U0001f600\n")
        self.assertEqual(result.stderr, "")


class NoneAcceptance(unittest.TestCase):
    """REQ-004: the single lowercase word none when no key is common."""

    def test_req_004_ac1_disjoint_objects_print_none(self):
        result = run_entry('[{"a": 1}, {"b": 2}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, NONE)

    def test_req_004_ac2_none_is_the_complete_output(self):
        result = run_entry('[{"a": 1, "b": 2}, {"c": 3, "d": 4}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, NONE)
        self.assertEqual(result.stdout.count("\n"), 1, "exactly one line")
        self.assertNotIn("key", result.stdout)
        self.assertNotIn("none", result.stderr)
        self.assertEqual(result.stderr, "")

    def test_req_004_the_sentinel_is_the_lowercase_word_only(self):
        for key in ("NONE", "None", "nOne"):
            with self.subTest(key=key):
                result = run_entry('[{"%s": 1}, {"%s": 2}]' % (key, key))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, key + "\n")
                self.assertEqual(result.stderr, "")
        result = run_entry('[{"NONE": 1}, {"other": 2}]')
        self.assertEqual(result.stdout, NONE)


class RunnerAcceptance(unittest.TestCase):
    """REQ-005: the delivered suite and its runner."""

    def test_req_005_ac1_runner_is_discoverable_and_writes_the_declared_tap_report(self):
        self.assertTrue(os.path.isfile(RUNNER), "run-tests.sh must sit at the repository root")
        self.assertTrue(os.access(RUNNER, os.X_OK), "run-tests.sh must be executable")
        syntax = subprocess.run(
            ["bash", "-n", RUNNER], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        with open(RUNNER, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("reports/tests.tap", source, "the runner must name the declared report")
        self.assertIn("common_keys_tests.py", source, "the runner must run the declared suite")
        with open(MANIFEST, encoding="utf-8") as handle:
            scripts = json.load(handle).get("scripts", {})
        self.assertEqual(scripts.get("test"), "bash run-tests.sh")

    def test_req_005_ac2_tap_report_with_no_failing_point_is_accepted(self):
        green = (
            "TAP version 13\n"
            "1..2\n"
            "ok 1 - first\n"
            "ok 2 - second\n"
            "# tests 2\n"
            "# pass 2\n"
            "# fail 0\n"
        )
        self.assertEqual(VERIFY_TAP.validate(green), [])
        failing = green.replace("# fail 0", "# fail 1").replace("ok 2 - second", "not ok 2 - second")
        self.assertTrue(VERIFY_TAP.validate(failing), "a failing point must be rejected")


class MutationAcceptance(unittest.TestCase):
    """REQ-006: the mutation harness and its survivors-json report."""

    def test_req_006_ac1_the_declared_entry_point_and_report_path_are_wired(self):
        self.assertTrue(os.path.isfile(MUTATION), "mutation.sh must sit at the repository root")
        syntax = subprocess.run(
            ["bash", "-n", MUTATION], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        expected = os.path.join("reports", "mutation", "mutation.json")
        self.assertEqual(MUTATION_HARNESS.DEFAULT_REPORT, expected)

    def test_req_006_ac2_at_least_one_mutant_is_recorded(self):
        self.assertGreater(len(MUTATION_HARNESS.MUTANTS), 0, "the mutation check must not be vacuous")
        with open(os.path.join(ROOT, "common_keys.py"), encoding="utf-8") as handle:
            source = handle.read()
        for mutant_id, find, _replace, _description in MUTATION_HARNESS.MUTANTS:
            with self.subTest(mutant=mutant_id):
                self.assertEqual(
                    source.count(find), 1, "each mutant must match the source exactly once"
                )


class AmbiguityAcceptance(unittest.TestCase):
    """REQ-007: the confirmed AMB-001 .. AMB-003 decisions."""

    def test_amb_001_an_empty_array_prints_none_and_exits_zero(self):
        for content in ("[]", "  [ ]  ", "\n[\n]\n"):
            with self.subTest(content=content):
                result = run_entry(content)
                self.assertEqual(result.returncode, 0, "AMB-001 chooses none, not an error")
                self.assertEqual(result.stdout, NONE)
                self.assertEqual(result.stderr, "")

    def test_amb_002_non_object_elements_are_skipped(self):
        for element in ("2", "null", '"x"', "[1]", "true", "1.5"):
            with self.subTest(element=element):
                result = run_entry('[{"a": 1, "b": 2}, %s, {"a": 3, "c": 4}]' % element)
                self.assertEqual(result.returncode, 0, "AMB-002 chooses skip, not an error")
                self.assertEqual(result.stdout, "a\n")
                self.assertEqual(result.stderr, "")

    def test_amb_002_an_array_of_only_non_objects_prints_none(self):
        result = run_entry('[1, "x", null, [1], true]')
        self.assertEqual(result.returncode, 0, "AMB-002 skip leaves an empty intersection")
        self.assertEqual(result.stdout, NONE)

    def test_amb_001_amb_002_an_empty_object_is_an_object_but_an_empty_array_is_not(self):
        """The two decisions meet at the element's JSON type.

        An empty object is still an object, so it removes every key; an empty
        array is not an object, so AMB-002 skips it and the other objects keep
        their common key. An array of only empty arrays has no object at all.
        """
        result = run_entry('[{"a": 1}, {}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, NONE)
        result = run_entry('[{"a": 1}, []]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "a\n")
        result = run_entry('[[]]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, NONE)

    def test_amb_003_unusable_input_is_a_clean_non_zero_stop_error(self):
        cases = {
            "invalid JSON": "{not json",
            "non-standard NaN constant": '[{"a": NaN}]',
            "non-standard Infinity constant": '[{"a": Infinity}]',
            "empty file": "",
            "top level object": '{"a": 1}',
            "top level string": '"hello"',
            "top level number": "42",
        }
        for label, content in cases.items():
            with self.subTest(case=label):
                result = run_entry(content)
                self.assertNotEqual(result.returncode, 0, "AMB-003 chooses error")
                self.assertEqual(result.stdout, "", "no result lines on the error path")
                self.assertNotEqual(result.stderr.strip(), "", "a diagnostic is required")
                self.assertNotIn("Traceback", result.stderr, "a diagnostic, not a crash")

    def test_amb_003_non_standard_constants_are_rejected_in_every_position(self):
        cases = [
            "NaN",
            "Infinity",
            "-Infinity",
            "[NaN]",
            "[1, Infinity]",
            '[{"a": NaN}]',
            '[{"a": Infinity}]',
            '[{"a": -Infinity}]',
            '[{"a": [Infinity]}]',
            '[{"a": {"b": -Infinity}}]',
            '{"a": NaN}',
        ]
        for content in cases:
            with self.subTest(content=content):
                result = run_entry(content)
                self.assertNotEqual(result.returncode, 0, "NaN/Infinity are not JSON (AMB-003)")
                self.assertEqual(result.stdout, "", "no result lines on the error path")
                self.assertNotEqual(result.stderr.strip(), "", "a diagnostic is required")
                self.assertNotIn("Traceback", result.stderr, "a diagnostic, not a crash")

    def test_amb_003_constant_names_inside_json_strings_are_ordinary_data(self):
        result = run_entry('[{"NaN": "Infinity"}, {"NaN": "-Infinity"}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "NaN\n")
        self.assertEqual(result.stderr, "")

    def test_amb_003_missing_or_unreadable_path_is_a_stop_error(self):
        missing = os.path.join(ROOT, "no-such-input-file.json")
        for path in (missing, tempfile.gettempdir()):
            with self.subTest(path=path):
                result = run_path(path)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertNotEqual(result.stderr.strip(), "")
                self.assertNotIn("Traceback", result.stderr)

    def test_amb_003_a_permission_denial_is_a_stop_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        denial = PermissionError(13, "Permission denied")
        with mock.patch("builtins.open", side_effect=denial):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = COMMON_KEYS.main(["common_keys.py", "unreadable.json"])
        self.assertNotEqual(status, 0, "AMB-003: an unreadable file is an error")
        self.assertEqual(stdout.getvalue(), "", "no result lines on the error path")
        self.assertIn("cannot read", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_amb_003_a_read_error_after_open_is_a_stop_error(self):
        """AMB-003 `unreadable` also covers a read that fails after a successful open.

        /proc/self/mem opens but fails on read, so this drives the OSError
        branch at handle.read() at the process boundary. The path is
        Linux-specific; where it is absent the mocked-open case above still
        covers the same branch.
        """
        path = "/proc/self/mem"
        if not os.path.exists(path):
            self.skipTest("no /proc/self/mem to provoke a read error on this platform")
        result = run_path(path)
        self.assertNotEqual(result.returncode, 0, "a read failure must exit non-zero")
        self.assertEqual(result.stdout, "", "no result lines on the error path")
        self.assertIn("cannot read", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class UnitAcceptance(unittest.TestCase):
    """Unit-level checks of the parsing and intersection functions."""

    def test_parse_rejects_non_array_and_malformed_json(self):
        for text in ('{"a": 1}', '"x"', "42", "null", "true", "{", ""):
            with self.subTest(text=text):
                with self.assertRaises(COMMON_KEYS.InputError):
                    COMMON_KEYS.parse(text)

    def test_reject_constant_guards_pythons_non_standard_extensions(self):
        for name in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    COMMON_KEYS.reject_constant(name)
                with self.assertRaises(COMMON_KEYS.InputError):
                    COMMON_KEYS.parse("[%s]" % name)

    def test_parse_accepts_standard_json_numbers(self):
        self.assertEqual(
            COMMON_KEYS.parse("[0, -2.5, 1e3, 0.5E-2, 1.0, -0]"),
            [0, -2.5, 1000.0, 0.005, 1.0, 0],
        )

    def test_parse_returns_the_array_elements(self):
        self.assertEqual(COMMON_KEYS.parse('[{"a": 1}, 2, null]'), [{"a": 1}, 2, None])
        self.assertEqual(COMMON_KEYS.parse("[]"), [])

    def test_common_keys_intersects_and_orders(self):
        self.assertEqual(COMMON_KEYS.common_keys([{"a": 1, "b": 2}, {"a": 3, "c": 4}]), ["a"])
        self.assertEqual(COMMON_KEYS.common_keys([{"z": 1, "A": 2, "a": 3}]), ["A", "a", "z"])
        self.assertEqual(COMMON_KEYS.common_keys([]), [])
        self.assertEqual(COMMON_KEYS.common_keys([{"a": 1}, 7, {"a": 2}]), ["a"])


if __name__ == "__main__":
    unittest.main()
