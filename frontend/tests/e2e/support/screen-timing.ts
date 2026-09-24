import type { Page } from '@playwright/test';

import { destinations, type Destination } from '@/shared/navigation/registry';

import { expect } from './api-guard';
import { budgetOf } from './screen-budgets';

// Screen timing for NFR-S7 (NFR-02, CLAUDE.md section 6): the time from a
// client-side navigation to the destination's own real data, as the browser
// sees it. Each sample starts on a fresh load of another screen, so the
// destination's queries are never already in the page's cache, then asks the
// app's router for the destination and watches every frame until the real-data
// locator of support/screen-budgets.ts is visible. The median of the samples
// is the screen's time. A screen measured under `next dev` would measure the
// dev server's on-demand compile, so the helper refuses one.

function samplesSetting(raw: string | undefined): number {
  const samples = Number(raw ?? 5);
  if (!Number.isInteger(samples) || samples < 1) throw new Error(`screen timing: E2E_SCREEN_SAMPLES must be a whole number of at least 1, not "${raw}"`);
  return samples;
}

/** Samples per screen; the median of them is the screen's time. */
export const SCREEN_SAMPLES = samplesSetting(process.env.E2E_SCREEN_SAMPLES);

/** How long a sample waits for the real data before it fails the screen, whatever its budget. */
const READY_TIMEOUT_MS = 10_000;

/** The screen a sample starts from: an account page every signed-in person opens, and never the destination itself. */
function startOf(destination: Destination): Destination {
  const start = destinations.find((d) => d.id === (destination.id === 'me-sessions' ? 'me-passkeys' : 'me-sessions'));
  if (start === undefined) throw new Error('screen timing: the registry lists no account page to start from');
  return start;
}

/** Loads a screen from cold and waits until its real data is on screen and nothing is still loading. */
async function settle(page: Page, destination: Destination): Promise<void> {
  await page.goto(destination.href);
  await expect(page.locator(budgetOf(destination).ready).first(), `screen timing: ${destination.href} never showed its real data`).toBeVisible({ timeout: READY_TIMEOUT_MS });
  await expect(page.locator('[data-loading-state]'), `screen timing: a skeleton lingers on ${destination.href}`).toHaveCount(0);
}

/** Next exposes `window.nd` only in a development build (next/dist/client/components/app-router.js). */
export async function expectProductionBuild(page: Page): Promise<void> {
  const development = await page.evaluate(() => 'nd' in window);
  if (development) throw new Error('screen timing: the app is a development build (next dev); measure against next build && next start');
}

/** One sample: milliseconds from the router push to the first frame that shows the real data. */
async function sample(page: Page, destination: Destination): Promise<number> {
  const { ready } = budgetOf(destination);
  const elapsed = await page.evaluate(
    ({ href, selector, timeout }) =>
      new Promise<number | null>((resolve) => {
        const router = (window as unknown as { next?: { router?: { push: (href: string) => void } } }).next?.router;
        if (router === undefined) throw new Error('screen timing: the app exposes no router on window.next');
        const started = performance.now();
        const frame = () => {
          const shown = [...document.querySelectorAll(selector)].some((element) => element.checkVisibility());
          const now = performance.now() - started;
          if (shown && window.location.pathname === href) resolve(now);
          else if (now > timeout) resolve(null);
          else requestAnimationFrame(frame);
        };
        router.push(href);
        requestAnimationFrame(frame);
      }),
    { href: destination.href, selector: ready, timeout: READY_TIMEOUT_MS },
  );
  if (elapsed === null) throw new Error(`screen timing: ${destination.href} showed no "${ready}" within ${READY_TIMEOUT_MS} ms of navigation`);
  await expect(page.locator('[data-loading-state]'), `screen timing: a skeleton lingers on ${destination.href} after its real data`).toHaveCount(0);
  return elapsed;
}

/**
 * The median, over SCREEN_SAMPLES client-side navigations, of the time the
 * destination takes to show its real data. Fails loudly when the real data
 * never shows, when a skeleton lingers beside it, or under next dev.
 */
export async function measureScreen(page: Page, destination: Destination): Promise<number> {
  const times: number[] = [];
  for (let i = 0; i < SCREEN_SAMPLES; i += 1) {
    await settle(page, startOf(destination));
    await expectProductionBuild(page);
    times.push(await sample(page, destination));
  }
  times.sort((a, b) => a - b);
  const middle = Math.floor(times.length / 2);
  const upper = times[middle] ?? 0;
  return times.length % 2 === 1 ? upper : ((times[middle - 1] ?? 0) + upper) / 2;
}
