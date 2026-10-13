#!/usr/bin/env node
// The declared mutation entry point.
//
// docs/requirements/intake.yaml declares the mutation harness as:
//
//     mutation:
//       run:           npx stryker run --reporters json
//       report_path:   reports/mutation/mutation.json
//       format:        survivors-json
//       max_survivors: 0
//
// The declared report format is the tool-agnostic survivors-json shape, not a
// mutator-specific one, so the project ships its own `stryker` executable
// (node_modules/.bin/stryker, documented in package.json's `bin` field and in
// the README). It accepts the declared arguments (`run`, `--reporters json`)
// and hands off to the project's mutation harness, which writes the report to
// reports/mutation/mutation.json by default.

import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function reportPath(argv) {
  let path = 'reports/mutation/mutation.json';
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--report' && argv[index + 1] !== undefined) {
      path = argv[index + 1];
      index += 1;
    } else if (argument.startsWith('--report=')) {
      path = argument.slice('--report='.length);
    }
  }
  return path;
}

const result = spawnSync(
  'python3',
  [
    resolve(projectRoot, 'mutation', 'common_keys_mutation.py'),
    '--report',
    reportPath(process.argv.slice(2)),
  ],
  { cwd: projectRoot, stdio: 'inherit' },
);

if (result.error) {
  process.stderr.write(`the mutation harness could not start: ${result.error.message}\n`);
  process.exit(1);
}
process.exit(result.status === null ? 1 : result.status);
