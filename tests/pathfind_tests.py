#!/usr/bin/env python3
"""Unit and integration tests for the delivered pathfind behaviour.

Every integration case drives the DELIVERED entry point through the process
boundary -- ``bash pathfind.sh <mapfile>`` -- on a hand-built map, and asserts
the answer the confirmed requirement document declares. The unit cases import
``pathfind.py`` directly and call ``parse()``, ``shortest()`` and ``main()``, so
the same contract is pinned without a subprocess per assertion (and the
S-equals-E edge, which the on-disk format cannot express, can be exercised).

The suite writes its TAP report to ``reports/tests.tap`` (the path the document
names) and exits 0 only when every case passes, so ``bash run-tests.sh`` is a
gate. The report ends with a ``# tests N``/``# pass N``/``# fail N`` summary so
a generic test-report reader can read it as TAP, and carries no ``not ok`` line
when the suite is green.

Coverage is explicit for every acceptance criterion and every open decision in
``docs/requirements/intake.yaml``:

* REQ-001 the entry point and its first argument
* REQ-002 the grid alphabet, rectangle and single S/E
* REQ-003 the shortest path length in steps, and the unreachable case
* REQ-004 the TAP report and the reachable + unreachable assertions
* REQ-005 the mutation tool the document declares
* AMB-001 orthogonal: only the four edge-adjacent moves are allowed
* AMB-002 edges: adjacent S and E print 1
* AMB-003 reject: a malformed map is a non-zero stop-error with a diagnostic
"""

import contextlib
import heapq
import importlib.util
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "pathfind.sh")
REPORT = os.path.join(ROOT, "reports", "tests.tap")

# The unit cases below import the implementation directly, so ROOT must be on
# the import path no matter how this module was loaded.
sys.path.insert(0, ROOT)
import pathfind  # noqa: E402 - imported after ROOT is on sys.path

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


def write_map(directory, content):
    """Write a fixture map (text or bytes) and return its path."""
    path = os.path.join(directory, "map.txt")
    if isinstance(content, bytes):
        with open(path, "wb") as handle:
            handle.write(content)
    else:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return path


def answer(content):
    """Return the single stdout line for a well-formed map."""
    with tempfile.TemporaryDirectory() as directory:
        result = run([write_map(directory, content)])
    assert result.returncode == 0, "a well-formed map must exit 0, got %d (%s)" % (
        result.returncode,
        result.stderr.strip(),
    )
    assert result.stdout.endswith("\n"), "the answer line must end with a newline"
    assert result.stdout.count("\n") == 1, "the answer must be exactly one line"
    return result.stdout[:-1]


def expect_answer(content, wanted, why):
    got = answer(content)
    assert got == wanted, "%s: expected %r, got %r" % (why, wanted, got)


def expect_malformed(content, why):
    """A malformed map is a stop-error: non-zero exit, stderr, empty stdout."""
    with tempfile.TemporaryDirectory() as directory:
        result = run([write_map(directory, content)])
    assert result.returncode != 0, "%s: expected a non-zero exit, got 0" % why
    assert result.stderr.strip() != "", "%s: expected a diagnostic on stderr" % why
    assert result.stdout == "", "%s: expected an empty stdout, got %r" % (why, result.stdout)


def reference_distance(rows, start, end):
    """An independent BFS oracle for the shortest orthogonal move count.

    This is deliberately written against the same contract but with a different
    shape than the implementation (a distance table and a plain list used as a
    queue, versus the implementation's ``deque`` and early return), so a shared
    mistake is less likely to cancel out. It only ever visits the four
    edge-adjacent neighbours, each one move (AMB-001), and it counts moves and
    not cells (AMB-002); it returns ``None`` when no route exists.
    """
    if start == end:
        return 0
    height = len(rows)
    width = len(rows[0])
    distances = {start: 0}
    frontier = [start]
    while frontier:
        node = frontier.pop(0)
        row, column = node
        for next_row, next_column in (
            (row - 1, column),
            (row + 1, column),
            (row, column - 1),
            (row, column + 1),
        ):
            if not (0 <= next_row < height and 0 <= next_column < width):
                continue
            neighbour = (next_row, next_column)
            if neighbour in distances:
                continue
            if rows[next_row][next_column] == "#":
                continue
            distances[neighbour] = distances[node] + 1
            if neighbour == end:
                return distances[neighbour]
            frontier.append(neighbour)
    return None


def random_grid(rng, max_height=6, max_width=6):
    """A seeded random ``#``/``.`` grid plus a start and an end cell.

    The two chosen cells are always forced passable, so the oracle and the
    implementation see the same walkable grid. Occasionally the same cell is
    returned, which lets the differential cover the zero-move edge that the
    on-disk S/E format cannot express. The endpoints are chosen before the walls
    so the function always terminates, even on a 1x1 grid.
    """
    height = rng.randint(1, max_height)
    width = rng.randint(1, max_width)
    cells = [(row, column) for row in range(height) for column in range(width)]
    if len(cells) < 2 or rng.random() < 0.1:
        start = end = rng.choice(cells)
    else:
        start, end = rng.sample(cells, 2)
    rows = [
        "".join("#" if rng.random() < 0.35 else "." for _ in range(width))
        for _ in range(height)
    ]
    for row, column in {start, end}:
        line = list(rows[row])
        line[column] = "."
        rows[row] = "".join(line)
    return rows, start, end


# --- REQ-001: the entry point and its first argument ---------------------------


@case
def req_001_a_well_formed_map_exits_zero():
    with tempfile.TemporaryDirectory() as directory:
        result = run([write_map(directory, "S.E\n")])
    assert result.returncode == 0, "a well-formed map must exit 0"


@case
def req_001_the_map_is_read_from_the_first_argument():
    with tempfile.TemporaryDirectory() as directory:
        path = write_map(directory, "S..E\n")
        result = run([path])
    assert result.returncode == 0, result.stderr
    assert result.stdout == "3\n", "the grid must come from $1, got %r" % result.stdout


@case
def req_001_no_argument_is_a_non_zero_error_with_a_diagnostic():
    result = run([])
    assert result.returncode != 0, "no argument must exit non-zero"
    assert result.stderr.strip() != "", "no argument must write a diagnostic on stderr"
    assert result.stdout == "", "no argument must write nothing on stdout"


