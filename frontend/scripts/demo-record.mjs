// Re-records the public page's demo (src/features/demo) on the demo's own stack
// (playwright.config.ts, E2E_DEMO_STACK: the real library baseline and a made-up
// bank, seeded by seed_public_demo), in two passes of the demo journey, each
// alone so nothing changes the data under it. The first walks the app and
// writes the recordings. The second photographs the demo for the public page's
// picture of it, so it runs on a fresh build that already carries those
// recordings: stop any server on the demo stack's ports (3007 and 8007 by
// default) first, or Playwright reuses its older build. Arguments pass through
// to Playwright (a -c for another config). The same command on Windows, macOS
// and Linux, with no shell in between.
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';

const cli = createRequire(import.meta.url).resolve('@playwright/test/cli');

function pass(grep) {
  const args = [cli, 'test', 'tests/e2e/demo.journey.spec.ts', '--grep', grep, '--workers=1', '--retries=0', ...process.argv.slice(2)];
  return spawnSync(process.execPath, args, { stdio: 'inherit', env: { ...process.env, DEMO_RECORD: '1', E2E_DEMO_STACK: '1' } }).status ?? 1;
}

const recorded = pass('recordings still answer');
process.exit(recorded === 0 ? pass('pictures of the demo') : recorded);
