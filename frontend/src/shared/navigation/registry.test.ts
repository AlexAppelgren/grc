import { describe, expect, it } from 'vitest';

import { catalogs } from '@/shared/i18n/messages';

import { ACCOUNT_PARENT, childDestinations, destinations, dockDestinations, findDestination, isCurrent, unlocks, visibleDestinations } from './registry';

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
    expect(visibleDestinations('console', ['proposals.review', 'library_vocab.manage', 'sources.manage']).map((d) => d.id)).toEqual([
      'console-queue',
      'console-vocabularies',
      'console-sources',
    ]);
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
    expect(dockDestinations('console', all).map((d) => d.id)).toEqual(['console-queue', 'console-vocabularies', 'console-sources']);
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
    expect(childDestinations(ACCOUNT_PARENT, []).map((d) => d.href)).toEqual(['/me/passkeys', '/me/sessions']);
    // Children never reach the rail or the dock.
    const all = destinations.flatMap((d) => d.anyOfPermissions);
    expect(visibleDestinations('tenant', all).every((d) => d.parent === undefined)).toBe(true);
    expect(dockDestinations('tenant', all).map((d) => d.id)).toEqual(['today', 'watch', 'inventory', 'search']);
    for (const child of destinations.filter((d) => d.parent !== undefined && d.parent !== ACCOUNT_PARENT)) {
      expect(findDestination(child.parent ?? '')).toBeDefined();
    }
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
});
