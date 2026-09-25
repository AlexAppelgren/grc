import { destinations, type Destination } from '@/shared/navigation/registry';

// The screen budgets of NFR-02 (playbook 10, CLAUDE.md section 6): every
// registered destination reaches real data within its budget, measured from a
// client-side navigation by support/screen-timing.ts. No screen carries a
// "data loaded" marker, so each row names the destination's own real-data
// locator: a CSS selector for an element the screen draws only from its API
// answer. A list the seed may leave empty, or another journey may empty,
// accepts the empty state too, which is also an answer and never a skeleton.
// A destination joins the registry with its row here; the completeness check
// in shared.journey.spec.ts fails until it does.

/** The budget of a screen with no row of its own that says otherwise (CLAUDE.md section 6). */
export const DEFAULT_SCREEN_BUDGET_MS = 500;

export interface ScreenBudget {
  /** A CSS selector for the destination's real data, never its skeleton or its heading. */
  ready: string;
  /** Milliseconds from navigation to `ready`; the default when absent. */
  budgetMs?: number;
}

const OR_EMPTY = ', [data-empty-state]';

export const SCREEN_BUDGETS: Readonly<Record<string, ScreenBudget>> = {
  today: { ready: '[data-lead-card]' },
  watch: { ready: '[data-change-rows] [data-change]' },
  inventory: { ready: '[data-obligation-rows] [data-obligation]' },
  roadmap: { ready: '[data-roadmap-card]' },
  briefing: { ready: `[data-lead-card], [data-brief-item]${OR_EMPTY}` },
  // At rest Ask asks nothing of the ask route (the question stays out of the
  // URL); it is ready when the permission gate has read the session and the
  // start panel is drawn. Search lives in the inventory's row (D-9x).
  ask: { ready: '[data-ask-start]' },
  admin: { ready: '[data-admin-section]' },
  'admin-organisation': { ready: '[data-onboarding] [data-step]' },
  'admin-members': { ready: '[data-members-list] [data-member-id]' },
  'admin-roles': { ready: '[data-roles-list] [data-role-key]' },
  'admin-vocabularies': { ready: '[data-vocabulary-lists] [data-vocabulary-list]' },
  'admin-footprint': { ready: '[data-footprint-dimensions] [data-dimension]' },
  'admin-api-keys': { ready: `[data-keys-list] [data-key-id]${OR_EMPTY}` },
  'admin-security-log': { ready: '[data-security-log] [data-event]' },
  'admin-audit-log': { ready: '[data-audit-log] [data-audit-row]' },
  'admin-ai-log': { ready: `[data-ai-log] [data-ai-row]${OR_EMPTY}` },
  'me-passkeys': { ready: '[data-passkey-id]' },
  'me-sessions': { ready: '[data-session-id]' },
  'me-calendar-feeds': { ready: `[data-feeds-list] [data-feed-id]${OR_EMPTY}` },
  'console-queue': { ready: `[data-proposal-rows] [data-proposal-id]${OR_EMPTY}` },
  'console-vocabularies': { ready: '[data-vocabulary-lists] [data-vocabulary-list]' },
  'console-change-facts': { ready: `[data-change-facts-list] [data-change-id]${OR_EMPTY}` },
  'console-sources': { ready: '[data-sources-list] [data-source-id]' },
  'console-tenants': { ready: '[data-tenants-list] [data-tenant-id]' },
  'console-agent-keys': { ready: `[data-agent-keys-list] [data-agent-key-id]${OR_EMPTY}` },
  'console-evaluation': { ready: `[data-eval-questions] [data-question-key]${OR_EMPTY}` },
};

/**
 * What keeps the table and the registry in step: a tenant or console
 * destination with no row, or a row with no destination.
 */
export function budgetGaps(): string[] {
  const ids = new Set(destinations.map((d) => d.id));
  return [
    ...[...ids].filter((id) => !(id in SCREEN_BUDGETS)).map((id) => `destination "${id}" has no screen budget`),
    ...Object.keys(SCREEN_BUDGETS)
      .filter((id) => !ids.has(id))
      .map((id) => `screen budget "${id}" names no registered destination`),
  ];
}

export function budgetOf(destination: Destination): Required<ScreenBudget> {
  const row = SCREEN_BUDGETS[destination.id];
  if (row === undefined) throw new Error(`screen budgets: destination "${destination.id}" has no row in support/screen-budgets.ts`);
  return { ready: row.ready, budgetMs: row.budgetMs ?? DEFAULT_SCREEN_BUDGET_MS };
}
