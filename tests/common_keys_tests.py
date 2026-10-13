#!/usr/bin/env python3
"""The delivered test suite for common-keys.sh (writes reports/tests.tap).

Every integration case drives the DELIVERED entry point exactly as the
requirement document declares it -- ``bash common-keys.sh <json-file>`` -- on a
hand-built JSON fixture, and asserts what the document declares:

* REQ-001 the entry point and its single positional argument
* REQ-002 the input is one JSON array of objects
* REQ-003 a key is reported only when every object carries it
* REQ-004 one key per line, sorted in ascending order
* REQ-005 the single word ``none`` when no key is common
* REQ-006 this suite and its TAP report
* REQ-007 / AMB-001 top-level keys only, never flattened paths
* REQ-007 / AMB-002 a malformed input is a clean non-zero stop-error
* REQ-007 / AMB-003 an array with no objects prints ``none``
* REQ-007 / AMB-004 codepoint order, so uppercase precedes lowercase

The suite also imports common_keys.py directly for a few unit cases, so the
same contract is pinned on both sides of the process boundary. It writes the
TAP report to the path the document names (reports/tests.tap) and exits 0 only
when every case passes, so ``bash run-tests.sh`` is a gate.
"""

import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "common-keys.sh")
RUNNER = os.path.join(ROOT, "run-tests.sh")
REPORT = os.path.join(ROOT, "reports", "tests.tap")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ci.yml")

sys.path.insert(0, ROOT)

_SPEC = importlib.util.spec_from_file_location(
    "common_keys_under_test", os.path.join(ROOT, "common_keys.py")
)
common_keys_module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(common_keys_module)

CASES = []


def case(function):
    """Register a test function under its own name, in declaration order."""
    CASES.append(function)
    return function


def run(args, stdin=subprocess.DEVNULL):
    """Invoke the delivered entry point exactly as the document declares it."""
    return subprocess.run(
        ["bash", ENTRY] + list(args),
        capture_output=True,
        text=True,
        stdin=stdin,
        timeout=30,
    )


def write_input(directory, content):
    """Write a fixture and return its path."""
    path = os.path.join(directory, "input.json")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    return path


def invoke(content):
    """Run the entry point on a fixture and return the completed process."""
    with tempfile.TemporaryDirectory() as directory:
        path = write_input(directory, content)
        return run([path])


def answer(content):
    """Return the whole stdout of a well-formed input (asserts exit 0)."""
    result = invoke(content)
    assert result.returncode == 0, "a well-formed input must exit 0, got %d (%s)" % (
        result.returncode,
        result.stderr.strip(),
    )
    return result.stdout


def expect_output(content, wanted, why):
    got = answer(content)
    assert got == wanted, "%s: expected %r, got %r" % (why, wanted, got)


def expect_keys(content, keys, why):
    expect_output(content, "".join(key + "\n" for key in keys), why)


def expect_none(content, why):
    expect_output(content, "none\n", why)


def expect_reject(content, why):
    """A malformed input: non-zero, a stderr diagnostic, nothing on stdout."""
    result = invoke(content)
    assert result.returncode != 0, "%s: expected a non-zero exit, got 0" % why
    assert result.stdout == "", "%s: stdout must be empty, got %r" % (why, result.stdout)
    assert result.stderr.strip() != "", "%s: a diagnostic is required on stderr" % why
    assert "Traceback" not in result.stderr, (
        "%s: the stop-error must be a diagnostic, not a crash: %s" % (why, result.stderr)
    )


def parse_error(text, why):
    try:
        common_keys_module.parse(text)
    except common_keys_module.InputError:
        return
    raise AssertionError("%s: parse must raise InputError" % why)


def load_workflow():
    with open(WORKFLOW, encoding="utf-8") as handle:
        return handle.read()


def workflow_code():
    """The workflow without its comment lines, i.e. what the runner executes."""
    return "\n".join(
        line for line in load_workflow().splitlines() if not line.strip().startswith("#")
    )


# --- REQ-001: the declared entry point ----------------------------------------


@case
def req_001_entry_point_prints_the_shared_keys():
    expect_keys('[{"a": 1, "b": 2}, {"a": 3, "b": 4}]', ["a", "b"], "two shared keys")