@case
def req_001_an_unreadable_path_is_a_non_zero_error_with_a_diagnostic():
    result = run([os.path.join(tempfile.gettempdir(), "no-such-takumi-map.txt")])
    assert result.returncode != 0, "an unreadable path must exit non-zero"
    assert result.stderr.strip() != "", "an unreadable path must write a diagnostic on stderr"
    assert result.stdout == "", "an unreadable path must write nothing on stdout"


@case
def req_001_stdout_is_exactly_one_bare_answer_token():
    """The success line is a bare integer or the word 'unreachable', nothing else."""
    allowed = re.compile(r"\A(0|[1-9][0-9]*|unreachable)\n\Z")
    maps = [
        "SE\n",
        "S.E\n",
        "S#E\n",
        "S....\n.....\n.....\n.....\n....E\n",
        "S.#\n..#\n#.E\n",
    ]
    for text in maps:
        with tempfile.TemporaryDirectory() as directory:
            result = run([write_map(directory, text)])
        assert result.returncode == 0, "%r must be accepted (%s)" % (text, result.stderr)
        assert allowed.match(result.stdout), (
            "the answer must be one bare integer or the lowercase word 'unreachable': %r"
            % result.stdout
        )
        assert result.stdout.count("\n") == 1, "the answer must be exactly one line"


# --- REQ-002: the grid alphabet, rectangle and single S/E ----------------------


@case
def req_002_the_declared_alphabet_parses_without_error():
    expect_answer("S.#\n.E.\n", "2", "a map over # . S E must parse")


@case
def req_002_wall_cells_are_never_entered():
    expect_answer("S#E\n", "unreachable", "a step must never enter a wall")


@case
def req_002_an_unequal_row_length_is_a_stop_error():
    expect_malformed("S.\n.E.\n", "the grid must be a rectangle")


@case
def req_002_a_character_outside_the_alphabet_is_a_stop_error():
    expect_malformed("SX\n.E\n", "only # . S E are map characters")


@case
def req_002_a_missing_start_is_a_stop_error():
    expect_malformed("..\n.E\n", "the map must hold one S")


@case
def req_002_a_repeated_start_is_a_stop_error():
    expect_malformed("SS\n.E\n", "the map must hold exactly one S")


@case
def req_002_a_missing_exit_is_a_stop_error():
    expect_malformed("S.\n..\n", "the map must hold one E")


@case
def req_002_a_repeated_exit_is_a_stop_error():
    expect_malformed("S.\nEE\n", "the map must hold exactly one E")


@case
def req_002_leading_and_trailing_whitespace_do_not_change_the_grid():
    expect_answer("  S.E  \n", "2", "surrounding whitespace must be normalised")


@case
def req_002_blank_lines_do_not_change_the_grid():
    expect_answer("\nS.E\n\n", "2", "blank lines must be skipped")


@case
def req_002_carriage_returns_do_not_change_the_grid():
    expect_answer("S.E\r\n", "2", "CRLF line endings must be normalised")


# --- REQ-003: the shortest path length in steps --------------------------------


@case
def req_003_a_reachable_exit_reports_the_minimum_moves():
    expect_answer("S....\n.....\n.....\n.....\n....E\n", "8", "a clear 5x5 grid is eight moves")


@case
def req_003_a_longer_alternative_route_does_not_change_the_answer():
    expect_answer("S..\n..#\n..E\n", "4", "every shortest route is four moves")


@case
def req_003_a_detour_is_counted_correctly():
    expect_answer("S.#\n..#\n#.E\n", "4", "the only route to E is four moves long")


@case
def req_003_a_longer_detour_is_counted_correctly():
    expect_answer(
        "S....\n###.#\n#...#\n#.###\n#..E.\n",
        "11",
        "the only route snakes eleven moves to E",
    )


@case
def req_003_a_walled_off_exit_is_unreachable():
    expect_answer("S#\n##\n#E\n", "unreachable", "walls fully separate S from E")


@case
def req_003_a_walled_off_exit_still_exits_zero():
    with tempfile.TemporaryDirectory() as directory:
        result = run([write_map(directory, "S#\n##\n#E\n")])
    assert result.returncode == 0, "unreachable is not an error"
    assert result.stdout == "unreachable\n", "unreachable must be the whole line"


# --- REQ-003: differential coverage against an independent oracle -------------


@case
def req_003_random_grids_match_an_independent_reference():
    """Unit differential: parse-free grids through the in-process search."""
    rng = random.Random(20261013)
    for _ in range(400):
        rows, start, end = random_grid(rng)
        expected = reference_distance(rows, start, end)
        got = pathfind.shortest(rows, start, end)
        assert got == expected, (
            "grid %r start %r end %r: implementation %r, reference %r"
            % (rows, start, end, got, expected)
        )


@case
def req_003_random_maps_match_the_reference_through_the_cli():
    """Integration differential: the delivered entry point against the oracle."""
    rng = random.Random(424242)
    checked = 0
    attempts = 0
    while checked < 25 and attempts < 400:
        attempts += 1
        rows, start, end = random_grid(rng)
        if start == end:
            continue
        grid = [list(row) for row in rows]
        grid[start[0]][start[1]] = "S"
        grid[end[0]][end[1]] = "E"
        text = "\n".join("".join(row) for row in grid) + "\n"
        expected = reference_distance(rows, start, end)
        wanted = "unreachable" if expected is None else str(expected)
        got = answer(text)
        assert got == wanted, "map %r: CLI %r, reference %r" % (text, got, wanted)
        checked += 1
    assert checked == 25, "the differential produced only %d maps" % checked


@case
def req_003_the_reference_agrees_the_zero_move_edge_is_zero():
    assert reference_distance(["."], (0, 0), (0, 0)) == 0
    assert pathfind.shortest(["."], (0, 0), (0, 0)) == 0


@case
def req_003_the_renderer_prints_a_zero_length_path_as_plain_zero():
    """A zero-move answer is still a bare decimal integer, not 'unreachable'.

    The on-disk format cannot spell a start that is also the exit, so the parse
    boundary is substituted to drive ``main()``'s renderer over the zero case.
    """
    import unittest.mock as mock

    with tempfile.TemporaryDirectory() as directory:
        path = write_map(directory, "S\n")
        with mock.patch.object(pathfind, "parse", return_value=(["S"], (0, 0), (0, 0))):
            code, out, err = captured_main([path])
    assert code == 0, err
    assert out == "0\n", "the zero answer must be the bare digit 0, got %r" % out
    assert err == "", err


# --- REQ-004: the delivered TAP report ----------------------------------------


