import type { PillTone } from '@/components/ui/pill-tones';
import type { ApiKey, Invitation, InvitationStatus, LoginEvent, Member, MemberStatus, TenantRole } from '@/features/tenant-admin/types';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import type { MessageKey, Translate } from '@/shared/i18n';

// Pills for the tenant admin screens (design/screens/admin-*.html). Role
// labels come from the rows, never from code; tone comes from the slot
// (roles, scopes and permissions are neutral facts) or from the kind.

const ORDER = { kind: 5, roles: 10, scopes: 10, status: 50 } as const;

export type MemberFacts = Pick<Member, 'status' | 'roles'>;
export type InvitationFacts = Pick<Invitation, 'kind' | 'roles' | 'status'>;
// The roles list returns active roles only, so a role row has no retired state.
export type RoleFacts = Pick<TenantRole, 'isSystem'>;
export type ApiKeyFacts = Pick<ApiKey, 'scopes' | 'revokedAt' | 'expiresAt'>;
export type LoginEventFacts = Pick<LoginEvent, 'event' | 'success'>;

function rolePills(roles: readonly { key: string; label: string }[]): PresentedPill[] {
  return roles.map((role, i) => ({ key: `role:${role.key}`, label: role.label, tone: 'information' as const, order: ORDER.roles + i }));
}

// Member status is a kind: invited needs attention, deactivated is a fact,
// active shows nothing.
export const memberStatusTone: Record<MemberStatus, PillTone | null> = {
  invited: 'warning',
  active: null,
  deactivated: 'information',
};

export function presentMember(member: MemberFacts, t: Translate): PresentedPill[] {
  const pills = rolePills(member.roles);
  const tone = memberStatusTone[member.status];
  if (tone !== null && tone !== undefined) {
    const label = member.status === 'invited' ? t('admin.members.awaitingEnrolment') : t('admin.members.deactivated');
    pills.push({ key: `status:${member.status}`, label, tone, order: ORDER.status });
  }
  return pills.sort(byOrder);
}

// Invitation status is a kind the server computes: pending needs attention,
// accepted is good, revoked and expired are facts.
export const invitationStatusTone: Record<InvitationStatus, PillTone> = {
  pending: 'warning',
  accepted: 'positive',
  revoked: 'information',
  expired: 'information',
};

const invitationStatusLabel: Record<InvitationStatus, MessageKey> = {
  pending: 'admin.members.awaitingEnrolment',
  accepted: 'admin.members.accepted',
  revoked: 'admin.members.revokedPill',
  expired: 'admin.members.expiredPill',
};

export function presentInvitation(invitation: InvitationFacts, t: Translate): PresentedPill[] {
  const pills = rolePills(invitation.roles);
  if (invitation.kind === 'reenrolment') {
    pills.push({ key: 'kind:reenrolment', label: t('admin.members.reenrolment'), tone: 'information', order: ORDER.kind });
  }
  const tone = invitationStatusTone[invitation.status];
  const labelKey = invitationStatusLabel[invitation.status];
  if (tone !== undefined && labelKey !== undefined) {
    pills.push({ key: `status:${invitation.status}`, label: t(labelKey), tone, order: ORDER.status });
  }
  return pills.sort(byOrder);
}

export function presentRole(role: RoleFacts, t: Translate): PresentedPill[] {
  return role.isSystem ? [{ key: 'role:system', label: t('admin.roles.systemRole'), tone: 'information', order: ORDER.kind }] : [];
}

// `cases.signoff` reads "cases signoff", `search:read` reads "search read":
// the grant or scope name in plain words, never a role name.
export function humaniseKey(key: string): string {
  return key.replace(/[._:-]/g, ' ');
}

export function presentPermissions(permissions: readonly string[]): PresentedPill[] {
  return permissions.map((permission, i) => ({ key: `permission:${permission}`, label: humaniseKey(permission), tone: 'information' as const, order: ORDER.roles + i }));
}

export function presentApiKey(key: ApiKeyFacts, t: Translate, now: Date): PresentedPill[] {
  const pills: PresentedPill[] = key.scopes.map((scope, i) => ({ key: `scope:${scope}`, label: humaniseKey(scope), tone: 'information' as const, order: ORDER.scopes + i }));
  if (key.revokedAt !== null) {
    pills.push({ key: 'status:revoked', label: t('admin.apiKeys.revoked'), tone: 'information', order: ORDER.kind });
  } else if (key.expiresAt !== null && new Date(key.expiresAt).getTime() < now.getTime()) {
    pills.push({ key: 'status:expired', label: t('admin.apiKeys.expired'), tone: 'warning', order: ORDER.kind });
  }
  return pills.sort(byOrder);
}

// Login event kinds (identity app.md, ID-11). Success is positive, a failure
// or a lock negative, a refusal warning, anything else a neutral fact.
export const loginEventTone: Record<string, PillTone> = {
  code_sent: 'information',
  code_refused_enrolled: 'warning',
  code_failed: 'negative',
  code_locked: 'negative',
  enrolled: 'positive',
  signin: 'positive',
  signin_failed: 'negative',
  step_up: 'information',
  step_up_failed: 'negative',
  refresh_replay: 'negative',
  session_revoked: 'information',
  reenrolment_issued: 'information',
  key_used: 'information',
  key_revoked: 'information',
};

const loginEventLabel: Record<string, MessageKey> = {
  code_sent: 'admin.securityLog.event.code_sent',
  code_refused_enrolled: 'admin.securityLog.event.code_refused_enrolled',
  code_failed: 'admin.securityLog.event.code_failed',
  code_locked: 'admin.securityLog.event.code_locked',
  enrolled: 'admin.securityLog.event.enrolled',
  signin: 'admin.securityLog.event.signin',
  signin_failed: 'admin.securityLog.event.signin_failed',
  step_up: 'admin.securityLog.event.step_up',
  step_up_failed: 'admin.securityLog.event.step_up_failed',
  refresh_replay: 'admin.securityLog.event.refresh_replay',
  session_revoked: 'admin.securityLog.event.session_revoked',
  reenrolment_issued: 'admin.securityLog.event.reenrolment_issued',
  key_used: 'admin.securityLog.event.key_used',
  key_revoked: 'admin.securityLog.event.key_revoked',
};

const loginMethodLabel: Record<string, MessageKey> = {
  email_code: 'admin.securityLog.method.email_code',
  passkey: 'admin.securityLog.method.passkey',
  api_key: 'admin.securityLog.method.api_key',
  oidc: 'admin.securityLog.method.oidc',
  saml: 'admin.securityLog.method.saml',
};

export function presentLoginEvent(event: LoginEventFacts, t: Translate): PresentedPill[] {
  const labelKey = loginEventLabel[event.event];
  const tone = loginEventTone[event.event] ?? (event.success ? 'information' : 'negative');
  const label = labelKey === undefined ? humaniseKey(event.event) : t(labelKey);
  return [{ key: `event:${event.event}`, label, tone, order: ORDER.kind }];
}

export function loginMethodText(method: string, t: Translate): string {
  const key = loginMethodLabel[method];
  return key === undefined ? humaniseKey(method) : t(key);
}
