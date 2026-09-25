// Re-records the public page's demo (src/features/demo) on the real stack:
// the demo journey in record mode, alone, so no other journey changes the data
// under it. Arguments pass through to Playwright (a -c for another config).
// The same command on Windows, macOS and Linux, with no shell in between.
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';

const cli = createRequire(import.meta.url).resolve('@playwright/test/cli');
const args = [cli, 'test', 'tests/e2e/demo.journey.spec.ts', '--grep', 'recordings', '--workers=1', '--retries=0', ...process.argv.slice(2)];
const run = spawnSync(process.execPath, args, { stdio: 'inherit', env: { ...process.env, DEMO_RECORD: '1' } });
process.exit(run.status ?? 1);