@case
def req_001_missing_argument_is_a_non_zero_usage_error():
    result = run([])
    assert result.returncode != 0, "a missing argument must exit non-zero"
    assert result.stdout == "", "a usage error must print nothing on stdout"
    assert result.stderr.strip() != "", "a usage error must print a diagnostic"


@case
def req_001_extra_argument_is_rejected():
    with tempfile.TemporaryDirectory() as directory:
        path = write_input(directory, '[{"a": 1}]')
        result = run([path, "extra"])
    assert result.returncode != 0, "an extra argument must exit non-zero"
    assert result.stdout == "", "an extra argument must print nothing on stdout"


@case
def req_001_unreadable_file_is_a_stop_error():
    result = run([os.path.join(ROOT, "does-not-exist.json")])
    assert result.returncode != 0, "an unreadable file must exit non-zero"
    assert result.stdout == "", "an unreadable file must print nothing on stdout"
    assert result.stderr.strip() != "", "an unreadable file needs a diagnostic"


# --- REQ-002: the input is an array of objects --------------------------------


@case
def req_002_a_well_formed_array_of_objects_is_accepted():
    expect_keys('[{"x": 1}, {"x": 2, "y": 3}]', ["x"], "an array of objects is valid")
    expect_none("[{}]", "an array holding one empty object has no shared key")


@case
def req_002_a_top_level_object_is_rejected():
    expect_reject('{"a": 1}', "an object is not an array")
    parse_error('{"a": 1}', "parse rejects a bare object")


@case
def req_002_a_top_level_string_is_rejected():
    expect_reject('"hello"', "a string is not an array")
    parse_error('"hello"', "parse rejects a string")


@case
def req_002_a_top_level_number_is_rejected():
    expect_reject("42", "a number is not an array")
    parse_error("42", "parse rejects a number")


@case
def req_002_a_top_level_null_or_bool_is_rejected():
    expect_reject("null", "null is not an array")
    expect_reject("true", "true is not an array")
    parse_error("null", "parse rejects null")
    parse_error("false", "parse rejects false")


@case
def req_002_a_non_object_element_is_rejected():
    for element in ("2", "null", '"x"', "[1]", "true"):
        expect_reject('[{"a": 1}, %s]' % element, "element %s is not an object" % element)
    parse_error('[{"a": 1}, 2]', "parse rejects a numeric element")


@case
def req_002_a_trailing_value_after_the_array_is_rejected():
    expect_reject('[{"a": 1}] [{"b": 2}]', "two JSON values are not one value")
    expect_reject('[{"a": 1}] trailing', "trailing text is not valid JSON")


# --- REQ-003: keys common to every object -------------------------------------


@case
def req_003_a_key_missing_from_one_object_is_not_printed():
    expect_keys('[{"a": 1, "b": 2}, {"a": 3, "c": 4}]', ["a"], "b is missing from one object")
    expect_keys('[{"a": 1, "b": 1}, {"a": 2, "b": 2}, {"a": 3}]', ["a"], "b is missing from the last")


@case
def req_003_a_key_present_in_every_object_is_printed():
    expect_keys('[{"a": 1}, {"a": 2}, {"a": 3}]', ["a"], "a is in every object")
    expect_keys(
        '[{"k": 1, "m": 1}, {"k": 2, "m": 2}, {"k": 3, "m": 3}]',
        ["k", "m"],
        "both keys are in every object",
    )


@case
def req_003_only_the_shared_keys_are_printed():
    expect_keys(
        '[{"a": 1, "b": 2, "c": 3}, {"a": 4, "c": 5, "d": 6}]',
        ["a", "c"],
        "the union of one-sided keys is not printed",
    )


@case
def req_003_a_single_object_shares_all_its_own_keys():
    expect_keys('[{"one": 1, "two": 2, "three": 3}]', ["one", "three", "two"], "one object")
    expect_keys('[{"one": 1, "two": 2, "three": 3}]', ["one", "three", "two"], "repeated")


@case
def req_003_duplicate_json_keys_collapse_to_one_key():
    expect_keys('[{"a": 1, "a": 2}, {"a": 3}]', ["a"], "a repeated key is still one key")


