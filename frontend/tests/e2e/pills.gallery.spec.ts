import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';

// NFR-S8 (NFR-03, AC-NFR3): pins the pill gallery in both themes (playbook
// 6.7, 9: "the design's tones, slots and labels drifting, in either theme").
// It lives here rather than in shared.journey.spec.ts because its screenshot
// baselines sit beside this file.
//
// The gallery renders a light column and a dark column with their own theme
// classes, so ONE baseline covers both themes. The page is loaded under a
// light and then a dark system theme and compared to the SAME baseline: that
// is the proof that the columns do not follow the visitor's theme. Two
// separate baselines were byte-identical (2026-09-19), which is a control
// that reports green while proving nothing; comparing to one baseline makes
// the equality the assertion.
//
// Beside the screenshot, each section's pills are read as text, tone and
// label in order, and compared to GALLERY below. The screenshot catches a
// changed colour; the text names the tone, label or slot order that moved,
// in words a review can read.

// What pills-and-labels.html shows, section by section: "tone: label", with
// "outlined" for a tenant tag. The labels are the gallery's sample data
// (src/app/dev/pills/samples.ts) and the section titles its catalog copy.
const GALLERY = `
Six tones
  information: information
  notice: notice
  positive: positive
  warning: warning
  negative: negative
  brand: brand
  information outlined: Tenant tag
Change row
  notice: Adopted rule
  negative: Act now
  brand: Advice perimeter
  information: Needs triage
  notice: EU proposal
  warning: Within 3 months
  brand: AI
  information outlined: Q4 review
Obligation row
  brand: LVM
  positive: Applies
  warning: Partly compliant
  notice: 2 open changes
  brand: ESMAGL
  information: Guidance
  positive: Applies
  negative: Gap
  brand: Appropriateness
  information outlined: Digital investing
Obligation header
  brand: LVM
  information: Securities
  information: Binding
  warning: Partly compliant
  brand: ESMAGL
  information: Securities
  warning: Guidance, comply or explain
  negative: Gap
Instrument header
  brand: FFFS 2017:2
  information: FI regulation
  information: Binding
  brand: Sweden
  information: Securities
  brand: ESMA guidelines
  information: EU guidance, level 3
  warning: Guidance, comply or explain
  brand: EU
Scope block
  brand: Bank
  brand: Fund company
  brand: All services
Gap
  negative: Open
  negative: High
  information: Impact assessment
  warning: Remediating
  warning: Medium
  information: Annual review
Roadmap item
  negative: Act now
  brand: Our deadline
Severity scales
  negative: Act now
  warning: Within 3 months
  notice: 6+ months
  information: Monitor
  positive: No action
  positive: Compliant
  warning: Partly compliant
  negative: Gap
  information: Not assessed
  negative: Open
  warning: Remediating
  information: Risk accepted
  positive: Closed
  negative: High
  warning: Medium
  information: Low
Register entry
  brand: LVM
  positive: Applies
  warning: Partly compliant
  notice: 2 open changes
  brand: ESMAGL
  information: Guidance
  information: Does not apply
  information outlined: Private to us
  information outlined: Outsourcing policy
  positive: Applies
  positive: Compliant
Applicability
  positive: Applies
  information: Does not apply
  information: Not assessed
Case status
  information: Needs triage
  information: Assigned
  information: Waiting for legal
  information: Being implemented
  information: Waiting for sign-off
  information: Closed
  information: Dismissed
Evidence and actions
  notice: Being checked
  positive: Checked
  warning: Could not be checked
  negative: Refused, malware found
  negative: Overdue
Participants
  positive: You
  information outlined: Legal
Notification kinds
  information: Mention
  information: Assigned to you
  information: Added to
  warning: Sign-off requested
  warning: Approval requested
  warning: Due soon
  warning: Review due
  warning: Proposal waiting
  negative: Overdue
  negative: Escalated
  notice: Change on your item
  notice: New search match
My work
  negative: Gap
  negative: Act now
Certificate
  brand: Our deadline
  brand: Our deadline
Our agents and their runs
  positive: On
  warning: Paused
  information: Off
  positive: Done
  notice: Running
  warning: Stopped
  negative: Failed
  information: Queued
  notice: Running
  positive: Done
  negative: Failed
  information: Rejected
  information: Cancelled
  information: Platform
  brand: Version 3
  positive: Active
  information: For banks
  information: Draft
Agent access
  positive: Active
  notice: Reads our register
  positive: Active
  information: Library only
  information: Revoked
  information: Service
  information: library read
  information: tenant read
  information: Personal
  warning: Expired
  information: library read
  information: Service
  information: Revoked
  information: search read
Support access
  warning: Waiting for approval
  notice: Active
  information: Ended
  information: Revoked
  information: Declined
  information: Lapsed
Our own records
  information outlined: Private to us
  information outlined: Outsourcing policy
  information: Banking
  information: Binding
  positive: Compliant
  notice: New obligation
  warning: Waiting
  brand: Proposed by our agent
  notice: New instrument
  positive: Approved
  warning: Waiting for your agent
  notice: Our agent is researching
  positive: Researched
`.trim();

async function settled(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
}

/** One theme column's sections as text: the title, then each pill as "tone: label" in the order it renders. */
async function galleryText(page: Page, column: 'light' | 'dark'): Promise<string> {
  const sections = await page.locator(`[data-theme-column="${column}"] section`).evaluateAll((nodes) =>
    nodes.map((section) => {
      const pills = [...section.querySelectorAll('[data-pill]')].map((pill) => {
        const outlined = pill.hasAttribute('data-outlined') ? ' outlined' : '';
        return `  ${pill.getAttribute('data-pill') ?? ''}${outlined}: ${pill.textContent ?? ''}`;
      });
      return [section.querySelector('h2')?.textContent ?? '', ...pills].join('\n');
    }),
  );
  return sections.join('\n');
}

test.describe('pill gallery', () => {
  for (const scheme of ['light', 'dark'] as const) {
    test(`NFR-S8: The pill gallery matches the design card in both themes, ${scheme} system theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto('/dev/pills');
      await expect(page.locator('[data-theme-column="light"]')).toBeVisible();
      await expect(page.locator('[data-theme-column="dark"]')).toBeVisible();
      await expect(page.locator('[data-pill]').first()).toBeVisible();
      // The page really took the system theme: next-themes puts `light` or
      // `dark` on <html> (providers.tsx), so the columns are shown not to follow it.
      await expect(page.locator('html')).toHaveClass(new RegExp(`(^|\\s)${scheme}(\\s|$)`));

      // Both columns read the same: a theme changes colours, never a tone, a label or an order.
      expect(await galleryText(page, 'light')).toBe(GALLERY);
      expect(await galleryText(page, 'dark')).toBe(GALLERY);

      await settled(page);
      await expect(page).toHaveScreenshot('pills-gallery.png', { fullPage: true });
    });
  }
});
