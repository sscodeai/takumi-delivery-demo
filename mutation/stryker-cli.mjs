#!/usr/bin/env node
// Compatibility alias for the mutation harness.
//
// The confirmed requirement document declares the mutation step as:
//
//     mutation:
//       run:           bash mutation.sh
//       report_path:   reports/mutation/mutation.json
//       format:        survivors-json
//       max_survivors: 0
//
// `bash mutation.sh` is the declared entry point. This executable is kept so an
// older `npx stryker run --reporters json` invocation still works: it accepts
// the declared arguments and the `--report` path, and hands off to the same
// harness (mutation/common_keys_mutation.py), which writes the report to
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
