import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { catalogs } from '@/shared/i18n/messages';

import {
  ACCOUNT_PARENT,
  CONSOLE_HOME,
  childDestinations,
  destinations,
  dockDestinations,
  findDestination,
  homeOf,
  isCurrent,
  isInMore,
  moreDestinations,
  surfaceOf,
  unlocks,
  visibleDestinations,
} from './registry';

/** Every platform permission (PRD section 6), so a test sees every console destination the registry holds. */
const PLATFORM = ['proposals.review', 'library_vocab.manage', 'sources.manage', 'eval.manage', 'tenants.manage', 'agent_definitions.manage', 'support_access.grant', 'system.health'];

describe('navigation registry (playbook 6.2)', () => {
  it('seeds the prototype destinations on the tenant surface and the console ones', () => {
    expect(visibleDestinations('tenant', ['watch.read', 'library.read', 'roadmap.read', 'search.use', 'vocab.manage']).map((d) => d.id)).toEqual([
      'today',
      'watch',
      'inventory',
      'roadmap',
      'search',
      'admin',
    ]);
    // A console destination registers with its page: vocabularies and tenants
    // from chunk 4, Change facts, Sources and Agent keys from chunk 5,
    // Evaluation from chunk 7. The queue joins with its own.
    expect(visibleDestinations('console', PLATFORM).map((d) => d.id)).toEqual([
      'console-queue',
      'console-vocabularies',
      'console-change-facts',
      'console-sources',
      'console-tenants',
      'console-agent-keys',
      'console-evaluation',
    ]);
    // Each console destination answers to the one platform role that holds
    // its permission, so neither platform role sees the other's (ADM-S4).
    expect(visibleDestinations('console', ['library_vocab.manage']).map((d) => d.id)).toEqual(['console-vocabularies']);
    expect(visibleDestinations('console', ['tenants.manage']).map((d) => d.id)).toEqual(['console-tenants']);
    // A library editor reviews the queue, reads the change facts and the
    // sources; the platform admin holds the agent keys. Neither reaches the
    // other's. Queue and Change facts share proposals.review (chunk4-T14).
    expect(visibleDestinations('console', ['proposals.review']).map((d) => d.id)).toEqual(['console-queue', 'console-change-facts']);
    expect(visibleDestinations('console', ['sources.manage']).map((d) => d.id)).toEqual(['console-sources']);
    expect(visibleDestinations('console', ['agent_definitions.manage']).map((d) => d.id)).toEqual(['console-agent-keys']);
    expect(visibleDestinations('console', ['eval.manage']).map((d) => d.id)).toEqual(['console-evaluation']);
  });

  it('registers a console destination only once its page exists, so none renders "coming soon"', () => {
    for (const d of destinations.filter((entry) => entry.surface === 'console')) {
      expect(existsSync(join(import.meta.dirname, '..', '..', 'app', '(console)', d.href, 'page.tsx')), d.href).toBe(true);
    }
  });

  it('gives platform staff, who sign in without a tenant, the console, and everyone else their organisation', () => {
    const tenant = { id: 't1', name: 'Example Bank AB', slug: 'example', timezone: 'Europe/Stockholm' };
    expect(surfaceOf({ tenant: null })).toBe('console');
    expect(homeOf({ tenant: null })).toBe(CONSOLE_HOME);
    expect(CONSOLE_HOME).toBe('/console');
    expect(surfaceOf({ tenant })).toBe('tenant');
    expect(homeOf({ tenant })).toBe('/');
    // No session yet: the tenant surface, whose gate sends the visitor to sign in.
    expect(surfaceOf(null)).toBe('tenant');
    expect(homeOf(null)).toBe('/');
  });

  it('shows a destination iff the permission list unlocks it, never by role name', () => {
    expect(unlocks([], [])).toBe(true);
    expect(unlocks(['watch.read'], [])).toBe(false);
    expect(unlocks(['members.manage', 'vocab.manage'], ['vocab.manage'])).toBe(true);
    expect(visibleDestinations('tenant', []).map((d) => d.id)).toEqual(['today']);
    expect(visibleDestinations('tenant', ['search.use']).map((d) => d.id)).toEqual(['today', 'search']);
  });

  it('orders the phone dock by rank', () => {
    const all = destinations.flatMap((d) => d.anyOfPermissions);
    expect(dockDestinations('tenant', all).map((d) => d.id)).toEqual(['today', 'watch', 'inventory', 'search']);
    expect(dockDestinations('console', all).map((d) => d.id)).toEqual(['console-queue', 'console-vocabularies', 'console-tenants', 'console-sources']);
  });

  // iOS shows at most four tabs plus More (UIKit UITabBarController), and
  // More is always the fifth item here (design/system/navigation.md 2). A
  // fifth ranked destination would silently drop out of the bar, so the cap
  // lives in this test and nowhere in the code.
  it('ranks at most four destinations per surface, so every ranked one fits in the tab bar beside More', () => {
    const MAX_TABS_BESIDE_MORE = 4;
    for (const surface of ['tenant', 'console'] as const) {
      expect(destinations.filter((d) => d.surface === surface && d.dockRank !== undefined).length).toBeLessThanOrEqual(MAX_TABS_BESIDE_MORE);
    }
  });

  it('puts every visible destination that is not a tab in More, and never promotes an unranked one', () => {
    const all = destinations.flatMap((d) => d.anyOfPermissions);
    expect(moreDestinations('tenant', all).map((d) => d.id)).toEqual(['roadmap', 'admin']);
    expect(moreDestinations('console', all).map((d) => d.id)).toEqual(['console-change-facts', 'console-agent-keys', 'console-evaluation']);

    expect(dockDestinations('tenant', []).map((d) => d.id)).toEqual(['today']);
    expect(moreDestinations('tenant', []).map((d) => d.id)).toEqual([]);

    // A ranked destination the person cannot open is skipped; the rest move up
    // and the empty slot stays empty rather than taking Roadmap or Admin.
    const noWatch = all.filter((p) => p !== 'watch.read');
    expect(dockDestinations('tenant', noWatch).map((d) => d.id)).toEqual(['today', 'inventory', 'search']);
    expect(moreDestinations('tenant', noWatch).map((d) => d.id)).toEqual(['roadmap', 'admin']);
  });

  it('knows when the current page lives in More, account pages included', () => {
    const all = destinations.flatMap((d) => d.anyOfPermissions);
    for (const path of ['/roadmap', '/admin/members', '/me/sessions', '/me/calendar-feeds']) {
      expect(isInMore('tenant', all, path)).toBe(true);
    }
    for (const path of ['/', '/watch', '/watch/42']) {
      expect(isInMore('tenant', all, path)).toBe(false);
    }
  });

  it('marks the current destination by path prefix, with Today exact', () => {
    const today = findDestination('today');
    const watch = findDestination('watch');
    if (today === undefined || watch === undefined) throw new Error('seed missing');
    expect(isCurrent(today, '/')).toBe(true);
    expect(isCurrent(today, '/watch')).toBe(false);
    expect(isCurrent(watch, '/watch')).toBe(true);
    expect(isCurrent(watch, '/watch/123')).toBe(true);
    expect(isCurrent(watch, '/watchlist')).toBe(false);
    expect(findDestination('nope')).toBeUndefined();
  });

  it('keeps admin sections and account links under their parent, gated by their own permission', () => {
    expect(childDestinations('admin', ['members.manage']).map((d) => d.id)).toEqual(['admin-organisation', 'admin-members']);
    expect(childDestinations('admin', ['roles.manage', 'integrations.manage', 'security.manage']).map((d) => d.id)).toEqual([
      'admin-organisation',
      'admin-roles',
      'admin-api-keys',
      'admin-security-log',
    ]);
    // Chunk 2: the vocabulary screen needs vocab.manage; the footprint screen
    // opens for either footprint grant and is read-only without the first.
    expect(childDestinations('admin', ['vocab.manage']).map((d) => d.id)).toEqual(['admin-organisation', 'admin-vocabularies']);
    expect(childDestinations('admin', ['footprint.request']).map((d) => d.id)).toEqual(['admin-organisation', 'admin-footprint']);
    expect(childDestinations('admin', ['footprint.approve']).map((d) => d.id)).toEqual(['admin-organisation', 'admin-footprint']);
    // An approver who holds nothing else still reaches /admin to find it.
    expect(visibleDestinations('tenant', ['footprint.approve']).map((d) => d.id)).toEqual(['today', 'admin']);
    // Notifications (COL-02) is any member's own inbox, first in the account group.
    expect(childDestinations(ACCOUNT_PARENT, []).map((d) => d.href)).toEqual(['/notifications', '/me/passkeys', '/me/sessions']);
    // Calendar feeds needs the grant the roadmap needs (HOM-04), so it joins the
    // account links only for a reader who holds it, and never unlocks anything else.
    expect(childDestinations(ACCOUNT_PARENT, ['roadmap.read']).map((d) => d.href)).toEqual(['/notifications', '/me/passkeys', '/me/sessions', '/me/calendar-feeds']);
    expect(visibleDestinations('tenant', ['roadmap.read']).map((d) => d.id)).toEqual(['today', 'roadmap']);
    // Children never reach the rail or the dock.
    const all = destinations.flatMap((d) => d.anyOfPermissions);
    expect(visibleDestinations('tenant', all).every((d) => d.parent === undefined)).toBe(true);
    expect(dockDestinations('tenant', all).map((d) => d.id)).toEqual(['today', 'watch', 'inventory', 'search']);
    for (const child of destinations.filter((d) => d.parent !== undefined && d.parent !== ACCOUNT_PARENT)) {
      expect(findDestination(child.parent ?? '')).toBeDefined();
    }
  });

  // AUD-01: audit.read is in every system role, so the audit log is the one
  // admin section a reader reaches, and it is what puts Admin in their rail.
  it('lets any member reach Admin for the audit log and the organisation profile', () => {
    expect(visibleDestinations('tenant', ['audit.read']).map((d) => d.id)).toEqual(['today', 'admin']);
    expect(childDestinations('admin', ['audit.read']).map((d) => d.id)).toEqual(['admin-organisation', 'admin-audit-log']);
    expect(findDestination('admin-audit-log')?.href).toBe('/admin/audit-log');
    expect(existsSync(join(import.meta.dirname, '..', '..', 'app', '(tenant)', 'admin', 'audit-log', 'page.tsx'))).toBe(true);
  });

  it('has unique ids and hrefs, and a label in every language', () => {
    const ids = destinations.map((d) => d.id);
    const hrefs = destinations.map((d) => d.href);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    for (const d of destinations) {
      expect(catalogs.en[d.labelKey]).toBeTruthy();
      expect(catalogs.sv[d.labelKey]).toBeTruthy();
    }
  });

  it('gives a tab its short label in every language, and Search one word', () => {
    const short = destinations.filter((d) => d.shortLabelKey !== undefined);
    expect(short.map((d) => d.id)).toEqual(['search']);
    for (const d of short) {
      const key = d.shortLabelKey ?? d.labelKey;
      expect(catalogs.en[key]).toBeTruthy();
      expect(catalogs.sv[key]).toBeTruthy();
    }
    expect(catalogs.en['nav.search.short']).toBe('Search');
    expect(catalogs.sv['nav.search.short']).toBe('Sök');
  });
});
