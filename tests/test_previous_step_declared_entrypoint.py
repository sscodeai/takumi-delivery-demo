"""Unit and integration tests for the previous step's declared mutation entry point.

The previous step (``fix: add the requirement-declared scripts/mutation.sh
entry point``) added ``scripts/mutation.sh``. ``test_scripts_mutation_entrypoint.py``
pins that script only statically; this module adds the behavioural layer:

* unit tests for the script's own contract -- it changes into the repository
  root, execs the harness, selects the legacy report path the earlier delivery
  named and forwards the caller's arguments; and
* integration tests that run the real script through a process boundary. The
  expensive harness is replaced by a recording stub in a throwaway copy, so the
  argument, working-directory and exit-code contract is exercised without
  paying for (or recursing into) a full mutation run. The real harness is still
  reached for its ``--help`` and usage-error paths.

The module also carries one independent acceptance test per ``REQ-nnn``
criterion and per ``AMB-nnn`` decision in the confirmed requirement document
(``docs/requirements/intake.yaml``), driven through the real process boundary
``bash summary.sh <csv>``. The focused suites cover the same contract in depth;
this layer keeps the criteria visible next to the previous step's artifact and
uses a differential oracle for the whole report.
"""

import importlib.util
import json
import os
import random
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from fractions import Fraction

from helpers import (
    HEADER,
    ROOT,
    SCRIPT,
    counts_sum,
    names_in_order,
    run_csv,
    skipped_of,
    station_lines,
    total_of,
)
from reference import reference_output, round_half_up_one

MUTATION_SCRIPT = os.path.join(ROOT, "scripts", "mutation.sh")
HARNESS = os.path.join(ROOT, "mutation", "mutation_test.py")
LEGACY_REPORT_ARG = "reports/mutation/mutation.json"

