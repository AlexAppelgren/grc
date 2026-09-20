import type { MessageKey } from '@/shared/i18n';

// The one typed navigation registry (playbook 6.2). Pure TypeScript, no
// React: sidebar, tab bar, More sheet, command palette, the client gate and the
// Playwright role-matrix spec all derive from it. Nothing here checks a role
// name: a destination is visible iff the user's permission list unlocks it.
// The server's structured 403 remains the enforcer.

export type Surface = 'tenant' | 'console';
export type NavGroup = 'primary' | 'secondary' | 'admin' | 'account';

export interface Destination {
  id: string;
  href: string;
  labelKey: MessageKey;
  /** A tab's label when `labelKey` is longer than one word; the rail and the More sheet keep `labelKey`. */
  shortLabelKey?: MessageKey;
  surface: Surface;
  /** Empty means any signed-in user of that surface. Permission names are PRD section 6. */
  anyOfPermissions: readonly string[];
  /** Present on destinations that sit in the tab bar below 1024 px, lowest first. */
  dockRank?: number;
  group: NavGroup;
  /**
   * A child sits under its parent's screen (the Admin index, the who panel's
   * account links) and never in the rail or the dock. `account` is a virtual
   * parent: the who panel lists its children.
   */
  parent?: string;
}

export const ACCOUNT_PARENT = 'account';

const TENANT_ADMIN_PERMISSIONS = [
  'members.manage',
  'roles.manage',
  'security.manage',
  'vocab.manage',
  'workflow.manage',
  'agents.manage',
  'integrations.manage',
  // A compliance officer may hold nothing but these two and still needs the
  // way in to the footprint screen (FP-01, FP-02).
  'footprint.request',
  'footprint.approve',
  // Every system role holds audit.read (PRD section 6), so every member
  // reaches Admin for the audit log and the organisation profile (AUD-01).
  'audit.read',
] as const;

// Seeing the footprint is enough to request a change or to approve one; the
// chips are editable only with `footprint.request`, and the screen says so.
const FOOTPRINT_PERMISSIONS = ['footprint.request', 'footprint.approve'] as const;

export const destinations: readonly Destination[] = [
  { id: 'today', href: '/', labelKey: 'nav.today', surface: 'tenant', anyOfPermissions: [], dockRank: 1, group: 'primary' },
  { id: 'watch', href: '/watch', labelKey: 'nav.watch', surface: 'tenant', anyOfPermissions: ['watch.read'], dockRank: 2, group: 'primary' },
  { id: 'inventory', href: '/inventory', labelKey: 'nav.inventory', surface: 'tenant', anyOfPermissions: ['library.read'], dockRank: 3, group: 'primary' },
  { id: 'roadmap', href: '/roadmap', labelKey: 'nav.roadmap', surface: 'tenant', anyOfPermissions: ['roadmap.read'], group: 'secondary' },
  { id: 'search', href: '/search', labelKey: 'nav.search', shortLabelKey: 'nav.search.short', surface: 'tenant', anyOfPermissions: ['search.use'], dockRank: 4, group: 'primary' },
  { id: 'admin', href: '/admin', labelKey: 'nav.admin', surface: 'tenant', anyOfPermissions: TENANT_ADMIN_PERMISSIONS, group: 'admin' },
  // Admin sections (ADM-03): each gated by its own permission. The
  // organisation profile is readable by any member; the server refuses edits.
  { id: 'admin-organisation', href: '/admin/organisation', labelKey: 'nav.admin.organisation', surface: 'tenant', anyOfPermissions: [], group: 'admin', parent: 'admin' },
  { id: 'admin-members', href: '/admin/members', labelKey: 'nav.admin.members', surface: 'tenant', anyOfPermissions: ['members.manage'], group: 'admin', parent: 'admin' },
  { id: 'admin-roles', href: '/admin/roles', labelKey: 'nav.admin.roles', surface: 'tenant', anyOfPermissions: ['roles.manage'], group: 'admin', parent: 'admin' },
  { id: 'admin-vocabularies', href: '/admin/vocabularies', labelKey: 'nav.admin.vocabularies', surface: 'tenant', anyOfPermissions: ['vocab.manage'], group: 'admin', parent: 'admin' },
  { id: 'admin-footprint', href: '/admin/footprint', labelKey: 'nav.admin.footprint', surface: 'tenant', anyOfPermissions: FOOTPRINT_PERMISSIONS, group: 'admin', parent: 'admin' },
  { id: 'admin-api-keys', href: '/admin/api-keys', labelKey: 'nav.admin.apiKeys', surface: 'tenant', anyOfPermissions: ['integrations.manage'], group: 'admin', parent: 'admin' },
  { id: 'admin-security-log', href: '/admin/security-log', labelKey: 'nav.admin.securityLog', surface: 'tenant', anyOfPermissions: ['security.manage'], group: 'admin', parent: 'admin' },
  { id: 'admin-audit-log', href: '/admin/audit-log', labelKey: 'nav.admin.auditLog', surface: 'tenant', anyOfPermissions: ['audit.read'], group: 'admin', parent: 'admin' },
  // Account: any signed-in person, from the who panel.
  { id: 'me-passkeys', href: '/me/passkeys', labelKey: 'nav.me.passkeys', surface: 'tenant', anyOfPermissions: [], group: 'account', parent: ACCOUNT_PARENT },
  { id: 'me-sessions', href: '/me/sessions', labelKey: 'nav.me.sessions', surface: 'tenant', anyOfPermissions: [], group: 'account', parent: ACCOUNT_PARENT },
  // The platform console (ADM-02): a destination joins with its page, so none
  // renders "coming soon". The queue takes rank 1 with its page (chunk 4),
  // sources with theirs (chunk 5).
  { id: 'console-vocabularies', href: '/console/vocabularies', labelKey: 'nav.console.vocabularies', surface: 'console', anyOfPermissions: ['library_vocab.manage'], dockRank: 2, group: 'primary' },
  // Chunk 5. A library editor settles a change's facts and reads the source
  // registry; the platform admin holds the agent keys. Change facts and
  // Agent keys take no dock rank, so the phone's tab bar keeps the shape the
  // console card draws and they sit in More.
  { id: 'console-change-facts', href: '/console/change-facts', labelKey: 'nav.console.changeFacts', surface: 'console', anyOfPermissions: ['proposals.review'], group: 'primary' },
  { id: 'console-sources', href: '/console/sources', labelKey: 'nav.console.sources', surface: 'console', anyOfPermissions: ['sources.manage'], dockRank: 4, group: 'primary' },
  { id: 'console-tenants', href: '/console/tenants', labelKey: 'nav.console.tenants', surface: 'console', anyOfPermissions: ['tenants.manage'], dockRank: 3, group: 'primary' },
  { id: 'console-agent-keys', href: '/console/agent-keys', labelKey: 'nav.console.agentKeys', surface: 'console', anyOfPermissions: ['agent_definitions.manage'], group: 'primary' },
];

