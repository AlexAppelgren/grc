import type { MessageKey } from '@/shared/i18n';

// The one typed navigation registry (playbook 6.2). Pure TypeScript, no
// React: sidebar, dock, More menu, command palette, the client gate and the
// Playwright role-matrix spec all derive from it. Nothing here checks a role
// name: a destination is visible iff the user's permission list unlocks it.
// The server's structured 403 remains the enforcer.

export type Surface = 'tenant' | 'console';
export type NavGroup = 'primary' | 'secondary' | 'admin';

export interface Destination {
  id: string;
  href: string;
  labelKey: MessageKey;
  surface: Surface;
  /** Empty means any signed-in user of that surface. Permission names are PRD section 6. */
  anyOfPermissions: readonly string[];
  /** Present on destinations that sit in the phone dock, lowest first. */
  dockRank?: number;
  group: NavGroup;
}

const TENANT_ADMIN_PERMISSIONS = [
  'members.manage',
  'roles.manage',
  'security.manage',
  'vocab.manage',
  'workflow.manage',
  'agents.manage',
  'integrations.manage',
] as const;

export const destinations: readonly Destination[] = [
  { id: 'today', href: '/', labelKey: 'nav.today', surface: 'tenant', anyOfPermissions: [], dockRank: 1, group: 'primary' },
  { id: 'watch', href: '/watch', labelKey: 'nav.watch', surface: 'tenant', anyOfPermissions: ['watch.read'], dockRank: 2, group: 'primary' },
  { id: 'inventory', href: '/inventory', labelKey: 'nav.inventory', surface: 'tenant', anyOfPermissions: ['library.read'], dockRank: 3, group: 'primary' },
  { id: 'roadmap', href: '/roadmap', labelKey: 'nav.roadmap', surface: 'tenant', anyOfPermissions: ['roadmap.read'], group: 'secondary' },
  { id: 'search', href: '/search', labelKey: 'nav.search', surface: 'tenant', anyOfPermissions: ['search.use'], dockRank: 4, group: 'primary' },
  { id: 'admin', href: '/admin', labelKey: 'nav.admin', surface: 'tenant', anyOfPermissions: TENANT_ADMIN_PERMISSIONS, group: 'admin' },
  { id: 'console-queue', href: '/console/queue', labelKey: 'nav.console.queue', surface: 'console', anyOfPermissions: ['proposals.review'], dockRank: 1, group: 'primary' },
  { id: 'console-vocabularies', href: '/console/vocabularies', labelKey: 'nav.console.vocabularies', surface: 'console', anyOfPermissions: ['library_vocab.manage'], dockRank: 2, group: 'primary' },
  { id: 'console-sources', href: '/console/sources', labelKey: 'nav.console.sources', surface: 'console', anyOfPermissions: ['sources.manage'], dockRank: 3, group: 'primary' },
];

export function unlocks(anyOfPermissions: readonly string[], permissions: readonly string[]): boolean {
  if (anyOfPermissions.length === 0) return true;
  return anyOfPermissions.some((permission) => permissions.includes(permission));
}

export function visibleDestinations(surface: Surface, permissions: readonly string[]): Destination[] {
  return destinations.filter((d) => d.surface === surface && unlocks(d.anyOfPermissions, permissions));
}

export function dockDestinations(surface: Surface, permissions: readonly string[]): Destination[] {
  return visibleDestinations(surface, permissions)
    .filter((d) => d.dockRank !== undefined)
    .sort((a, b) => (a.dockRank ?? 0) - (b.dockRank ?? 0));
}

export function isCurrent(destination: Destination, pathname: string): boolean {
  if (destination.href === '/') return pathname === '/';
  return pathname === destination.href || pathname.startsWith(`${destination.href}/`);
}

export function findDestination(id: string): Destination | undefined {
  return destinations.find((d) => d.id === id);
}