@case
def req_004_the_report_path_is_the_declared_tap_report():
    assert REPORT == os.path.join(ROOT, "reports", "tests.tap"), REPORT


@case
def req_004_the_runner_invokes_this_suite():
    with open(os.path.join(ROOT, "run-tests.sh"), encoding="utf-8") as handle:
        source = handle.read()
    assert "pathfind_tests.py" in source, "run-tests.sh must run this suite"


@case
def req_004_the_suite_asserts_a_reachable_and_an_unreachable_case():
    names = " ".join(function.__name__ for function in CASES).lower()
    assert "reachable" in names or "detour" in names, "the suite must assert a reachable map"
    assert "unreachable" in names, "the suite must assert the unreachable case"


# --- REQ-004: the TAP renderer that produces reports/tests.tap ----------------


@case
def req_004_the_tap_renderer_marks_pass_and_fail_with_totals():
    report = tap_report(
        [
            ("a_passing_case", True, ""),
            ("a_failing_case", False, "boom"),
        ]
    )
    assert report.startswith("TAP version 13\n"), report
    assert "ok 1 - a_passing_case" in report, report
    assert "not ok 2 - a_failing_case" in report, report
    assert "# tests 2" in report, report
    assert "# pass 1" in report, report
    assert "# fail 1" in report, report


@case
def req_004_the_tap_renderer_has_no_failing_line_for_a_green_run():
    report = tap_report([("green", True, "")])
    assert "not ok" not in report, report
    assert "# tests 1" in report, report
    assert "# pass 1" in report, report
    assert "# fail 0" in report, report


# --- REQ-005: the mutation tool the document declares -------------------------


@case
def req_005_the_declared_mutation_entry_point_exists():
    assert os.path.exists(os.path.join(ROOT, "node_modules", ".bin", "stryker")), (
        "npx stryker must resolve to a committed local bin"
    )
    assert os.path.exists(os.path.join(ROOT, "mutation", "stryker-cli.mjs")), (
        "the stryker CLI that runs the mutation harness must exist"
    )
    assert os.path.exists(os.path.join(ROOT, "mutation", "pathfind_mutation.py")), (
        "the mutation harness must exist"
    )