/** The console's landing: it sends each person on to the first console destination they may open. */
export const CONSOLE_HOME = '/console';

/**
 * A person's own surface, read from the principal and never from a role name:
 * platform staff sign in without a tenant and work in the console; everyone
 * else works in their organisation. Before a session exists it is the
 * tenant's, whose gate sends the visitor to sign in.
 */
export function surfaceOf(me: { tenant: object | null } | null): Surface {
  return me !== null && me.tenant === null ? 'console' : 'tenant';
}

/** Where sign-in and the logo take a person: Today, or the console. */
export function homeOf(me: { tenant: object | null } | null): string {
  return surfaceOf(me) === 'console' ? CONSOLE_HOME : '/';
}

export function unlocks(anyOfPermissions: readonly string[], permissions: readonly string[]): boolean {
  if (anyOfPermissions.length === 0) return true;
  return anyOfPermissions.some((permission) => permissions.includes(permission));
}

/** Top-level destinations of a surface the permission list unlocks: the rail and the More menu. */
export function visibleDestinations(surface: Surface, permissions: readonly string[]): Destination[] {
  return destinations.filter((d) => d.surface === surface && d.parent === undefined && unlocks(d.anyOfPermissions, permissions));
}

/** Children of a destination (or of the virtual `account` parent) the permission list unlocks. */
export function childDestinations(parent: string, permissions: readonly string[]): Destination[] {
  return destinations.filter((d) => d.parent === parent && unlocks(d.anyOfPermissions, permissions));
}

export function dockDestinations(surface: Surface, permissions: readonly string[]): Destination[] {
  return visibleDestinations(surface, permissions)
    .filter((d) => d.dockRank !== undefined)
    .sort((a, b) => (a.dockRank ?? 0) - (b.dockRank ?? 0));
}

/** The visible destinations that are not tabs: the More sheet lists them above the account. */
export function moreDestinations(surface: Surface, permissions: readonly string[]): Destination[] {
  const dock = dockDestinations(surface, permissions);
  return visibleDestinations(surface, permissions).filter((d) => !dock.includes(d));
}

/** Whether the current page is reached through More: a More destination (or one of its children) or an account page. */
export function isInMore(surface: Surface, permissions: readonly string[], pathname: string): boolean {
  return [...moreDestinations(surface, permissions), ...childDestinations(ACCOUNT_PARENT, permissions)].some((d) => isCurrent(d, pathname));
}

export function isCurrent(destination: Destination, pathname: string): boolean {
  if (destination.href === '/') return pathname === '/';
  return pathname === destination.href || pathname.startsWith(`${destination.href}/`);
}

export function findDestination(id: string): Destination | undefined {
  return destinations.find((d) => d.id === id);
}
