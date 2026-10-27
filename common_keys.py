#!/usr/bin/env python3
"""Print the keys shared by every object in a JSON array (behind common-keys.sh).

The behaviour is exactly the one the confirmed requirement document declares
(docs/requirements/intake.yaml):

    REQ-001  the command-line entry point is common-keys.sh, one file argument
    REQ-002  the input is one JSON value: an array; its key names are the
             object elements' own top-level keys
    REQ-003  one common key per line, ascending Unicode code point order
    REQ-004  when no key is common, the single line `none`
    REQ-005  the delivered tests pin this behaviour and write reports/tests.tap
    REQ-006  the delivered `bash mutation.sh` writes the survivors-json report
    REQ-007  the choices recorded for AMB-001 .. AMB-003 are applied here

The decisions the requirement leaves open are settled in the document:

    AMB-001  none: the top-level array may be empty; no key is common to zero
             objects, so the answer is the single line `none` and exit 0
    AMB-002  skip: an array element that is not a JSON object is ignored, and
             the intersection is taken over the object elements that remain
    AMB-003  error: a missing or unreadable file, a file that is not valid
             JSON, or a top-level value that is not an array is a diagnostic on
             stderr and a non-zero exit with no result lines on stdout

Nothing here reads a second file, needs stdin, touches the network, or depends
on anything outside the Python 3 standard library.
"""

import json
import sys

# The exact usage diagnostic; the entry point carries the same text.
USAGE = "usage: bash common-keys.sh <json-file>\n"

# Prefix for diagnostics, matching the entry point's name.
PREFIX = "common-keys.sh"


class InputError(Exception):
    """The input is not a usable JSON array (AMB-003 error)."""


def reject_constant(name):
    """Reject the NaN/Infinity extensions Python's decoder accepts by default.

    RFC 8259 JSON has no NaN or Infinity literals, so a file that uses them is
    not valid JSON and therefore takes the AMB-003 stop-error path instead of
    being decoded into a float.
    """
    raise ValueError("%s is not a valid JSON value" % name)


def parse(text):
    """Return the top-level array ``text`` holds, else raise InputError.

    The whole file is one JSON value and that value must be an array (REQ-002).
    A file that does not parse, and a top-level value that is not an array, are
    the AMB-003 error. The ELEMENTS are deliberately not validated here: an
    element that is not an object is not an error under AMB-002, it is skipped
    by common_keys().
    """
    try:
        value = json.loads(text, parse_constant=reject_constant)
    except ValueError as error:
        # AMB-003 (error): a file that is not valid JSON is a stop-error.
        raise InputError("the input is not valid JSON: %s" % error)

    if not isinstance(value, list):
        # AMB-003 (error): a top-level value that is not an array is a stop-error.
        raise InputError("the top-level JSON value is not an array")

    return value


def common_keys(elements):
    """Return the keys present in every object element, ordered by code point.

    Only an object's own top-level keys count (REQ-002), so a nested object is
    just another value and its keys are never considered or flattened. An
    element that is not a JSON object is skipped (AMB-002), so the intersection
    runs over the object elements only; an array with no object element at all
    has no common key. Either way the result is empty when nothing is common
    (AMB-001, REQ-004), which the caller renders as ``none``.

    The result is sorted with Python's default string ordering, which is
    ascending Unicode code point order (REQ-003).
    """
    # AMB-002 (skip): a non-object element is ignored, never an error.
    objects = [element for element in elements if isinstance(element, dict)]
    # AMB-001 (none): zero objects means no common key, which renders as `none`.
    if not objects:
        return []

    shared = set(objects[0].keys())
    for element in objects[1:]:
        shared &= set(element.keys())
        if not shared:
            # Nothing can be added back: intersecting further stays empty.
            return []

    return sorted(shared)


def main(argv):
    """Run the declared entry point; ``argv`` is sys.argv (program name first)."""
    if len(argv) != 2:
        sys.stderr.write(USAGE)
        return 2

    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        # AMB-003 (error): a missing or unreadable file is a stop-error, not a crash.
        sys.stderr.write("%s: cannot read %s: %s\n" % (PREFIX, path, error))
        return 1
    except UnicodeDecodeError as error:
        # AMB-003 (error): a file that is not UTF-8 is unusable input, so it is a
        # stop-error rather than a traceback.
        sys.stderr.write("%s: %s: the input is not valid UTF-8: %s\n" % (PREFIX, path, error))
        return 1

    try:
        elements = parse(text)
        keys = common_keys(elements)
    except InputError as error:
        sys.stderr.write("%s: %s: %s\n" % (PREFIX, path, error))
        return 1

    if keys:
        # One key per line, nothing else: the bare key names.
        sys.stdout.write("".join(key + "\n" for key in keys))
    else:
        # AMB-001 (none): no key is common to every object, so print the word.
        sys.stdout.write("none\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