# A stand-in harness: it records how the entry point invoked it and exits with
# the code STUB_EXIT names. It lets the integration tests observe the real
# script's argv, cwd and exit-code propagation without running 14 mutants.
HARNESS_STUB = """\
import json
import os
import sys

with open(os.path.join(os.getcwd(), "invocation.json"), "w", encoding="utf-8") as handle:
    json.dump({"cwd": os.getcwd(), "argv": sys.argv[1:]}, handle)
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
"""


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class DeclaredMutationScriptUnitTests(unittest.TestCase):
    """The previous step's script is a real, runnable, root-relative entry point."""

    def setUp(self):
        self.source = read_text(MUTATION_SCRIPT)

    def test_the_previous_steps_script_exists_and_is_executable(self):
        self.assertTrue(os.path.isfile(MUTATION_SCRIPT), MUTATION_SCRIPT)
        self.assertTrue(
            os.stat(MUTATION_SCRIPT).st_mode & stat.S_IXUSR,
            "scripts/mutation.sh is not executable",
        )

    def test_the_script_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", MUTATION_SCRIPT],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_script_changes_into_the_repository_root(self):
        # scripts/mutation.sh lives one directory below the root, so it must
        # climb to the root before naming a repository-relative harness path.
        self.assertIn('cd "$(dirname "$0")/.."', self.source)

    def test_the_script_execs_the_harness(self):
        self.assertIn("exec python3 mutation/mutation_test.py", self.source)

    def test_the_script_selects_the_legacy_report_path(self):
        # The earlier delivery named reports/mutation/mutation.json; the
        # declared script keeps that name so a reader of either path is served.
        self.assertIn("--report %s" % LEGACY_REPORT_ARG, self.source)

    def test_the_script_forwards_the_callers_arguments(self):
        self.assertIn('"$@"', self.source)

    def test_the_harness_the_script_names_exists_and_accepts_the_path(self):
        self.assertTrue(os.path.isfile(HARNESS), HARNESS)
        spec = importlib.util.spec_from_file_location("declared_entry_harness", HARNESS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(
            module.parse_report(["--report", LEGACY_REPORT_ARG]),
            os.path.join(ROOT, LEGACY_REPORT_ARG),
        )


class DeclaredMutationScriptIntegrationTests(unittest.TestCase):
    """Run the real script against a stub harness, through a process boundary."""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="takumi-declared-entry-")
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.project = os.path.join(self.work, "project")
        os.makedirs(os.path.join(self.project, "scripts"))
        os.makedirs(os.path.join(self.project, "mutation"))
        shutil.copy2(
            MUTATION_SCRIPT, os.path.join(self.project, "scripts", "mutation.sh")
        )
        with open(
            os.path.join(self.project, "mutation", "mutation_test.py"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(HARNESS_STUB)

    def run_script(self, extra=(), cwd=None, env=None):
        run_env = dict(os.environ)
        if env:
            run_env.update(env)
        return subprocess.run(
            [
                "bash",
                os.path.join(self.project, "scripts", "mutation.sh"),
                *extra,
            ],
            cwd=cwd or self.project,
            capture_output=True,
            text=True,
            env=run_env,
            timeout=60,
        )

    def invocation(self):
        with open(
            os.path.join(self.project, "invocation.json"), encoding="utf-8"
        ) as handle:
            return json.load(handle)

    def test_the_script_passes_the_report_path_to_the_harness(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = self.invocation()
        self.assertEqual(
            recorded["argv"], ["--report", LEGACY_REPORT_ARG]
        )

    def test_the_script_runs_the_harness_from_the_project_root(self):
        caller = os.path.join(self.work, "caller")
        os.makedirs(caller)
        result = self.run_script(cwd=caller)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            os.path.realpath(self.invocation()["cwd"]),
            os.path.realpath(self.project),
        )

    def test_the_script_forwards_extra_arguments_after_the_report_flag(self):
        result = self.run_script(extra=["--timeout", "5"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.invocation()["argv"],
            ["--report", LEGACY_REPORT_ARG, "--timeout", "5"],
        )

    def test_the_script_propagates_a_failing_harness_exit_code(self):
        result = self.run_script(env={"STUB_EXIT": "7"})
        self.assertEqual(result.returncode, 7, result.stderr)

    def test_the_real_harness_reaches_its_help_path_through_the_script(self):
        result = subprocess.run(
            ["bash", MUTATION_SCRIPT, "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: mutation_test.py", result.stdout)

    def test_the_real_harness_rejects_an_unknown_flag_with_a_nonzero_exit(self):
        result = subprocess.run(
            ["bash", MUTATION_SCRIPT, "--definitely-not-a-flag"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage: mutation_test.py", result.stderr or result.stdout)


class ConfirmedRequirementAcceptanceTests(unittest.TestCase):
    """One test per REQ-nnn criterion, driven through ``bash summary.sh``."""

    def test_req_001_script_at_root_reads_the_first_positional_argument(self):
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")

    def test_req_002_header_is_consumed_and_each_valid_row_is_one_reading(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("date ", result.stdout.splitlines()[0])
        self.assertEqual(
            station_lines(result.stdout),
            ["ALPHA 2 1.0 2.0 1.5", "BRAVO 1 3.0 3.0 3.0"],
        )

    def test_req_003_one_line_per_station_with_count_min_max_mean(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-03,ALPHA,9.5\n"
            + "2024-01-01,BRAVO,-2.5\n"
            + "2024-01-02,BRAVO,-1.5\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            station_lines(result.stdout),
            ["ALPHA 3 9.5 11.6 10.5", "BRAVO 2 -2.5 -1.5 -2.0"],
        )
        for line in station_lines(result.stdout):
            for field in line.split(" ")[2:]:
                self.assertRegex(field, r"^-?[0-9]+\.[0-9]$")

    def test_req_004_exactly_one_total_equal_to_the_station_counts(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
        )
        result = run_csv(text)
        total_lines = [
            line for line in result.stdout.splitlines() if line.startswith("TOTAL ")
        ]
        self.assertEqual(total_lines, ["TOTAL 3"])
        self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))

    def test_req_005_malformed_rows_complete_and_change_no_aggregate(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA\n"
            + "no-such-date,ALPHA,2.0\n"
            + "2024-01-02,,3.0\n"
            + "2024-01-02,ALPHA,nan\n"
            + "2024-01-02,BRAVO,4.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            station_lines(result.stdout),
            ["ALPHA 1 1.0 1.0 1.0", "BRAVO 1 4.0 4.0 4.0"],
        )
        self.assertEqual(skipped_of(result.stdout), 4)
        self.assertEqual(total_of(result.stdout), 2)

    def test_req_006_permuting_rows_is_byte_identical(self):
        rows = [
            "2024-01-01,ALPHA,1.0",
            "2024-01-02,BRAVO,2.0",
            "2024-01-03,ALPHA,3.0",
            "2024-01-04,CHARLIE,4.0",
        ]
        baseline = run_csv(HEADER + "\n".join(rows) + "\n")
        for seed in range(5):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            result = run_csv(HEADER + "\n".join(shuffled) + "\n")
            self.assertEqual(result.stdout, baseline.stdout)

    def test_req_007_station_lines_ascend_byte_wise(self):
        text = (
            HEADER
            + "2024-01-01,zeta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,alpha,3.0\n"
            + "2024-01-04,Zulu,4.0\n"
        )
        result = run_csv(text)
        self.assertEqual(
            names_in_order(result.stdout),
            ["ALPHA", "Zulu", "alpha", "zeta", "SKIPPED", "TOTAL"],
        )

    def test_req_008_output_is_unchanged_with_networking_blocked(self):
        text = HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n"
        baseline = run_csv(text)
        blocked = dict(os.environ)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            blocked[name] = "http://127.0.0.1:9"
        blocked["NO_PROXY"] = ""
        offline = run_csv(text, env=blocked)
        self.assertEqual(offline.returncode, 0)
        self.assertEqual(offline.stdout, baseline.stdout)

    def test_req_009_two_hundred_thousand_rows_finish_promptly(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        path = handle.name
        handle.close()
        try:
            with open(path, "w", encoding="utf-8", newline="") as writer:
                writer.write(HEADER)
                for index in range(200000):
                    writer.write(
                        "2024-%02d-%02d,STATION-%03d,%.1f\n"
                        % (
                            index % 12 + 1,
                            index % 28 + 1,
                            index % 50,
                            -20 + index % 60,
                        )
                    )
            started = time.perf_counter()
            result = subprocess.run(
                ["bash", SCRIPT, path],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            elapsed = time.perf_counter() - started
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 0)
        self.assertIn("TOTAL 200000\n", result.stdout)
        self.assertLess(elapsed, 30.0, "200k rows took %.2fs" % elapsed)


class ConfirmedDecisionAcceptanceTests(unittest.TestCase):
    """One test per AMB-nnn decision, pinning the option the document chose."""

    def test_amb_001_skip_count(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA\n"
            + "not-a-date,ALPHA,2.0\n"
            + "2024-01-02,BRAVO,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(skipped_of(result.stdout), 2)
        self.assertEqual(total_of(result.stdout), 2)
        self.assertEqual(
            station_lines(result.stdout),
            ["ALPHA 1 1.0 1.0 1.0", "BRAVO 1 3.0 3.0 3.0"],
        )

    def test_amb_002_merge(self):
        # A repeated (date, station) key keeps every occurrence as a reading.
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.0\n"
            + "2024-01-01,ALPHA,20.0\n"
            + "2024-01-01,ALPHA,30.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 3 10.0 30.0 20.0\nSKIPPED 0\nTOTAL 3\n")

    def test_amb_003_half_up(self):
        for raw, want in (("1.25", "1.3"), ("-1.25", "-1.3"), ("0.05", "0.1")):
            with self.subTest(raw=raw):
                result = run_csv(HEADER + "2024-01-01,ALPHA,%s\n" % raw)
                self.assertEqual(
                    result.stdout,
                    "ALPHA 1 %s %s %s\nSKIPPED 0\nTOTAL 1\n" % (want, want, want),
                )
                self.assertEqual(want, round_half_up_one(Fraction(raw)))
        # A mean of exactly -0.15 rounds away from zero to -0.2.
        mean = run_csv(
            HEADER + "2024-01-01,ALPHA,-0.1\n2024-01-02,ALPHA,-0.2\n"
        )
        self.assertIn("ALPHA 2 -0.2 -0.1 -0.2\n", mean.stdout)

    def test_amb_004_ascending_station_id(self):
        text = (
            HEADER
            + "2024-01-01,beta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,Zulu,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(
            names_in_order(result.stdout),
            ["ALPHA", "Zulu", "beta", "SKIPPED", "TOTAL"],
        )

    def test_amb_005_total_counts_valid_readings_only(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
            + "not-a-date,BRAVO,4.0\n"
        )
        result = run_csv(text)
        self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))
        self.assertEqual(total_of(result.stdout), 3)
        self.assertEqual(skipped_of(result.stdout), 1)


class DifferentialAcceptanceTests(unittest.TestCase):
    """DIFF-001: an independent recomputation agrees on the whole report."""

    def test_the_whole_report_matches_an_independent_reference(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-02,BRAVO,-2.5\n"
            + "2024-01-03,CHARLIE,0.05\n"
            + "2024-01-04,ALPHA,11.55\n"
            + "2024-01-05,ALPHA\n"
            + "not-a-date,BRAVO,7.0\n"
            + "2024-01-06,DELTA,1.25\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference_output(text))


if __name__ == "__main__":
    unittest.main()
