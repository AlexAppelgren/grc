import { isExpired, scopeLabel } from '@/features/agent-access/presentation';
import type { PersonalToken } from '@/features/personal-tokens/types';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import type { MessageKey, Translate } from '@/shared/i18n';

// What the tokens screen reads from a token's facts (design/screens/me-tokens.html;
// design/system/pills-and-labels.md). Every row here is personal, so no kind
// pill: Expired (warning) or Revoked (information) from its dates, then its
// scopes as information pills.

const ORDER = { state: 0, scopes: 1 } as const;

// The four read scopes a token may hold, in the design card's order, each with
// the permission of the member's own that backs it (the server refuses any
// other with unknown_key, and one not backed with scope_not_held).
export const TOKEN_SCOPES = ['library:read', 'search:read', 'upcoming:read', 'tenant:read'] as const;
export type TokenScope = (typeof TOKEN_SCOPES)[number];

export const SCOPE_PERMISSION: Record<TokenScope, string> = {
  'library:read': 'library.read',
  'search:read': 'search.use',
  'upcoming:read': 'roadmap.read',
  'tenant:read': 'register.read',
};

export const SCOPE_HINT: Record<TokenScope, MessageKey> = {
  'library:read': 'me.tokens.scope.library:read',
  'search:read': 'me.tokens.scope.search:read',
  'upcoming:read': 'me.tokens.scope.upcoming:read',
  'tenant:read': 'me.tokens.scope.tenant:read',
};

/** A token's state first, then what it may read. */
export function presentToken(token: Pick<PersonalToken, 'scopes' | 'revokedAt' | 'expiresAt'>, t: Translate, now: Date): PresentedPill[] {
  const pills: PresentedPill[] = token.scopes.map((scope, i) => ({ key: `scope:${scope}`, label: scopeLabel(scope), tone: 'information', order: ORDER.scopes + i }));
  if (token.revokedAt !== null) pills.push({ key: 'state:revoked', label: t('me.tokens.revoked'), tone: 'information', order: ORDER.state });
  else if (isExpired(token, now)) pills.push({ key: 'state:expired', label: t('me.tokens.expired'), tone: 'warning', order: ORDER.state });
  return pills.sort(byOrder);
}

/** A token that still works: neither revoked nor past its expiry. */
export function isLiveToken(token: Pick<PersonalToken, 'revokedAt' | 'expiresAt'>, now: Date): boolean {
  return token.revokedAt === null && !isExpired(token, now);
}

// Every refusal the mint route answers, read from its code, never its detail.
export function mintRefusals(t: Translate): Record<string, string> {
  return {
    step_up_required: t('problem.stepUpCancelled'),
    name_required: t('me.tokens.nameRequired'),
    scope_not_held: t('me.tokens.refusal.scopeNotHeld'),
    entry_required: t('me.tokens.entryRequired'),
    unknown_key: t('me.tokens.refusal.unknownKey'),
    expiry_in_past: t('me.tokens.refusal.expiryInPast'),
    expiry_too_late: t('me.tokens.refusal.expiryTooLate'),
  };
}