# --- REQ-004: one per line, sorted --------------------------------------------


@case
def req_004_each_shared_key_is_on_its_own_line_with_no_extra_text():
    got = answer('[{"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 2, "c": 3}]')
    assert got == "a\nb\nc\n", got
    assert got.count("\n") == 3, "exactly one newline per key"


@case
def req_004_keys_are_sorted_in_ascending_order():
    expect_keys('[{"b": 1, "a": 2, "c": 3, "A": 4}, {"b": 1, "a": 2, "c": 3, "A": 4}]',
                ["A", "a", "b", "c"], "sorted ascending")


@case
def req_004_codepoint_order_puts_uppercase_before_lowercase():
    expect_keys(
        '[{"a": 1, "A": 2, "B": 3, "b": 4}, {"a": 1, "A": 2, "B": 3, "b": 4}]',
        ["A", "B", "a", "b"],
        "codepoint order, not case-insensitive",
    )


@case
def req_004_codepoint_order_over_digits_and_symbols():
    shared = '{"1": 1, "A": 2, "_": 3, "z": 4}'
    expect_keys("[%s, %s]" % (shared, shared), ["1", "A", "_", "z"], "codepoint order")


@case
def req_004_codepoint_order_over_unicode():
    shared = '{"z": 1, "\\u00e9": 2, "\\u03a9": 3}'
    expect_keys("[%s, %s]" % (shared, shared), ["z", "\u00e9", "\u03a9"], "unicode code points")


@case
def req_004_codepoint_order_is_not_length_order():
    expect_keys(
        '[{"a": 1, "bb": 2, "c": 3}, {"a": 1, "bb": 2, "c": 3}]',
        ["a", "bb", "c"],
        "a key is ordered by its code points, not by its length",
    )