def load_mutation_harness():
    """Import mutation/pathfind_mutation.py so its copy policy can be checked."""
    path = os.path.join(ROOT, "mutation", "pathfind_mutation.py")
    spec = importlib.util.spec_from_file_location("pathfind_mutation_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@case
def req_005_the_mutation_copy_keeps_the_delivered_suite_runnable():
    """The mutant copy must not fail the suite for an unrelated reason.

    The delivered suite asserts that the declared mutation entry point exists,
    so a mutation copy that dropped ``node_modules`` would fail every mutant
    before the defect could be observed: every mutant would look killed and the
    gate would be vacuous. This pins the copy policy the harness uses.
    """
    harness = load_mutation_harness()
    with tempfile.TemporaryDirectory() as directory:
        copy = os.path.join(directory, "copy")
        shutil.copytree(ROOT, copy, dirs_exist_ok=True, ignore=harness.IGNORED)
        for relative in (
            "pathfind.sh",
            "pathfind.py",
            "run-tests.sh",
            os.path.join("tests", "pathfind_tests.py"),
            os.path.join("node_modules", ".bin", "stryker"),
            os.path.join("mutation", "pathfind_mutation.py"),
        ):
            assert os.path.exists(os.path.join(copy, relative)), (
                "the mutation copy must keep %s" % relative
            )


@case
def req_005_the_mutation_gate_is_not_vacuous():
    """A pristine copy passes and a real mutant is actually killed.

    The control half catches a harness whose copies fail the suite for an
    unrelated reason (which would report every mutant as killed); the mutant
    half catches a suite that can no longer detect a defect at all. The harness
    marks its own child runs with PATHFIND_MUTATION_COPY so this case stands
    down inside them instead of recursing.
    """
    if os.environ.get("PATHFIND_MUTATION_COPY") == "1":
        return
    harness = load_mutation_harness()
    with tempfile.TemporaryDirectory() as directory:
        control = os.path.join(directory, "control")
        shutil.copytree(ROOT, control, dirs_exist_ok=True, ignore=harness.IGNORED)
        assert harness.run_suite(control), (
            "the delivered suite must pass on an unmutated copy"
        )

        mutant_id, find, replace, _description = harness.MUTANTS[0]
        mutant = os.path.join(directory, "mutant")
        shutil.copytree(ROOT, mutant, dirs_exist_ok=True, ignore=harness.IGNORED)
        target = os.path.join(mutant, harness.TARGET)
        with open(target, encoding="utf-8") as handle:
            source = handle.read()
        assert find in source, "mutant %s no longer matches the source" % mutant_id
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(source.replace(find, replace, 1))
        assert not harness.run_suite(mutant), (
            "mutant %s must be killed by the delivered suite" % mutant_id
        )


# --- AMB-001: orthogonal adjacency --------------------------------------------


@case
def amb_001_a_two_by_two_diagonal_costs_two_orthogonal_moves():
    expect_answer("S.\n.E\n", "2", "a diagonal target is two orthogonal moves away")


@case
def amb_001_a_diagonal_only_link_is_unreachable():
    expect_answer("S#\n#E\n", "unreachable", "a diagonal step is not a move")


@case
def amb_001_a_diagonal_shortcut_around_a_wall_is_not_used():
    expect_answer("S..\n.#.\n..E\n", "4", "the centre wall forces the four-move route")


@case
def amb_001_unit_adjacency_is_orthogonal():
    assert sorted(pathfind.NEIGHBOURS) == sorted([(-1, 0), (1, 0), (0, -1), (0, 1)])
    assert all(abs(row) + abs(column) == 1 for row, column in pathfind.NEIGHBOURS)


# --- AMB-002: the number is moves, not cells ----------------------------------


@case
def amb_002_an_orthogonally_adjacent_exit_is_one_move():
    expect_answer("SE\n", "1", "adjacent S and E print 1")


@case
def amb_002_a_three_cell_row_is_two_moves_not_three_cells():
    expect_answer("S.E\n", "2", "S.E is two moves, not three cells")


@case
def amb_002_a_five_cell_corridor_is_four_moves():
    expect_answer("S...E\n", "4", "a five-cell corridor is four moves")


# --- AMB-003: a malformed map is a reject stop-error --------------------------


@case
def amb_003_a_malformed_map_exits_non_zero_and_writes_stderr():
    expect_malformed("S.\n.E.\n", "a malformed map must stop with a diagnostic")


@case
def amb_003_a_malformed_map_writes_nothing_on_stdout():
    expect_malformed("SX\n.E\n", "a malformed map must not print an answer")


@case
def amb_003_unit_parse_rejects_every_malformed_shape():
    parse_error("S.\n.E.\n", "unequal rows")
    parse_error("SX\n.E\n", "a character outside the alphabet")
    parse_error("..\n.E\n", "a missing S")
    parse_error("SS\n.E\n", "two S")
    parse_error("S.\n..\n", "a missing E")
    parse_error("S.\nEE\n", "two E")
    parse_error("", "an empty map")
    parse_error("\n\n", "a blank-only map")


# --- Independent verification added by the unit-and-integration test step -----
#
# Every case below is a SECOND, independent check of one acceptance criterion
# and of the option chosen for each AMB-nnn entry. The oracle is deliberately
# not the one the implementation uses: Dijkstra over a heap-ordered frontier and
# a distance table, where the implementation is a breadth-first deque with an
# early return. No code is shared with pathfind.py.


def dijkstra_distance(rows, start, end):
    """Shortest orthogonal move count via Dijkstra over unit-cost edges.

    Returns ``None`` when no route exists and 0 when start is end. Only the four
    edge-adjacent neighbours are generated (AMB-001) and every edge costs one
    move (AMB-002), so this is an independent statement of the same contract.
    """
    if start == end:
        return 0
    height = len(rows)
    width = len(rows[0])
    distances = {start: 0}
    frontier = [(0, start)]
    while frontier:
        distance, node = heapq.heappop(frontier)
        if distance != distances.get(node):
            continue
        if node == end:
            return distance
        row, column = node
        for next_row, next_column in (
            (row - 1, column),
            (row + 1, column),
            (row, column - 1),
            (row, column + 1),
        ):
            if not (0 <= next_row < height and 0 <= next_column < width):
                continue
            if rows[next_row][next_column] == "#":
                continue
            candidate = distance + 1
            if candidate < distances.get((next_row, next_column), candidate + 1):
                distances[(next_row, next_column)] = candidate
                heapq.heappush(frontier, (candidate, (next_row, next_column)))
    return None


def oracle_answer(rows, start, end):
    distance = dijkstra_distance(rows, start, end)
    return "unreachable" if distance is None else str(distance)


def render_fixture(rows, start, end):
    """Turn an oracle grid into an on-disk map with exactly one S and one E."""
    grid = [list(row) for row in rows]
    grid[start[0]][start[1]] = "S"
    grid[end[0]][end[1]] = "E"
    return "\n".join("".join(row) for row in grid) + "\n"


@case
def extra_req_002_the_start_and_exit_cells_are_walkable():
    """S must be leaveable and E enterable: both are ordinary free cells."""
    expect_answer("SE\n", "1", "E to the right is a walkable target")
    expect_answer("S\nE\n", "1", "S reaches E below")
    expect_answer("E\nS\n", "1", "S reaches E above")
    expect_answer("ES\n", "1", "S reaches E to the left")


@case
def extra_req_002_internal_whitespace_is_a_stop_error():
    expect_malformed("S E\n", "an embedded space is not a map character")
    expect_malformed("S\tE\n", "an embedded tab is not a map character")


@case
def extra_req_002_blank_only_and_empty_maps_are_stop_errors():
    expect_malformed("", "an empty file has no grid")
    expect_malformed("\n\n\n", "a blank-only file has no grid")


@case
def extra_req_002_invalid_utf8_bytes_are_rejected():
    """The reader decodes with errors=replace, so a stray byte becomes U+FFFD.

    U+FFFD is not one of # . S E, so the map is rejected rather than misread.
    """
    with tempfile.TemporaryDirectory() as directory:
        result = run([write_map(directory, b"S\xffE\n")])
    assert result.returncode != 0, "a byte outside the alphabet must be rejected"
    assert result.stderr.strip() != "", "the rejection must carry a diagnostic"
    assert result.stdout == "", "the rejection must print nothing on stdout"


@case
def extra_req_003_a_large_open_grid_prints_the_manhattan_distance():
    size = 20
    grid = [["." for _ in range(size)] for _ in range(size)]
    grid[0][0] = "S"
    grid[size - 1][size - 1] = "E"
    text = "\n".join("".join(row) for row in grid) + "\n"
    expect_answer(text, str(2 * (size - 1)), "an open 20x20 grid is 38 moves")


@case
def extra_req_003_an_exit_sealed_by_walls_is_unreachable():
    text = "S....\n.###.\n.#E#.\n.###.\n.....\n"
    expect_answer(text, "unreachable", "an exit sealed by walls has no route")


@case
def extra_req_003_dijkstra_oracle_agrees_on_detour_mazes():
    fixtures = [
        (["S.#", "..#", "#.E"], "4"),
        (["S....", "###.#", "#...#", "#.###", "#..E."], "11"),
    ]
    for rows, wanted in fixtures:
        rendered = "\n".join(rows) + "\n"
        got = answer(rendered)
        assert got == wanted, "map %r: expected %s, got %s" % (rendered, wanted, got)
        start = next(
            (r, c) for r, line in enumerate(rows) for c, cell in enumerate(line) if cell == "S"
        )
        end = next(
            (r, c) for r, line in enumerate(rows) for c, cell in enumerate(line) if cell == "E"
        )
        assert dijkstra_distance(rows, start, end) == int(wanted), (
            "the Dijkstra oracle disagrees on %r" % rendered
        )


@case
def extra_req_003_random_maps_match_dijkstra_through_the_entry_point():
    rng = random.Random(90210)
    checked = 0
    attempts = 0
    while checked < 30 and attempts < 600:
        attempts += 1
        rows, start, end = random_grid(rng, max_height=7, max_width=7)
        if start == end:
            continue
        rendered = render_fixture(rows, start, end)
        got = answer(rendered)
        wanted = oracle_answer(rows, start, end)
        assert got == wanted, "map %r: CLI %s, Dijkstra %s" % (rendered, got, wanted)
        checked += 1
    assert checked == 30, "the differential produced only %d maps" % checked


@case
def extra_req_003_the_two_independent_oracles_agree():
    rng = random.Random(112233)
    for _ in range(300):
        rows, start, end = random_grid(rng)
        assert dijkstra_distance(rows, start, end) == reference_distance(rows, start, end), (
            "the two independent oracles disagree on %r %r %r" % (rows, start, end)
        )


@case
def extra_amb_001_an_open_grid_never_takes_a_diagonal_shortcut():
    # A 4x4 open grid: orthogonal is 3+3=6 moves; a diagonal mover would take 3.
    expect_answer("S...\n....\n....\n...E\n", "6", "a diagonal shortcut is not a move")


@case
def extra_amb_002_every_adjacent_direction_costs_exactly_one_move():
    expect_answer("SE\n", "1", "E to the right is one move")
    expect_answer("ES\n", "1", "E to the left is one move")
    expect_answer("S\nE\n", "1", "E below is one move")
    expect_answer("E\nS\n", "1", "E above is one move")


@case
def extra_req_004_the_runner_propagates_a_failing_suite():
    """run-tests.sh must exit non-zero when the suite it runs fails."""
    with tempfile.TemporaryDirectory() as directory:
        failing = os.path.join(directory, "failing_suite.py")
        with open(failing, "w", encoding="utf-8") as handle:
            handle.write("import sys\nprint('not ok 1 - deliberately failing')\nsys.exit(1)\n")
        environment = dict(os.environ)
        environment["PATHFIND_TEST_FILE"] = failing
        result = subprocess.run(
            ["bash", os.path.join(ROOT, "run-tests.sh")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
    assert result.returncode != 0, "run-tests.sh must exit non-zero when a case fails"


@case
def extra_req_005_the_declared_mutation_command_reports_zero_survivors():
    """Run exactly the declared command and read the declared report shape.

    The outer mutation harness runs this very suite against each mutant with
    ``PATHFIND_MUTATION_COPY=1``; stand down there so the command does not
    recurse into a second mutation run.
    """
    if os.environ.get("PATHFIND_MUTATION_COPY") == "1":
        return
    report_path = os.path.join(ROOT, "reports", "mutation", "mutation.json")
    result = subprocess.run(
        ["npx", "stryker", "run", "--reporters", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        "the declared mutation command must exit 0 with no survivor: %s" % result.stderr[-2000:]
    )
    assert os.path.exists(report_path), "the declared report path %s must exist" % report_path
    with open(report_path, encoding="utf-8") as handle:
        report = json.load(handle)
    assert isinstance(report, dict), report
    assert "total" in report and "survivors" in report, report
    assert isinstance(report["total"], int) and report["total"] > 0, report
    assert isinstance(report["survivors"], list), report
    assert report["survivors"] == [], (
        "every mutant must be killed, got %r" % (report["survivors"],)
    )


# --- REQ-001: bounded, non-interactive invocation -----------------------------


@case
def req_001_a_small_map_finishes_well_within_a_couple_of_seconds():
    with tempfile.TemporaryDirectory() as directory:
        path = write_map(directory, "S....\n.....\n.....\n.....\n....E\n")
        started = time.monotonic()
        result = run([path])
        elapsed = time.monotonic() - started
    assert result.returncode == 0, result.stderr
    assert elapsed < 5.0, "a small map must finish quickly, took %.2fs" % elapsed


@case
def req_001_the_command_terminates_without_waiting_for_input():
    with tempfile.TemporaryDirectory() as directory:
        path = write_map(directory, "SE\n")
        result = run([path], stdin=subprocess.DEVNULL)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n", result.stdout


# --- Unit tests: the implementation's own functions ---------------------------


def parse_error(text, why):
    """Assert that parse() raises the AMB-003 reject error with a diagnostic."""
    try:
        pathfind.parse(text)
    except pathfind.MapError as error:
        assert str(error).strip() != "", "%s: the error must carry a diagnostic" % why
        return
    raise AssertionError("%s: expected MapError" % why)


def captured_main(args):
    """Call main() in-process and return (exit code, stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = pathfind.main(["pathfind.py"] + list(args))
    return code, out.getvalue(), err.getvalue()


@case
def unit_parse_returns_the_rows_start_and_exit():
    rows, start, end = pathfind.parse("S.E\n")
    assert rows == ["S.E"], rows
    assert start == (0, 0), start
    assert end == (0, 2), end


@case
def unit_parse_normalises_whitespace_carriage_returns_and_blank_lines():
    rows, start, end = pathfind.parse("  S.E  \r\n\r\n\n")
    assert rows == ["S.E"], rows
    assert start == (0, 0), start
    assert end == (0, 2), end


@case
def unit_shortest_is_zero_when_start_equals_exit():
    assert pathfind.shortest(["."], (0, 0), (0, 0)) == 0


@case
def unit_shortest_counts_one_for_an_adjacent_exit():
    assert pathfind.shortest(["SE"], (0, 0), (0, 1)) == 1


@case
def unit_shortest_counts_a_corridor_in_moves():
    assert pathfind.shortest(["S...E"], (0, 0), (0, 4)) == 4


@case
def unit_shortest_follows_a_detour():
    rows = ["S.#", "..#", "#.E"]
    assert pathfind.shortest(rows, (0, 0), (2, 2)) == 4


@case
def unit_shortest_returns_none_when_unreachable():
    assert pathfind.shortest(["S#E"], (0, 0), (0, 2)) is None


@case
def unit_shortest_uses_orthogonal_adjacency():
    assert pathfind.shortest(["S.", ".E"], (0, 0), (1, 1)) == 2
    assert pathfind.shortest(["S#", "#E"], (0, 0), (1, 1)) is None


@case
def unit_shortest_never_steps_through_a_wall():
    rows = ["S.#", "##.", "..E"]
    assert pathfind.shortest(rows, (0, 0), (2, 2)) is None


@case
def unit_main_reports_a_reachable_distance():
    with tempfile.TemporaryDirectory() as directory:
        code, out, err = captured_main([write_map(directory, "S..E\n")])
    assert code == 0, "a well-formed map must exit 0"
    assert out == "3\n", out
    assert err == "", err


@case
def unit_main_reports_unreachable():
    with tempfile.TemporaryDirectory() as directory:
        code, out, err = captured_main([write_map(directory, "S#E\n")])
    assert code == 0, "unreachable is not an error"
    assert out == "unreachable\n", out


@case
def unit_main_stops_on_a_malformed_map():
    with tempfile.TemporaryDirectory() as directory:
        code, out, err = captured_main([write_map(directory, "S.\n.E.\n")])
    assert code != 0, "a malformed map must exit non-zero"
    assert out == "", out
    assert err.strip() != "", "a malformed map must write a diagnostic on stderr"


@case
def unit_main_requires_an_argument():
    code, out, err = captured_main([])
    assert code != 0, "no argument must exit non-zero"
    assert out == "", out
    assert err.strip() != "", "no argument must write a diagnostic on stderr"


@case
def unit_main_reports_an_unreadable_path():
    missing = os.path.join(tempfile.gettempdir(), "no-such-unit-pathfind-map.txt")
    code, out, err = captured_main([missing])
    assert code != 0, "an unreadable path must exit non-zero"
    assert out == "", out
    assert err.strip() != "", "an unreadable path must write a diagnostic on stderr"


# --- Independent coverage added by this run's unit-and-integration step -------
#
# A THIRD, self-contained check of every acceptance criterion in
# docs/requirements/intake.yaml and of the option chosen for every AMB-nnn
# entry. The oracle below is neither the implementation's BFS nor the Dijkstra
# oracle above: it builds the grid graph and solves all-pairs shortest paths
# with the Floyd-Warshall dynamic program. Every integration case still drives
# the delivered entry point exactly as the document declares it
# (``bash pathfind.sh <mapfile>``) and every unit case calls the
# implementation's own functions.

ONE_LINE = re.compile(r"\A(0|[1-9][0-9]*|unreachable)\n\Z")


def floyd_warshall_distance(rows, start, end):
    """Shortest orthogonal move count via Floyd-Warshall.

    An independent oracle: it relaxes every intermediate vertex over a dense
    distance matrix, where the implementation is a breadth-first deque and the
    oracle above is a heap-ordered Dijkstra. Walls are absent from the vertex
    set, only the four edge-adjacent pairs get an edge (AMB-001) and every edge
    costs one move (AMB-002). Returns ``None`` when no route exists and 0 when
    the start is the end.
    """
    cells = [
        (row, column)
        for row, line in enumerate(rows)
        for column, cell in enumerate(line)
        if cell != "#"
    ]
    index = {cell: position for position, cell in enumerate(cells)}
    if start not in index or end not in index:
        return None
    size = len(cells)
    infinity = float("inf")
    distance = [[infinity] * size for _ in range(size)]
    for position in range(size):
        distance[position][position] = 0
    for cell, position in index.items():
        row, column = cell
        for neighbour in (
            (row - 1, column),
            (row + 1, column),
            (row, column - 1),
            (row, column + 1),
        ):
            if neighbour in index:
                distance[position][index[neighbour]] = 1
    for through in range(size):
        through_row = distance[through]
        for source in range(size):
            base = distance[source][through]
            if base == infinity:
                continue
            source_row = distance[source]
            for destination in range(size):
                candidate = base + through_row[destination]
                if candidate < source_row[destination]:
                    source_row[destination] = candidate
    result = distance[index[start]][index[end]]
    return None if result == infinity else result


# --- REQ-001: the command-line entry point ------------------------------------


@case
def new_req_001_every_accepted_map_prints_one_legal_answer_line():
    maps = [
        "SE\n",
        "S.E\n",
        "S#E\n",
        "S....\n.....\n.....\n.....\n....E\n",
        "S.#\n..#\n#.E\n",
    ]
    for text in maps:
        with tempfile.TemporaryDirectory() as directory:
            result = run([write_map(directory, text)])
        assert result.returncode == 0, "%r must exit 0 (%s)" % (text, result.stderr)
        assert ONE_LINE.match(result.stdout), (
            "%r must print one bare integer or 'unreachable', got %r" % (text, result.stdout)
        )
        assert result.stdout.count("\n") == 1, "%r must print exactly one line" % text


@case
def new_req_001_every_rejection_is_non_zero_with_stderr_and_no_stdout():
    malformed = [
        "S.\n.E.\n",
        "SX\n.E\n",
        "..\n.E\n",
        "SS\n.E\n",
        "S.\n..\n",
        "S.\nEE\n",
        "",
        "\n\n",
    ]
    for text in malformed:
        with tempfile.TemporaryDirectory() as directory:
            result = run([write_map(directory, text)])
        assert result.returncode != 0, "%r must be rejected" % text
        assert result.stderr.strip() != "", "%r must write a diagnostic" % text
        assert result.stdout == "", "%r must print nothing, got %r" % (text, result.stdout)

    missing = run([])
    assert missing.returncode != 0 and missing.stderr.strip() != "", "no argument is a stop-error"
    assert missing.stdout == "", missing.stdout

    absent = run([os.path.join(tempfile.gettempdir(), "no-such-new-run-pathfind.txt")])
    assert absent.returncode != 0 and absent.stderr.strip() != "", "an unreadable map is a stop-error"
    assert absent.stdout == "", absent.stdout


# --- REQ-002: the grid-map format ---------------------------------------------


@case
def new_req_002_start_and_exit_are_ordinary_walkable_cells():
    rows, start, end = pathfind.parse("SE\n")
    assert rows[start[0]][start[1]] == "S"
    assert rows[end[0]][end[1]] == "E"
    assert pathfind.shortest(rows, start, end) == 1
    expect_answer("S\nE\n", "1", "E below S is one step")
    expect_answer("S.E\n", "2", "S and E are walkable like any free cell")


@case
def new_req_002_every_rectangle_and_alphabet_violation_is_rejected():
    for text in ["S.\n.E.\n", "S..\n.E\n", "S\n.E\n", "SX\n.E\n", "S \n.E\n", "S\t\n.E\n"]:
        expect_malformed(text, "shape or alphabet violation %r" % text)


@case
def new_req_002_missing_or_repeated_endpoints_are_rejected():
    for text in ["..\n.E\n", "SS\n.E\n", "S.\n..\n", "S.\nEE\n", "SES\n...\n", "S.E\n.S.\n"]:
        expect_malformed(text, "endpoint violation %r" % text)


@case
def new_req_002_whitespace_and_line_endings_do_not_change_the_answer():
    base = "S.#\n..#\n#.E\n"
    variants = [
        base,
        "  " + base.replace("\n", "  \n") + "  ",
        "\n" + base + "\n\n",
        base.replace("\n", "\r\n"),
    ]
    answers = []
    for text in variants:
        with tempfile.TemporaryDirectory() as directory:
            result = run([write_map(directory, text)])
        assert result.returncode == 0, "%r must be accepted (%s)" % (text, result.stderr)
        answers.append(result.stdout)
    assert len(set(answers)) == 1, answers
    assert answers[0] == "4\n", answers


# --- REQ-003: shortest path length or unreachable -----------------------------


@case
def new_req_003_wall_obstacles_agree_with_floyd_warshall():
    detour = ["S....", "###.#", "#...#", "#.###", "#..E."]
    assert floyd_warshall_distance(detour, (0, 0), (4, 3)) == 11
    assert 11 > (4 - 0) + (3 - 0), "the only route must be longer than the straight line"
    expect_answer("\n".join(detour) + "\n", "11", "the snake maze is eleven moves")

    sealed = ["S....", ".###.", ".#E#.", ".###.", "....."]
    assert floyd_warshall_distance(sealed, (0, 0), (2, 2)) is None
    expect_answer("\n".join(sealed) + "\n", "unreachable", "a sealed exit has no route")


@case
def new_req_003_random_grids_match_floyd_warshall_through_the_cli():
    rng = random.Random(271828)
    checked = 0
    attempts = 0
    while checked < 30 and attempts < 600:
        attempts += 1
        rows, start, end = random_grid(rng, max_height=6, max_width=6)
        if start == end:
            continue
        rendered = render_fixture(rows, start, end)
        got = answer(rendered)
        expected = floyd_warshall_distance(rows, start, end)
        wanted = "unreachable" if expected is None else str(expected)
        assert got == wanted, "map %r: CLI %s, Floyd-Warshall %s" % (rendered, got, wanted)
        checked += 1
    assert checked == 30, "the differential produced only %d maps" % checked


@case
def new_req_003_zero_length_is_a_plain_decimal_zero():
    import unittest.mock as mock

    assert pathfind.shortest(["S"], (0, 0), (0, 0)) == 0
    with tempfile.TemporaryDirectory() as directory:
        path = write_map(directory, "S\n")
        with mock.patch.object(pathfind, "parse", return_value=(["S"], (0, 0), (0, 0))):
            code, out, err = captured_main([path])
    assert code == 0, err
    assert out == "0\n", "a zero-length path is the bare digit 0, got %r" % out
    assert err == "", err


@case
def new_req_003_multi_digit_answers_are_unlabelled_integers():
    size = 12
    grid = [["." for _ in range(size)] for _ in range(size)]
    grid[0][0] = "S"
    grid[size - 1][size - 1] = "E"
    text = "\n".join("".join(row) for row in grid) + "\n"
    expect_answer(text, str(2 * (size - 1)), "a clear 12x12 grid is 22 moves")


# --- REQ-004: a discoverable, wired test entry point ---------------------------


@case
def new_req_004_the_test_entry_point_is_discoverable_and_wired():
    with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as handle:
        package = json.load(handle)
    assert package.get("scripts", {}).get("test") == "bash run-tests.sh", package.get("scripts")
    runner_path = os.path.join(ROOT, "run-tests.sh")
    assert os.path.exists(runner_path), "run-tests.sh must exist at the project root"
    with open(runner_path, encoding="utf-8") as handle:
        runner = handle.read()
    assert "pathfind_tests.py" in runner, "run-tests.sh must run the delivered suite"
    assert REPORT == os.path.join(ROOT, "reports", "tests.tap"), REPORT


@case
def new_req_004_the_suite_has_reachable_wall_and_unreachable_cases():
    names = " ".join(function.__name__ for function in CASES).lower()
    assert "reachable" in names or "detour" in names, "the suite must assert a reachable path"
    assert "wall" in names or "detour" in names, "the suite must route around walls"
    assert "unreachable" in names, "the suite must assert the unreachable case"


# --- REQ-005: the declared mutation tool ---------------------------------------


@case
def new_req_005_the_declared_mutation_command_is_wired_to_measurable_mutants():
    assert os.path.exists(os.path.join(ROOT, "node_modules", ".bin", "stryker")), (
        "npx stryker must resolve to the committed local binary"
    )
    harness = load_mutation_harness()
    assert harness.DEFAULT_REPORT == os.path.join("reports", "mutation", "mutation.json"), (
        harness.DEFAULT_REPORT
    )
    assert len(harness.MUTANTS) > 0, "the harness must measure at least one mutant"
    for mutant_id, find, replace, description in harness.MUTANTS:
        assert mutant_id and find and replace and description, mutant_id
        assert find != replace, "mutant %s must change behaviour" % mutant_id


# --- AMB-001: orthogonal adjacency --------------------------------------------


@case
def new_amb_001_diagonal_targets_cost_the_manhattan_distance():
    expect_answer("S.\n.E\n", "2", "a diagonal target is two orthogonal moves")
    expect_answer("S...\n....\n...E\n", "5", "a 3x4 grid is five orthogonal moves")
    expect_answer("S#\n#E\n", "unreachable", "a diagonal step is not a move")


@case
def new_amb_001_the_neighbourhood_is_exactly_the_four_edges():
    assert set(pathfind.NEIGHBOURS) == {(-1, 0), (1, 0), (0, -1), (0, 1)}
    assert all(abs(row) + abs(column) == 1 for row, column in pathfind.NEIGHBOURS)


# --- AMB-002: the printed number counts moves, not cells -----------------------


@case
def new_amb_002_a_corridor_counts_edges_not_cells():
    expect_answer("SE\n", "1", "adjacent S and E is one move")
    expect_answer("S.E\n", "2", "S.E is two moves, not three cells")
    expect_answer("S..E\n", "3", "S..E is three moves, not four cells")
    expect_answer("S\nE\n", "1", "E below S is one move")


# --- AMB-003: a malformed map is a reject stop-error ---------------------------


@case
def new_amb_003_every_malformed_class_is_a_stop_error():
    malformed = ["", "\n\n", "S.\n.E.\n", "SX\n.E\n", "..\n.E\n", "SS\n.E\n", "S.\n..\n", "S.\nEE\n"]
    for text in malformed:
        expect_malformed(text, "malformed map %r" % text)
        parse_error(text, "parse must reject %r" % text)


# --- The delivered pipeline (REQ-001..REQ-005 through the workflow) -----------
#
# ci_config regenerates .github/workflows/ci.yml from a generic skeleton for
# every delivery, and the regenerated skeleton can name another project's world
# (an unexecutable `bash common-keys.sh {json}` placeholder, a package-manager
# test command) while the delivered suite stays green. These cases pin the
# repair: the pipeline must carry the declared commands and the declared report
# paths, every map it feeds the deliverable must be a valid map, and the answers
# it declares must be exactly what the delivered entry point prints.

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ci.yml")


def workflow_text():
    with open(WORKFLOW, encoding="utf-8") as handle:
        return handle.read()


def parse_workflow_jobs(text):
    """Return {job-name: body-lines} for the workflow's ``jobs:`` mapping."""
    jobs = {}
    current = None
    in_jobs = False
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            current = None
            continue
        if not in_jobs:
            continue
        name = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if name:
            current = name.group(1)
            jobs[current] = []
            continue
        if current is not None:
            jobs[current].append(line)
    return jobs


def job_timeout_minutes(body):
    """The job-level ``timeout-minutes`` (four spaces) in a job body, or None."""
    for line in body:
        match = re.match(r"^    timeout-minutes:\s*([0-9]+)\s*$", line)
        if match:
            return int(match.group(1))
    return None


def heredoc(text, tag):
    """Return the dedented body lines of the ``<<'tag'`` heredoc in ``text``."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "<<'%s'" % tag not in line:
            continue
        body = []
        for following in lines[index + 1:]:
            if following.strip() == tag:
                # The heredoc sits inside a YAML block scalar, so the shell
                # sees the body without the workflow's own indentation.
                return [row.strip() for row in body]
            body.append(following)
        raise AssertionError("heredoc %s is never closed" % tag)
    raise AssertionError("the workflow declares no %s heredoc" % tag)


def declared_maps(text):
    """Return {map-file: grid-lines} for every ``cat > file <<'TAG'`` in the run."""
    return {
        name: heredoc(text, tag)
        for name, tag in re.findall(r"cat > (\S+) <<'([A-Z0-9_]+)'", text)
    }


def declared_answers(text):
    """Return [(map-file, declared answer)] from the workflow's diff step."""
    expected = {
        name: value for value, name in re.findall(r"printf '([^']*)\\n' > (\S+)", text)
    }
    pairs = []
    for expected_file, answer_file in re.findall(r"^\s*diff -u (\S+) (\S+)$", text, re.M):
        assert expected_file in expected, "%s is diffed but never written" % expected_file
        assert answer_file.endswith(".answer"), answer_file
        pairs.append((answer_file[: -len(".answer")], expected[expected_file]))
    return pairs


@case
def pipeline_declares_the_three_jobs_each_with_a_time_bound():
    jobs = parse_workflow_jobs(workflow_text())
    assert {"tests", "deliverable", "mutation"} <= set(jobs), sorted(jobs)
    for name, body in jobs.items():
        assert job_timeout_minutes(body) is not None, "job %s has no timeout-minutes" % name


@case
def pipeline_runs_the_declared_test_command_and_reads_the_tap_report():
    text = workflow_text()
    assert "bash run-tests.sh" in text, "the pipeline must run the delivered suite"
    assert "reports/tests.tap" in text, "the pipeline must read the declared TAP report"
    assert "TAP version 13" in text, "the pipeline must require real TAP"


def workflow_code():
    """The workflow without its comment lines, i.e. what the runner executes."""
    return "\n".join(
        line for line in workflow_text().splitlines() if not line.strip().startswith("#")
    )


@case
def pipeline_runs_the_declared_deliverable_command():
    text = workflow_text()
    code = workflow_code()
    assert "bash pathfind.sh" in text, "the pipeline must run the declared entry point"
    assert "common-keys.sh" not in code, "the pipeline must not name another project's entry point"
    assert "{json}" not in code, "the pipeline must not carry an unexecutable placeholder"
    assert "pnpm test" not in code, "the pipeline must run the declared suite, not a guess"


@case
def pipeline_runs_the_declared_mutation_command_and_reads_its_report():
    text = workflow_text()
    assert "npx stryker run --reporters json" in text, "the declared mutation command is missing"
    assert "reports/mutation/mutation.json" in text, "the declared mutation report is missing"


@case
def pipeline_limits_the_token_and_cancels_superseded_runs():
    text = workflow_text()
    permissions = re.search(r"(?ms)^permissions:\s*\n((?:[ \t]+[^\n]*\n)*)", text)
    assert permissions is not None, "the pipeline grants no permissions block"
    assert re.search(r"contents:\s*read", permissions.group(1)), permissions.group(1)
    assert not re.search(r":\s*write", permissions.group(1)), "the pipeline escalates a permission"
    concurrency = re.search(r"(?ms)^concurrency:\s*\n((?:[ \t]+[^\n]*\n)*)", text)
    assert concurrency is not None, "the pipeline declares no concurrency block"
    assert "cancel-in-progress: true" in concurrency.group(1), concurrency.group(1)


@case
def pipeline_maps_are_valid_and_its_answers_match_the_entry_point():
    text = workflow_text()
    maps = declared_maps(text)
    answers = declared_answers(text)
    assert maps, "the pipeline feeds the deliverable no map"
    assert answers, "the pipeline declares no expected answer"
    for map_file, declared in answers:
        assert map_file in maps, "%s has no map heredoc" % map_file
        content = "\n".join(maps[map_file]) + "\n"
        rows, start, end = pathfind.parse(content)
        distance = reference_distance(rows, start, end)
        oracle = "unreachable" if distance is None else str(distance)
        assert declared == oracle, "%s declares %r, the oracle says %r" % (
            map_file,
            declared,
            oracle,
        )
        assert answer(content) == declared, "%s: the CLI disagrees with the declared answer" % map_file


@case
def pipeline_map_set_covers_reachable_wall_and_unreachable_worlds():
    answers = dict(declared_answers(workflow_text()))
    values = list(answers.values())
    assert "unreachable" in values, "the pipeline must run an unreachable map"
    numbers = [int(value) for value in values if value != "unreachable"]
    assert any(number > 0 for number in numbers), "the pipeline must run a reachable map"


# --- Visible, discoverable test entry point (see run-tests.sh) ------------------
#
# run-tests.sh at the project root runs this module and exits non-zero when any
# case fails; package.json's `test` script delegates to it. The delivery's smoke
# gate therefore runs `pnpm test`, which runs `bash run-tests.sh`, which writes
# the declared TAP report at reports/tests.tap.


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
    # The summary lines are what a generic TAP reader (and the delivery's smoke
    # gate) reads the totals from; the plan alone is not a summary.
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
        sys.stderr.write("pathfind tests: %d of %d failed\n" % (len(failed), len(results)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
