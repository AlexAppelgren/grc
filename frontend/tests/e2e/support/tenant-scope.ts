import { mkdirSync, rmSync, statSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { test } from './api-guard';

// Tenant A's regulatory scope is one record every worker shares. The journeys that change it
// (FP-S2, FP-S5 and FP-S16's requests, WAT-S10's and REG-S15's E2E switch, J-10's request)
// and the ones that read what it hides or reveals (FP-S13's watched-market view, INV-S11's
// outside view of the standard) take turns through this lock, one directory per E2E stack:
// `mkdir` either creates it or fails, so exactly one journey holds it. A describe block takes
// it with `test.beforeEach(lockTenantAScope)` and gives it back with
// `test.afterEach(unlockTenantAScope)`, which runs on failure too. The time spent waiting is
// added to the journey's own timeout; a lock older than the longest journey is taken over,
// so a run that was killed mid-journey never blocks the next one.

const LOCK = path.join(os.tmpdir(), `cw-e2e-tenant-a-scope-${process.env.E2E_DATABASE_NAME ?? 'default'}`);
const STALE_MS = 4 * 60_000;
const POLL_MS = 250;
/** Whether this worker holds the lock, so a journey that timed out waiting never frees another's. */
let held = false;

function taken(): boolean {
  try {
    mkdirSync(LOCK);
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
    return false;
  }
}

function stale(): boolean {
  try {
    return Date.now() - statSync(LOCK).mtimeMs > STALE_MS;
  } catch (error) {
    // Released between the failed mkdir and this look: try again.
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false;
    throw error;
  }
}

export async function lockTenantAScope(): Promise<void> {
  const own = test.info().timeout;
  const started = Date.now();
  // No deadline while waiting; the journey's own starts again once it holds the lock.
  test.info().setTimeout(0);
  while (!taken()) {
    if (stale()) rmSync(LOCK, { recursive: true, force: true });
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
  held = true;
  test.info().setTimeout(own + (Date.now() - started));
}

export function unlockTenantAScope(): void {
  if (!held) return;
  held = false;
  rmSync(LOCK, { recursive: true, force: true });
}