@case
def req_004_output_uses_plain_lf_without_carriage_returns():
    with tempfile.TemporaryDirectory() as directory:
        path = write_input(directory, '[{"a": 1, "b": 2}, {"a": 3, "b": 4}]')
        result = subprocess.run(
            ["bash", ENTRY, path],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"a\nb\n", result.stdout
    assert b"\r" not in result.stdout, "the output must not contain carriage returns"


# --- REQ-005: none when no key is common --------------------------------------


@case
def req_005_disjoint_objects_print_none():
    expect_none('[{"a": 1}, {"b": 2}]', "no shared key")
    expect_none('[{"a": 1, "b": 2}, {"c": 3, "d": 4}]', "disjoint key sets")


@case
def req_005_none_is_not_printed_when_a_key_is_shared():
    got = answer('[{"a": 1, "b": 2}, {"a": 3}]')
    assert got == "a\n", got
    assert "none" not in got, "the literal none is only for an empty intersection"


@case
def req_005_an_array_of_empty_objects_prints_none():
    expect_none("[{}, {}]", "the only common keys of empty objects are none")
    expect_none('[{"a": 1}, {}]', "an empty object shares no key")


@case
def amb_003_an_empty_array_prints_none():
    expect_none("[]", "AMB-003: an array with no objects prints none")
    expect_none("  [ ]  ", "AMB-003 still holds around whitespace")


# --- AMB-001: only top-level keys count ---------------------------------------


@case
def amb_001_nested_keys_are_not_flattened_into_paths():
    expect_keys(
        '[{"a": {"b": 1}}, {"a": {"c": 2}}]',
        ["a"],
        "the nested keys b and c never become a.b or a.c",
    )


@case
def amb_001_a_key_nested_in_one_object_does_not_count_as_top_level():
    expect_keys(
        '[{"x": {"y": 1}}, {"x": 2}]',
        ["x"],
        "y is nested in the first object and must not join the intersection",
    )


@case
def amb_001_nested_and_top_level_keys_are_distinguished():
    expect_keys(
        '[{"outer": {"inner": 1}}, {"outer": 2, "inner": 3}]',
        ["outer"],
        "inner is top-level only in the second object",
    )


# --- AMB-002: malformed input is a clean stop-error ---------------------------


@case
def amb_002_invalid_json_is_a_clean_stop_error():
    for text in ("", "   ", "{not json", "[{", "[{\"a\": }]", "NaN", "[1,]"):
        expect_reject(text, "invalid JSON %r" % text)
    parse_error("", "parse rejects an empty file")


@case
def amb_002_a_non_object_element_has_a_readable_diagnostic():
    result = invoke('[{"a": 1}, 2]')
    assert result.returncode != 0, "a non-object element must be rejected"
    assert result.stdout == "", "no key list may be printed on rejection"
    assert "element" in result.stderr, "the diagnostic should name the element: %s" % result.stderr
    assert "Traceback" not in result.stderr, "the rejection must not be a crash"


@case
def amb_002_a_non_array_top_level_value_has_a_readable_diagnostic():
    result = invoke('{"a": 1}')
    assert result.returncode != 0, "a non-array top level must be rejected"
    assert "array" in result.stderr, "the diagnostic should name the array: %s" % result.stderr


# --- unit cases over common_keys.py -------------------------------------------


@case
def unit_parse_returns_the_array_of_objects():
    assert common_keys_module.parse('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]
    assert common_keys_module.parse("[]") == []


@case
def unit_common_keys_is_the_intersection():
    assert common_keys_module.common_keys([{"a": 1, "b": 2}, {"a": 3, "c": 4}]) == ["a"]
    assert common_keys_module.common_keys([{"b": 1, "a": 2}]) == ["a", "b"]
    assert common_keys_module.common_keys([]) == []
    assert common_keys_module.common_keys([{}, {}]) == []


@case
def unit_common_keys_orders_by_code_point():
    keys = common_keys_module.common_keys([{"z": 1, "A": 2, "_": 3, "1": 4}])
    assert keys == ["1", "A", "_", "z"], keys


@case
def unit_main_writes_none_for_an_empty_array():
    import io
    with tempfile.TemporaryDirectory() as directory:
        path = write_input(directory, "[]")
        stdout = io.StringIO()
        stderr = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout, stderr
        try:
            status = common_keys_module.main(["common_keys.py", path])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
    assert status == 0, status
    assert stdout.getvalue() == "none\n", stdout.getvalue()


# --- the delivered pipeline ---------------------------------------------------


@case
def pipeline_runs_the_declared_commands():
    code = workflow_code()
    assert "bash run-tests.sh" in code, "the pipeline must run the delivered suite"
    assert "bash common-keys.sh" in code, "the pipeline must run the declared entry point"
    assert "reports/tests.tap" in code, "the pipeline must read the declared TAP report"
    assert "reports/mutation/mutation.json" in code, "the mutation report path must be named"
    assert "npx stryker run --reporters json" in code, "the declared mutation command must run"
    assert "common-keys.sh {json}" not in code, "the placeholder must not survive"
    assert "pnpm test" not in code, "the pipeline must run the declared suite, not a guess"


# --- independent verification layer -------------------------------------------
#
# The cases below re-verify the same contract with machinery written
# independently of the delivered implementation: a count-based oracle instead
# of the implementation's start-from-the-first-object-and-intersect loop, and a
# seeded differential that compares that oracle with both the in-process logic
# and the real entry point. A mistake shared by the implementation and the
# delivered suite cannot cancel out here, because the oracle is derived from
# the definition rather than from the code. The oracle also sorts with explicit
# Unicode ordinals, a second expression of AMB-004.


# The value alphabet deliberately includes nested objects and arrays, whose
# keys AMB-001 says never count, and case/Unicode letters, which exercise
# AMB-004. It is only ever used through the oracle and the entry point.
def oracle_common_keys(objects):
    """The common keys, counted rather than intersected.

    A key is common exactly when it appears in as many objects as there are:
    count it in every object, keep the counts equal to len(objects), then order
    by explicit Unicode code point. This is the definition in the document, not
    the implementation's algorithm.
    """
    counts = Counter()
    for element in objects:
        counts.update(element.keys())
    total = len(objects)
    return sorted(
        (key for key, count in counts.items() if count == total),
        key=lambda key: [ord(character) for character in key],
    )


def oracle_output(objects):
    """The exact stdout the document declares for a JSON array of objects."""
    keys = oracle_common_keys(objects)
    if keys:
        return "".join(key + "\n" for key in keys)
    return "none\n"


KEYS = ["a", "A", "b", "B", "z", "Z", "_", "1", "\u00e9", "\u03a9", ""]
VALUES = [1, 2.5, "text", None, True, False, [1, 2], {"a": 1, "inner": 2}, {}]


def random_objects(rng, max_objects=6, max_keys=6):
    """Build a random JSON array of objects over the small alphabet above."""
    objects = []
    for _ in range(rng.randint(0, max_objects)):
        element = {}
        for _ in range(rng.randint(0, max_keys)):
            element[rng.choice(KEYS)] = rng.choice(VALUES)
        objects.append(element)
    return objects


@case
def independent_oracle_is_not_trivially_constant():
    """Guard the oracle itself, so the differential below cannot be vacuous."""
    assert oracle_common_keys([]) == []
    assert oracle_common_keys([{}, {}]) == []
    assert oracle_common_keys([{"a": 1}, {"b": 2}]) == []
    assert oracle_common_keys([{"b": 1, "a": 2}, {"a": 3, "b": 4}]) == ["a", "b"]
    assert oracle_common_keys([{"A": 1, "a": 2}, {"A": 3, "a": 4}]) == ["A", "a"]


@case
def independent_oracle_matches_the_intersection_on_random_arrays():
    rng = random.Random(0x5EED)
    for _ in range(1000):
        objects = random_objects(rng)
        got = common_keys_module.common_keys(objects)
        want = oracle_common_keys(objects)
        assert got == want, "common_keys(%r) = %r, oracle = %r" % (objects, got, want)


@case
def independent_oracle_matches_the_entry_point_on_random_arrays():
    rng = random.Random(0xC0FFEE)
    for _ in range(40):
        objects = random_objects(rng)
        got = answer(json.dumps(objects))
        want = oracle_output(objects)
        assert got == want, "CLI on %r = %r, oracle = %r" % (objects, got, want)


@case
def independent_oracle_covers_the_declared_worlds():
    """The all-shared, partially-shared and none worlds, through the oracle."""
    assert oracle_output([{"a": 1, "b": 2}, {"a": 3, "b": 4}]) == "a\nb\n"
    assert oracle_output([{"a": 1, "b": 2}, {"a": 3, "c": 4}]) == "a\n"
    assert oracle_output([{"x": 1}, {"y": 2}]) == "none\n"


@case
def amb_001_nested_keys_do_not_enter_the_independent_oracle():
    objects = [
        {"outer": {"inner": 1, "a": 2}, "top": 1},
        {"outer": {"inner": 3}, "top": 2},
    ]
    assert oracle_common_keys(objects) == ["outer", "top"]
    assert answer(json.dumps(objects)) == "outer\ntop\n"


@case
def amb_002_a_file_that_is_not_utf8_is_a_clean_stop_error():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "bad.json")
        with open(path, "wb") as handle:
            handle.write(b'[{"a": 1}, \xff\xfe]')
        result = subprocess.run(
            ["bash", ENTRY, path],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    assert result.returncode != 0, "an undecodable file must exit non-zero"
    assert result.stdout == "", "an undecodable file must print no key list"
    assert result.stderr.strip() != "", "an undecodable file needs a diagnostic"
    assert "Traceback" not in result.stderr, (
        "the stop-error must be a diagnostic, not a crash: %s" % result.stderr
    )


@case
def amb_002_a_utf8_bom_is_rejected_as_malformed():
    # json.loads rejects a leading BOM rather than silently accepting it, so it
    # is one more malformed class that must take the AMB-002 stop-error path.
    expect_reject("\ufeff[]", "a BOM is not valid JSON")


@case
def amb_003_the_independent_oracle_prints_none_for_no_objects():
    assert oracle_output([]) == "none\n"
    assert answer("[]") == "none\n"
    assert answer("[ ]") == "none\n"


@case
def amb_004_the_independent_oracle_orders_by_code_point():
    objects = [{"b": 1, "A": 2, "a": 3, "B": 4, "1": 5, "_": 6}]
    want = oracle_common_keys(objects)
    assert want == ["1", "A", "B", "_", "a", "b"], want
    assert answer(json.dumps(objects)) == "".join(key + "\n" for key in want)


@case
def req_001_a_directory_argument_is_a_stop_error():
    result = run([tempfile.gettempdir()])
    assert result.returncode != 0, "a directory argument must exit non-zero"
    assert result.stdout == "", "a directory argument must print nothing on stdout"
    assert result.stderr.strip() != "", "a directory argument needs a diagnostic"


# --- the run-tests.sh gate ----------------------------------------------------


def stub_suite(directory, name, report_path, tap, status):
    """Write a tiny self-contained TAP suite that run-tests.sh can drive."""
    path = os.path.join(directory, name)
    source = (
        "import sys\n"
        "with open(%r, 'w', encoding='utf-8') as handle:\n"
        "    handle.write(%r)\n"
        "sys.exit(%d)\n" % (report_path, tap, status)
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)
    return path


def run_runner(test_file):
    """Invoke run-tests.sh with its suite redirected to ``test_file``."""
    env = dict(os.environ, COMMON_KEYS_TEST_FILE=test_file)
    return subprocess.run(
        ["bash", RUNNER],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


@case
def req_006_the_runner_passes_a_green_suite_and_keeps_its_report():
    with tempfile.TemporaryDirectory() as directory:
        report = os.path.join(directory, "green.tap")
        tap = "TAP version 13\n1..1\nok 1 - green\n# tests 1\n# pass 1\n# fail 0\n"
        suite = stub_suite(directory, "green.py", report, tap, 0)
        result = run_runner(suite)
        assert result.returncode == 0, result.stderr
        with open(report, encoding="utf-8") as handle:
            assert handle.read() == tap


@case
def req_006_the_runner_fails_when_its_suite_fails():
    with tempfile.TemporaryDirectory() as directory:
        report = os.path.join(directory, "red.tap")
        tap = "TAP version 13\n1..1\nnot ok 1 - red\n# tests 1\n# pass 0\n# fail 1\n"
        suite = stub_suite(directory, "red.py", report, tap, 1)
        result = run_runner(suite)
        assert result.returncode != 0, "a failing suite must make the runner exit non-zero"
        with open(report, encoding="utf-8") as handle:
            assert "not ok 1" in handle.read()


@case
def req_006_the_runner_rejects_a_missing_suite_file():
    missing = os.path.join(ROOT, "no-such-suite.py")
    result = run_runner(missing)
    assert result.returncode != 0, "a missing suite file must fail the runner"
    assert result.stderr.strip() != "", "the runner should explain the missing file"


@case
def req_006_the_tap_renderer_reports_the_pass_and_fail_totals():
    text = tap_report([("a", True, ""), ("b", False, "boom"), ("c", True, "")])
    assert text.startswith("TAP version 13\n1..3\n"), text
    assert "ok 1 - a\n" in text
    assert "not ok 2 - b\n" in text
    assert "ok 3 - c\n" in text
    assert "# tests 3\n" in text
    assert "# pass 2\n" in text
    assert "# fail 1\n" in text
    assert "message: boom" in text


# --- TAP report ---------------------------------------------------------------


def tap_report(results):
    """Render the results as TAP, with the plan first and a summary last."""
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    lines = ["TAP version 13", "1..%d" % len(results)]
    for index, (name, ok, detail) in enumerate(results, start=1):
        lines.append(("ok %d - %s" if ok else "not ok %d - %s") % (index, name))
        if not ok:
            lines.append("  ---")
            lines.append("  message: %s" % detail.replace("\n", " ").strip())
            lines.append("  ...")
    lines.append("# tests %d" % len(results))
    lines.append("# pass %d" % passed)
    lines.append("# fail %d" % failed)
    return "\n".join(lines) + "\n"


def main():
    results = []
    for function in CASES:
        try:
            function()
        except AssertionError as error:
            results.append((function.__name__, False, str(error)))
        except Exception as error:  # noqa: BLE001 - a crash is a failing test
            results.append((function.__name__, False, "%s: %s" % (type(error).__name__, error)))
        else:
            results.append((function.__name__, True, ""))

    report = tap_report(results)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as handle:
        handle.write(report)
    sys.stdout.write(report)

    failed = [name for name, ok, _ in results if not ok]
    if failed:
        sys.stderr.write("common-keys tests: %d of %d failed\n" % (len(failed), len(results)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
