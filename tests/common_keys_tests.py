#!/usr/bin/env python3
"""The delivered test suite for common-keys.sh (writes reports/tests.tap).

Every integration case drives the DELIVERED entry point exactly as the
requirement document declares it -- ``bash common-keys.sh <json-file>`` -- on a
hand-built JSON fixture, and asserts what the document declares:

* REQ-001 the entry point and its single positional argument
* REQ-002 the input is one JSON array; a key is an object's own top-level name
* REQ-003 one key per line, ascending Unicode code point order
* REQ-004 the single word ``none`` when no key is common
* REQ-005 this suite and its TAP report
* REQ-006 the declared ``bash mutation.sh`` entry point and report
* REQ-007 / AMB-001 an empty array prints ``none`` and exits zero
* REQ-007 / AMB-002 a non-object element is skipped, not rejected
* REQ-007 / AMB-003 an unusable input is a clean non-zero stop-error

The suite also imports common_keys.py directly for a few unit cases, so the
same contract is pinned on both sides of the process boundary. It writes the
TAP report to the path the document names (reports/tests.tap) and exits 0 only
when every case passes, so ``bash run-tests.sh`` is a gate.
"""

import importlib.util
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "common-keys.sh")
RUNNER = os.path.join(ROOT, "run-tests.sh")
MUTATION = os.path.join(ROOT, "mutation.sh")
REPORT = os.path.join(ROOT, "reports", "tests.tap")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ci.yml")

