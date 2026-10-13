#!/usr/bin/env python3
"""Print the keys shared by every object in a JSON array (behind common-keys.sh).

The behaviour is exactly the one the confirmed requirement document declares
(docs/requirements/intake.yaml):

    REQ-001  the command-line entry point is common-keys.sh, one file argument
    REQ-002  the input is one JSON value: an array whose elements are objects
    REQ-003  a key is reported only when it is present in EVERY object
    REQ-004  one common key per line, sorted in ascending alphabetical order
    REQ-005  when no key is common, the single line `none`
    REQ-006  the delivered tests pin this behaviour and write reports/tests.tap
    REQ-007  the choices recorded for AMB-001 .. AMB-004 are applied here

The decisions the requirement leaves open are settled in the document:

    AMB-001  top-level: only the keys directly on each object count, so a key
             nested inside a sub-object is never reported and never flattened
             into a dotted path
    AMB-002  stop-error: a file that is not valid JSON, or a value that is not
             an array of objects, is a diagnostic on stderr and a non-zero
             exit with no key list on stdout
    AMB-003  none: an array that holds no objects at all prints the single line
             `none` and exits zero
    AMB-004  codepoint: the keys are ordered by Unicode code point, so an
             uppercase letter precedes its lowercase counterpart

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
    """The file is not the declared JSON array of objects (AMB-002 stop-error)."""


def parse(text):
    """Return the array of objects ``text`` holds, else raise InputError.

    The whole file is one JSON value (REQ-002). It must be an array, and every
    element of that array must be an object; anything else is the stop-error
    AMB-002 records. An empty array is valid here and yields ``[]``: it holds
    no objects, which AMB-003 renders as ``none``.
    """
    try:
        value = json.loads(text)
    except ValueError as error:
        raise InputError("the input is not valid JSON: %s" % error)

    if not isinstance(value, list):
        raise InputError("the top-level JSON value is not an array")

    for index, element in enumerate(value):
        if not isinstance(element, dict):
            raise InputError("array element %d is not an object" % index)

    return value


def common_keys(objects):
    """Return the keys present in every object, ordered by code point.

    Only the objects' own top-level keys count (AMB-001), so a nested object is
    just another value and its keys are never considered. When the array holds
    no objects the result is empty and the caller prints ``none`` (AMB-003);
    when the objects share nothing the result is empty for the same reason.
    The result is sorted with Python's default string ordering, which is
    ascending Unicode code point order (AMB-004).
    """
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
        sys.stderr.write("%s: cannot read %s: %s\n" % (PREFIX, path, error))
        return 1

    try:
        objects = parse(text)
        keys = common_keys(objects)
    except InputError as error:
        sys.stderr.write("%s: %s: %s\n" % (PREFIX, path, error))
        return 1

    if keys:
        # One key per line, nothing else: the bare key names.
        sys.stdout.write("".join(key + "\n" for key in keys))
    else:
        # No key is common to every object: the single lowercase word.
        sys.stdout.write("none\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
