import type { PresentedPill } from '@/features/shared/presentation-types';
import { byOrder } from '@/features/shared/presentation-types';
import type { AccessEntry, AccessKey, OrgUnit, Product } from '@/features/agent-access/types';
import type { MessageKey, Translate } from '@/shared/i18n';

// What the agent access screens read from a record's facts
// (design/screens/admin-agent-access.html; design/system/pills-and-labels.md,
// "Agent access"). Every tone comes from a kind or a slot, never a person.

const ORDER = { state: 0, reads: 1, kind: 0, credentialState: 1, scopes: 2 } as const;

/**
 * An entry's state (Active positive, Revoked information) and what it reads
 * now: on only when the organisation's switch and the entry's own toggle are
 * both on. `orgReach` is null when the organisation's half cannot be read
 * (it needs security.manage), and then no reach pill is drawn rather than a guess.
 */
export function presentEntry(entry: Pick<AccessEntry, 'active' | 'tenantReach'>, orgReach: boolean | null, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    entry.active ? { key: 'state:active', label: t('agentAccess.pill.active'), tone: 'positive', order: ORDER.state } : { key: 'state:revoked', label: t('agentAccess.pill.revoked'), tone: 'information', order: ORDER.state },
  ];
  if (entry.active && orgReach !== null) {
    pills.push(
      orgReach && entry.tenantReach
        ? { key: 'reads:register', label: t('agentAccess.pill.readsRegister'), tone: 'notice', order: ORDER.reads }
        : { key: 'reads:library', label: t('agentAccess.pill.libraryOnly'), tone: 'information', order: ORDER.reads },
    );
  }
  return pills.sort(byOrder);
}

/** Departments and products on an entry: the scope facets' slot, brand. */
export function presentUnits(units: readonly { id: string; name: string }[], slot: 'department' | 'product'): PresentedPill[] {
  return units.map((unit, i) => ({ key: `${slot}:${unit.id}`, label: unit.name, tone: 'brand', order: i }));
}

const KIND_KEY: Record<AccessKey['kind'], MessageKey> = { service: 'agentAccess.pill.service', personal: 'agentAccess.pill.personal' };

/** A scope key read as words: `library:read` is "library read". */
export function scopeLabel(scope: string): string {
  return scope.replace(/[._:-]/g, ' ');
}

/** A credential's kind, then Revoked or Expired from its facts, then its scopes. */
export function presentCredential(key: AccessKey, t: Translate, now: Date): PresentedPill[] {
  const pills: PresentedPill[] = [{ key: `kind:${key.kind}`, label: t(KIND_KEY[key.kind]), tone: 'information', order: ORDER.kind }];
  if (key.revokedAt !== null && key.revokedAt !== undefined) {
    pills.push({ key: 'state:revoked', label: t('agentAccess.pill.revoked'), tone: 'information', order: ORDER.credentialState });
  } else if (isExpired(key, now)) {
    pills.push({ key: 'state:expired', label: t('agentAccess.pill.expired'), tone: 'warning', order: ORDER.credentialState });
  }
  key.scopes.forEach((scope, i) => pills.push({ key: `scope:${scope}`, label: scopeLabel(scope), tone: 'information', order: ORDER.scopes + i }));
  return pills.sort(byOrder);
}

export function isExpired(key: Pick<AccessKey, 'expiresAt'>, now: Date): boolean {
  return key.expiresAt !== null && key.expiresAt !== undefined && new Date(key.expiresAt).getTime() <= now.getTime();
}

/** A credential that still works: neither revoked nor expired. */
export function isLive(key: AccessKey, now: Date): boolean {
  return (key.revokedAt === null || key.revokedAt === undefined) && !isExpired(key, now);
}

/** The service keys and personal tokens under an entry, and the latest use of any. */
export function credentialCounts(keys: readonly AccessKey[]): { keys: number; tokens: number; lastUsedAt: string | null } {
  let lastUsedAt: string | null = null;
  for (const key of keys) {
    if (key.lastUsedAt !== null && key.lastUsedAt !== undefined && (lastUsedAt === null || key.lastUsedAt > lastUsedAt)) lastUsedAt = key.lastUsedAt;
  }
  return { keys: keys.filter((k) => k.kind === 'service').length, tokens: keys.filter((k) => k.kind === 'personal').length, lastUsedAt };
}

/** The ids of a unit and every active unit below it; a deactivated unit cuts its branch. */
function branch(unitId: string, units: readonly OrgUnit[]): Set<string> {
  const ids = new Set([unitId]);
  for (let grew = true; grew; ) {
    grew = false;
    for (const unit of units) {
      if (unit.active && unit.parentId !== null && unit.parentId !== undefined && ids.has(unit.parentId) && !ids.has(unit.id)) {
        ids.add(unit.id);
        grew = true;
      }
    }
  }
  return ids;
}

/** The live products a department brings: its own and those of every active unit below it. */
export function productsUnder(unitId: string, units: readonly OrgUnit[], products: readonly Product[]): Product[] {
  const ids = branch(unitId, units);
  return products.filter((p) => p.status !== 'retired' && p.orgUnitId !== null && p.orgUnitId !== undefined && ids.has(p.orgUnitId));
}

/**
 * Whether a narrowing derives no term at all, so the entry would read nothing
 * (the server's `entry_scope_empty`). Naming nothing narrows nothing.
 */
export function readsNothing(selection: { departmentIds: readonly string[]; productIds: readonly string[] }, units: readonly OrgUnit[], products: readonly Product[]): boolean {
  if (selection.departmentIds.length === 0 && selection.productIds.length === 0) return false;
  const named = [...selection.departmentIds.flatMap((id) => productsUnder(id, units, products)), ...products.filter((p) => p.status !== 'retired' && selection.productIds.includes(p.id))];
  return named.every((p) => p.terms.length === 0);
}

/** An operation id or tool name read as words: `listObligations` is "List obligations". */
export function toolName(tool: string): string {
  const words = tool.replace(/[_-]+/g, ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase().trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** How many footprint terms a call read in. */
export function scopeTermCount(terms: Readonly<Record<string, readonly string[]>>): number {
  return Object.values(terms).reduce((sum, keys) => sum + keys.length, 0);
}

// Every refusal the entry and key routes answer, read from its code, never its detail.
const REFUSAL_KEY = {
  stale_write: 'agentAccess.refusal.stale',
  invalid_transition: 'agentAccess.refusal.invalidTransition',
  unknown_key: 'agentAccess.refusal.unknownKey',
  name_required: 'agentAccess.refusal.nameRequired',
  purpose_required: 'agentAccess.refusal.purposeRequired',
  expiry_in_past: 'agentAccess.refusal.expiryInPast',
  expiry_too_late: 'agentAccess.refusal.expiryTooLate',
  step_up_required: 'problem.stepUpCancelled',
} as const satisfies Record<string, MessageKey>;

/** The sentence each refusal code renders in place, for `ProblemAlert`'s `codes`. */
export function refusals(t: Translate): Record<string, string> {
  return Object.fromEntries(Object.entries(REFUSAL_KEY).map(([code, key]) => [code, t(key)]));
}