sys.path.insert(0, ROOT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common_keys_module = _load("common_keys_under_test", os.path.join(ROOT, "common_keys.py"))
mutation_module = _load(
    "mutation_under_test", os.path.join(ROOT, "mutation", "common_keys_mutation.py")
)

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


def write_input(directory, content, name="input.json"):
    """Write a fixture (LF endings, UTF-8) and return its path."""
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    return path


def invoke(content):
    """Run the entry point on a fixture and return the completed process."""
    with tempfile.TemporaryDirectory() as directory:
        path = write_input(directory, content)
        return run([path])


def answer(content):
    """Return the whole stdout of a well-formed input (asserts exit 0).

    REQ-001 AC2: a successful answer goes to standard output and nothing at all
    is written to standard error, so every success case also pins the stream.
    """
    result = invoke(content)
    assert result.returncode == 0, "a well-formed input must exit 0, got %d (%s)" % (
        result.returncode,
        result.stderr.strip(),
    )
    assert result.stderr == "", (
        "a successful answer must write nothing to stderr, got %r" % result.stderr
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
    """An unusable input: non-zero, a stderr diagnostic, nothing on stdout."""
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


@case
def req_001_a_directory_argument_is_a_stop_error():
    result = run([tempfile.gettempdir()])
    assert result.returncode != 0, "a directory argument must exit non-zero"
    assert result.stdout == "", "a directory argument must print nothing on stdout"
    assert result.stderr.strip() != "", "a directory argument needs a diagnostic"


@case
def req_001_the_entry_point_is_the_declared_root_script():
    """REQ-001 names the deliverable exactly: common-keys.sh at the root."""
    assert os.path.isfile(ENTRY), "REQ-001: common-keys.sh must exist at the repository root"
    assert os.path.basename(ENTRY) == "common-keys.sh", ENTRY
    assert os.path.dirname(ENTRY) == ROOT, "the entry point must sit at the repository root"


# --- REQ-002: the input is an array of objects --------------------------------


@case
def req_002_a_well_formed_array_of_objects_is_accepted():
    expect_keys('[{"x": 1}, {"x": 2, "y": 3}]', ["x"], "an array of objects is valid")
    expect_none("[{}]", "an array holding one empty object has no shared key")


@case
def req_002_the_declared_three_object_example_reports_only_a():
    expect_keys(
        '[{"a": 1, "b": 2}, {"a": 3, "c": 4}, {"a": 5, "b": 6}]',
        ["a"],
        "REQ-002: {a,b}, {a,c}, {a,b} share only a",
    )


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
def req_002_a_trailing_value_after_the_array_is_rejected():
    expect_reject('[{"a": 1}] [{"b": 2}]', "two JSON values are not one value")
    expect_reject('[{"a": 1}] trailing', "trailing text is not valid JSON")


@case
def req_002_duplicate_json_keys_collapse_to_one_key():
    expect_keys('[{"a": 1, "a": 2}, {"a": 3}]', ["a"], "a repeated key is still one key")


# --- REQ-003 (the intersection): keys common to every object ------------------


@case
def req_003_a_key_missing_from_one_object_is_not_printed():
    expect_keys('[{"a": 1, "b": 2}, {"a": 3, "c": 4}]', ["a"], "b is missing from one object")
    expect_keys(
        '[{"a": 1, "b": 1}, {"a": 2, "b": 2}, {"a": 3}]', ["a"], "b is missing from the last"
    )
    expect_keys(
        '[{"a": 1}, {"a": 2, "b": 2}, {"a": 3, "b": 3}]', ["a"], "b is missing from the first"
    )
    expect_keys(
        '[{"a": 1, "b": 1}, {"a": 2}, {"a": 3, "b": 3}]', ["a"], "b is missing from the middle"
    )


@case
def req_003_a_key_named_none_is_printed_as_a_key():
    """The literal key `none` is data, not the sentinel the document declares."""
    expect_keys('[{"none": 1}, {"none": 2}]', ["none"], "none is a perfectly ordinary key name")
    expect_none('[{"none": 1}, {"other": 2}]', "no key is shared, so the sentinel is printed")


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
    expect_keys('[{"three": 1, "one": 2, "two": 3}]', ["one", "three", "two"], "repeated")


@case
def req_003_multi_character_keys_are_ordered_lexicographically():
    expect_keys(
        '[{"a": 1, "ab": 2, "b": 3}, {"a": 4, "ab": 5, "b": 6}]',
        ["a", "ab", "b"],
        "a prefix sorts before the longer key that extends it",
    )
    expect_keys(
        '[{"ab": 1, "b": 2}, {"ab": 3, "b": 4}]',
        ["ab", "b"],
        "a longer key is not reordered by its spelling reversed",
    )


@case
def req_003_nested_keys_are_not_objects_keys():
    expect_keys(
        '[{"a": {"b": 1}}, {"a": {"c": 2}}]',
        ["a"],
        "the nested keys b and c are not keys of the objects",
    )
    expect_keys(
        '[{"outer": {"inner": 1}}, {"outer": 2, "inner": 3}]',
        ["outer"],
        "inner is a top-level key only in the second object",
    )


# --- REQ-003: one per line, sorted --------------------------------------------


@case
def req_003_each_shared_key_is_on_its_own_line_with_no_extra_text():
    got = answer('[{"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 2, "c": 3}]')
    assert got == "a\nb\nc\n", got
    assert got.count("\n") == 3, "exactly one newline per key"


@case
def req_003_keys_are_sorted_in_ascending_order():
    expect_keys(
        '[{"b": 1, "a": 2, "c": 3, "A": 4}, {"b": 1, "a": 2, "c": 3, "A": 4}]',
        ["A", "a", "b", "c"],
        "sorted ascending",
    )


@case
def req_003_the_declared_ordering_example_is_a_b_c():
    expect_keys(
        '[{"b": 1, "a": 2, "c": 3}, {"b": 4, "a": 5, "c": 6}]',
        ["a", "b", "c"],
        "REQ-003: the common keys {b,a,c} are emitted a, b, c",
    )


@case
def req_003_codepoint_order_puts_uppercase_before_lowercase():
    expect_keys(
        '[{"a": 1, "A": 2, "B": 3, "b": 4}, {"a": 1, "A": 2, "B": 3, "b": 4}]',
        ["A", "B", "a", "b"],
        "codepoint order, not case-insensitive",
    )


@case
def req_003_codepoint_order_over_digits_and_symbols():
    shared = '{"1": 1, "A": 2, "_": 3, "z": 4}'
    expect_keys("[%s, %s]" % (shared, shared), ["1", "A", "_", "z"], "codepoint order")


@case
def req_003_codepoint_order_over_unicode():
    shared = '{"z": 1, "\\u00e9": 2, "\\u03a9": 3}'
    expect_keys("[%s, %s]" % (shared, shared), ["z", "\u00e9", "\u03a9"], "unicode code points")


@case
def req_003_codepoint_order_is_not_length_order():
    expect_keys(
        '[{"a": 1, "bb": 2, "c": 3}, {"a": 1, "bb": 2, "c": 3}]',
        ["a", "bb", "c"],
        "a key is ordered by its code points, not by its length",
    )


@case
def req_003_output_uses_plain_lf_without_carriage_returns():
    with tempfile.TemporaryDirectory() as directory:
        path = write_input(directory, '[{"a": 1, "b": 2}, {"a": 3, "b": 4}]')
        result = subprocess.run(
            ["bash", ENTRY, path], capture_output=True, stdin=subprocess.DEVNULL, timeout=30
        )
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"a\nb\n", result.stdout
    assert b"\r" not in result.stdout, "the output must not contain carriage returns"


# --- REQ-004: none when no key is common --------------------------------------


@case
def req_004_disjoint_objects_print_none():
    expect_none('[{"a": 1}, {"b": 2}]', "no shared key")
    expect_none('[{"a": 1, "b": 2}, {"c": 3, "d": 4}]', "disjoint key sets")


@case
def req_004_none_is_not_printed_when_a_key_is_shared():
    got = answer('[{"a": 1, "b": 2}, {"a": 3}]')
    assert got == "a\n", got
    assert "none" not in got, "the literal none is only for an empty intersection"


@case
def req_004_an_array_of_empty_objects_prints_none():
    expect_none("[{}, {}]", "the only common keys of empty objects are none")
    expect_none('[{"a": 1}, {}]', "an empty object shares no key")


# --- AMB-001: an array with no objects prints none ----------------------------


@case
def amb_001_an_empty_array_prints_none():
    expect_none("[]", "AMB-001: an array with no objects prints none")
    expect_none("  [ ]  ", "AMB-001 still holds around whitespace")


# --- AMB-002: a non-object element is skipped ---------------------------------


@case
def amb_002_a_non_object_element_is_skipped():
    for element in ("2", "null", '"x"', "[1]", "true"):
        expect_keys(
            '[{"a": 1, "b": 2}, %s, {"a": 3, "c": 4}]' % element,
            ["a"],
            "element %s is skipped and the objects still intersect" % element,
        )


@case
def amb_002_an_object_before_or_after_the_objects_still_counts():
    expect_keys('[2, {"a": 1, "b": 2}, {"a": 3, "b": 4}]', ["a", "b"], "a leading non-object")
    expect_keys('[{"a": 1, "b": 2}, {"a": 3, "b": 4}, null]', ["a", "b"], "a trailing non-object")
    expect_keys(
        '[null, {"a": 1}, [1, 2], {"a": 3}, "x"]', ["a"], "non-objects around and between objects"
    )


@case
def amb_002_the_objects_still_contribute_when_a_non_object_is_present():
    expect_keys('[{"a": 1}, 2, {"a": 3}]', ["a"], "the two objects still share a")


@case
def amb_002_a_lone_object_keeps_all_its_keys_beside_non_objects():
    expect_keys(
        '[{"a": 1, "b": 2}, 7, null, "x"]',
        ["a", "b"],
        "AMB-002: the one object still contributes all its keys",
    )


@case
def amb_002_an_array_of_only_non_objects_prints_none():
    expect_none("[1, 2, 3]", "no object element, so no key is common")
    expect_none('[null, "x", [1], true]', "no object element, so no key is common")


@case
def amb_002_a_non_object_element_does_not_crash_the_command():
    result = invoke('[{"a": 1}, 2]')
    assert result.returncode == 0, "a non-object element must be skipped, not rejected"
    assert result.stdout == "a\n", result.stdout
    assert "Traceback" not in result.stderr, result.stderr


@case
def amb_002_common_keys_skips_non_objects():
    assert common_keys_module.common_keys([{"a": 1}, 2, {"a": 3, "b": 4}]) == ["a"]
    assert common_keys_module.common_keys([1, 2, 3]) == []
    assert common_keys_module.common_keys([{"a": 1}, [1, 2], {"a": 2}]) == ["a"]


# --- AMB-003: unusable input is a clean stop-error ----------------------------


@case
def amb_003_invalid_json_is_a_clean_stop_error():
    for text in ("", "   ", "{not json", "[{", '[{"a": }]', "NaN", "[1,]"):
        expect_reject(text, "invalid JSON %r" % text)
    parse_error("", "parse rejects an empty file")


@case
def amb_003_a_non_array_top_level_value_has_a_readable_diagnostic():
    result = invoke('{"a": 1}')
    assert result.returncode != 0, "a non-array top level must be rejected"
    assert "array" in result.stderr, "the diagnostic should name the array: %s" % result.stderr
    assert "Traceback" not in result.stderr, "the rejection must not be a crash"


@case
def amb_003_a_file_that_is_not_utf8_is_a_clean_stop_error():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "bad.json")
        with open(path, "wb") as handle:
            handle.write(b'[{"a": 1}, \xff\xfe]')
        result = subprocess.run(
            ["bash", ENTRY, path], capture_output=True, text=True, timeout=30
        )
    assert result.returncode != 0, "an undecodable file must exit non-zero"
    assert result.stdout == "", "an undecodable file must print no key list"
    assert result.stderr.strip() != "", "an undecodable file needs a diagnostic"
    assert "Traceback" not in result.stderr, (
        "the stop-error must be a diagnostic, not a crash: %s" % result.stderr
    )


@case
def amb_003_a_utf8_bom_is_rejected_as_malformed():
    # json.loads rejects a leading BOM rather than silently accepting it, so it
    # is one more malformed class that must take the AMB-003 stop-error path.
    expect_reject("\ufeff[]", "a BOM is not valid JSON")


# --- unit cases over common_keys.py -------------------------------------------


@case
def unit_parse_returns_the_whole_array():
    assert common_keys_module.parse('[{"a": 1}, 2, null]') == [{"a": 1}, 2, None]
    assert common_keys_module.parse("[]") == []


@case
def unit_main_prints_a_sorted_intersection():
    with tempfile.TemporaryDirectory() as directory:
        path = write_input(directory, '[{"b": 1, "a": 2}, {"b": 3, "a": 4}]')
        stdout = io.StringIO()
        stderr = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout, stderr
        try:
            status = common_keys_module.main(["common_keys.py", path])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
    assert status == 0, status
    assert stdout.getvalue() == "a\nb\n", stdout.getvalue()
    assert stderr.getvalue() == "", stderr.getvalue()


@case
def unit_main_reports_an_input_error_without_writing_a_result():
    with tempfile.TemporaryDirectory() as directory:
        path = write_input(directory, '{"not": "an array"}')
        stdout = io.StringIO()
        stderr = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout, stderr
        try:
            status = common_keys_module.main(["common_keys.py", path])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
    assert status != 0, "an unusable input must be a non-zero status"
    assert stdout.getvalue() == "", stdout.getvalue()
    assert stderr.getvalue().strip() != "", "the failure needs a diagnostic"


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


# --- independent verification layer -------------------------------------------
#
# The cases below re-verify the same contract with machinery written
# independently of the delivered implementation: a count-based oracle instead
# of the implementation's start-from-the-first-object-and-intersect loop, and a
# seeded differential that compares that oracle with both the in-process logic
# and the real entry point. A mistake shared by the implementation and the
# delivered suite cannot cancel out here, because the oracle is derived from
# the definition rather than from the code. The oracle also sorts with explicit
# Unicode ordinals, a second expression of the code-point order the document
# declares.


def oracle_common_keys(elements):
    """The common keys, counted rather than intersected.

    A key is common exactly when it appears in as many OBJECT elements as there
    are object elements (AMB-002: a non-object element contributes nothing and
    is not counted among the objects). The counts are then ordered by explicit
    Unicode code point. This is the definition in the document, not the
    implementation's algorithm.
    """
    objects = [element for element in elements if isinstance(element, dict)]
    counts = Counter()
    for element in objects:
        counts.update(element.keys())
    total = len(objects)
    return sorted(
        (key for key, count in counts.items() if count == total),
        key=lambda key: [ord(character) for character in key],
    )


def oracle_output(elements):
    """The exact stdout the document declares for a JSON array."""
    keys = oracle_common_keys(elements)
    if keys:
        return "".join(key + "\n" for key in keys)
    return "none\n"


KEYS = ["a", "A", "b", "B", "z", "Z", "_", "1", "ab", "b", "\u00e9", "\u03a9", ""]
VALUES = [1, 2.5, "text", None, True, False, [1, 2], {"a": 1, "inner": 2}, {}]
NON_OBJECTS = [1, 2.5, "text", None, True, [1, 2], [], "x"]


def random_object(rng, max_keys=6):
    element = {}
    for _ in range(rng.randint(0, max_keys)):
        element[rng.choice(KEYS)] = rng.choice(VALUES)
    return element


def random_elements(rng, max_objects=6, non_object_chance=0.3):
    """Build a random JSON array that mixes objects with non-object elements."""
    elements = []
    for _ in range(rng.randint(0, max_objects)):
        if rng.random() < non_object_chance:
            elements.append(rng.choice(NON_OBJECTS))
        else:
            elements.append(random_object(rng))
    return elements


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
        elements = random_elements(rng)
        got = common_keys_module.common_keys(elements)
        want = oracle_common_keys(elements)
        assert got == want, "common_keys(%r) = %r, oracle = %r" % (elements, got, want)


@case
def independent_oracle_matches_the_entry_point_on_random_arrays():
    rng = random.Random(0xC0FFEE)
    for _ in range(40):
        elements = random_elements(rng)
        got = answer(json.dumps(elements))
        want = oracle_output(elements)
        assert got == want, "CLI on %r = %r, oracle = %r" % (elements, got, want)


@case
def independent_oracle_covers_the_declared_worlds():
    """The all-shared, partially-shared and none worlds, through the oracle."""
    assert oracle_output([{"a": 1, "b": 2}, {"a": 3, "b": 4}]) == "a\nb\n"
    assert oracle_output([{"a": 1, "b": 2}, {"a": 3, "c": 4}]) == "a\n"
    assert oracle_output([{"x": 1}, {"y": 2}]) == "none\n"


@case
def independent_oracle_skips_non_object_elements():
    elements = [{"a": 1, "b": 2}, 7, None, {"a": 3, "c": 4}, "skip me"]
    assert oracle_common_keys(elements) == ["a"]
    assert answer(json.dumps(elements)) == "a\n"


@case
def independent_oracle_orders_by_code_point():
    elements = [{"b": 1, "A": 2, "a": 3, "B": 4, "1": 5, "_": 6}]
    want = oracle_common_keys(elements)
    assert want == ["1", "A", "B", "_", "a", "b"], want
    assert answer(json.dumps(elements)) == "".join(key + "\n" for key in want)


# --- the delivered mutation harness -------------------------------------------


@case
def req_006_the_declared_mutation_report_path_is_the_default():
    """REQ-006 AC1: plain ``bash mutation.sh`` writes the declared report path.

    The wrapper must not pass ``--report``, so the harness' default (the path
    the requirement document names) is what a bare invocation produces.
    """
    declared = os.path.join("reports", "mutation", "mutation.json")
    assert mutation_module.DEFAULT_REPORT == declared, mutation_module.DEFAULT_REPORT
    with open(MUTATION, encoding="utf-8") as handle:
        wrapper = handle.read()
    assert "--report" not in wrapper, (
        "bash mutation.sh must use the harness default so it writes the declared path"
    )


@case
def mutation_entry_point_exists_and_parses():
    assert os.path.isfile(MUTATION), "REQ-006: bash mutation.sh must exist at the root"
    result = subprocess.run(["bash", "-n", MUTATION], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, "mutation.sh must be valid shell: %s" % result.stderr
    with open(MUTATION, encoding="utf-8") as handle:
        source = handle.read()
    assert "common_keys_mutation.py" in source, "the entry point must run the harness"


@case
def mutation_harness_patterns_match_the_source():
    """Every mutant pattern must still match exactly once, or the gate is vacuous."""
    with open(os.path.join(ROOT, "common_keys.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert len(mutation_module.MUTANTS) > 0, "the harness must measure at least one mutant"
    for mutant_id, find, _replace, _description in mutation_module.MUTANTS:
        count = source.count(find)
        assert count == 1, "mutant %s matches %d times in common_keys.py" % (mutant_id, count)


def run_harness_with_fake_suite(directory, survivors):
    """Run the mutation harness' bookkeeping against a fake project and suite.

    The harness is the unit under test here, so its two process-level seams are
    replaced: ``copy_project`` returns a fresh directory holding a copy of the
    delivered common_keys.py, and ``run_suite`` reports whether the (fake)
    suite passed. The control copy is never mutated, so it must always pass;
    a mutant copy is one whose source differs from the delivered source. The
    returned list records, per suite run, whether that copy was a mutant.
    """
    with open(os.path.join(ROOT, "common_keys.py"), encoding="utf-8") as handle:
        original_source = handle.read()
    copies = []
    applied = []

    def fake_copy_project():
        path = os.path.join(directory, "project-%d" % len(copies))
        os.makedirs(path)
        shutil.copyfile(os.path.join(ROOT, "common_keys.py"), os.path.join(path, "common_keys.py"))
        copies.append(path)
        return path

    def fake_run_suite(path):
        with open(os.path.join(path, "common_keys.py"), encoding="utf-8") as handle:
            content = handle.read()
        is_mutant = content != original_source
        applied.append(is_mutant)
        if not is_mutant:
            return True  # the control run must pass on an unmutated copy
        return survivors

    original_copy = mutation_module.copy_project
    original_suite = mutation_module.run_suite
    mutation_module.copy_project = fake_copy_project
    mutation_module.run_suite = fake_run_suite
    try:
        status = mutation_module.run(os.path.join(directory, "mutation.json"))
    finally:
        mutation_module.copy_project = original_copy
        mutation_module.run_suite = original_suite
    return applied, status


@case
def mutation_harness_writes_a_real_survivors_json_report():
    """REQ-006: exercise the harness' bookkeeping without a nested full suite.

    Running the real harness inside the delivered suite would make every unit
    run spawn three full copies of the suite, which is slow and makes the test
    suite depend on itself recursively. Instead this case supplies a fake
    project and a fake suite verdict, so the harness' own control run, mutant
    application, kill counting and survivors-json rendering are all exercised
    directly. The real end-to-end mutation gate is the separately declared
    `bash mutation.sh`, which the host runs against this same suite.

    REQ-006 AC1: the report has exactly the total and survivors keys.
    REQ-006 AC2: it records at least one mutant.
    """
    original = mutation_module.MUTANTS
    mutation_module.MUTANTS = original[:3]
    try:
        with tempfile.TemporaryDirectory() as directory:
            report_path = os.path.join(directory, "mutation.json")
            applied, status = run_harness_with_fake_suite(directory, survivors=False)
            assert applied == [False, True, True, True], applied
            with open(report_path, encoding="utf-8") as handle:
                report = json.load(handle)
    finally:
        mutation_module.MUTANTS = original
    assert status == 0, "no mutant of the bounded subset may survive"
    assert set(report) == {"total", "survivors"}, report
    assert report["total"] == 3, "the harness must record every mutant it ran: %r" % report
    assert report["survivors"] == [], "the delivered tests must kill every mutant: %r" % report


@case
def mutation_harness_records_a_survivor_when_the_suite_passes():
    """A suite that fails to notice a defect must be reported, not hidden."""
    original = mutation_module.MUTANTS
    mutation_module.MUTANTS = original[:2]
    try:
        with tempfile.TemporaryDirectory() as directory:
            report_path = os.path.join(directory, "mutation.json")
            applied, status = run_harness_with_fake_suite(directory, survivors=True)
            with open(report_path, encoding="utf-8") as handle:
                report = json.load(handle)
    finally:
        mutation_module.MUTANTS = original
    assert applied == [False, True, True], applied
    assert status != 0, "a survivor must make the harness fail"
    assert report["total"] == 2, report
    assert len(report["survivors"]) == 2, report
    for survivor, (_, _, _, description) in zip(report["survivors"], original[:2]):
        assert set(survivor) == {"file", "line", "description"}, survivor
        assert survivor["file"] == "common_keys.py", survivor
        assert survivor["description"] == description, survivor
        assert survivor["line"] > 0, survivor


@case
def mutation_harness_fails_closed_when_a_pattern_does_not_match():
    """A rename must not silently turn the mutation gate into a no-op."""
    original = mutation_module.MUTANTS
    mutation_module.MUTANTS = [("m99-missing-pattern", "this text is not in the source", "x", "x")]
    try:
        with tempfile.TemporaryDirectory() as directory:
            report_path = os.path.join(directory, "mutation.json")
            try:
                run_harness_with_fake_suite(directory, survivors=False)
            except mutation_module.HarnessError:
                pass
            else:
                raise AssertionError("a mutant pattern that matches nothing must fail closed")
            assert not os.path.exists(report_path), "a failed measurement must not write a passing report"
    finally:
        mutation_module.MUTANTS = original


# --- the delivered pipeline ---------------------------------------------------


@case
def pipeline_runs_the_declared_commands():
    code = workflow_code()
    assert "bash run-tests.sh" in code, "the pipeline must run the delivered suite"
    assert "bash common-keys.sh" in code, "the pipeline must run the declared entry point"
    assert "reports/tests.tap" in code, "the pipeline must read the declared TAP report"
    assert "common-keys.sh {json}" not in code, "the placeholder must not survive"
    assert "pnpm test" not in code, "the pipeline must run the declared suite, not a guess"


@case
def pipeline_runs_the_declared_mutation_command():
    code = workflow_code()
    assert "bash mutation.sh" in code, "the pipeline must run the declared mutation command"
    assert "reports/mutation/mutation.json" in code, "the mutation report path must be named"


# --- the run-tests.sh gate ----------------------------------------------------


def stub_suite(directory, name, report_path, tap, status):
    """Write a tiny self-contained suite (TAP writer + exit status) instead of pytest."""
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
        ["bash", RUNNER], cwd=ROOT, capture_output=True, text=True, timeout=60, env=env
    )


@case
def req_005_the_root_has_a_discoverable_test_entry_point():
    """The run's smoke gate needs an invocable entry point it can find.

    REQ-005 declares run-tests.sh at the repository root; the project also
    exposes the same command as the package.json ``test`` script, so either
    discovery path runs the delivered suite and preserves its exit status.
    """
    assert os.path.isfile(RUNNER), "REQ-005: run-tests.sh must exist at the repository root"
    assert os.path.dirname(RUNNER) == ROOT, "the runner must sit at the repository root"
    with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    scripts = manifest.get("scripts", {})
    assert scripts.get("test") == "bash run-tests.sh", (
        "package.json must expose the delivered suite as its test script: %r" % scripts.get("test")
    )


@case
def req_005_the_runner_passes_a_green_suite_and_keeps_its_report():
    with tempfile.TemporaryDirectory() as directory:
        report = os.path.join(directory, "green.tap")
        tap = "TAP version 13\n1..1\nok 1 - green\n# tests 1\n# pass 1\n# fail 0\n"
        suite = stub_suite(directory, "green.py", report, tap, 0)
        result = run_runner(suite)
        assert result.returncode == 0, result.stderr
        with open(report, encoding="utf-8") as handle:
            assert handle.read() == tap


@case
def req_005_the_runner_fails_when_its_suite_fails():
    with tempfile.TemporaryDirectory() as directory:
        report = os.path.join(directory, "red.tap")
        tap = "TAP version 13\n1..1\nnot ok 1 - red\n# tests 1\n# pass 0\n# fail 1\n"
        suite = stub_suite(directory, "red.py", report, tap, 1)
        result = run_runner(suite)
        assert result.returncode != 0, "a failing suite must make the runner exit non-zero"
        with open(report, encoding="utf-8") as handle:
            assert "not ok 1" in handle.read()


@case
def req_005_the_runner_rejects_a_missing_suite_file():
    result = run_runner(os.path.join(ROOT, "no-such-suite.py"))
    assert result.returncode != 0, "a missing suite file must fail the runner"
    assert result.stderr.strip() != "", "the runner should explain the missing file"


@case
def req_005_the_tap_renderer_reports_the_pass_and_fail_totals():
    text = tap_report([("a", True, ""), ("b", False, "boom"), ("c", True, "")])
    assert text.startswith("TAP version 13\n1..3\n"), text
    assert "ok 1 - a\n" in text
    assert "not ok 2 - b\n" in text
    assert "ok 3 - c\n" in text
    assert "# tests 3\n" in text
    assert "# pass 2\n" in text
    assert "# fail 1\n" in text
    assert "# boom" in text


# --- TAP report ---------------------------------------------------------------


def tap_report(results):
    """Render the results as TAP: the plan first, then the cases, then a summary."""
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    lines = ["TAP version 13", "1..%d" % len(results)]
    for index, (name, ok, detail) in enumerate(results, start=1):
        lines.append("%s %d - %s" % ("ok" if ok else "not ok", index, name))
        for line in str(detail).splitlines():
            lines.append("# %s" % line)
    lines.append("# tests %d" % len(results))
    lines.append("# pass %d" % passed)
    lines.append("# fail %d" % failed)
    return "\n".join(lines) + "\n"


def write_report(text):
    """Write the TAP text to the declared path (REQ-005: reports/tests.tap)."""
    path = REPORT
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def main():
    results = []
    for function in CASES:
        try:
            function()
        except Exception as error:  # noqa: BLE001 - the report must name every failure
            results.append((function.__name__, False, "%s: %s" % (type(error).__name__, error)))
        else:
            results.append((function.__name__, True, ""))
    text = tap_report(results)
    write_report(text)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, detail in results:
        if not ok:
            sys.stderr.write("not ok - %s: %s\n" % (name, detail))
    sys.stderr.write("%d/%d cases passed (report: %s)\n" % (len(results) - failed, len(results), REPORT))
    # The TAP report is both written to the declared file and echoed to standard
    # output. A test consumer reads the runner's stdout for a known summary
    # shape; if the report lived only in a file, a green suite would look like
    # "no test summary found" and the run's smoke gate would fail closed on a
    # deliverable that actually passes. The whole report goes out LAST, after
    # every stderr diagnostic, so a bounded `tail` keeps the
    # `# tests` / `# pass` / `# fail` summary at the end of the stream.
    sys.stdout.write(text)
    sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
