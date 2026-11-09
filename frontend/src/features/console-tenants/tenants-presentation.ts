import type { PillTone } from '@/components/ui/pill-tones';
import { invitationStatusTone } from '@/features/tenant-admin/members-presentation';
import type { ConsoleTenant, FirstAdministrator, FirstAdministratorStatus, TenantStatus } from '@/features/console-tenants/types';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { MessageKey, Translate } from '@/shared/i18n';

// The pill of a tenant row in the platform console (ADM-02). Status is a kind
// without a severity scale, so the tone comes from the kind the same way an
// invitation's does (members-presentation.ts): the live state reads positive
// and the ended one is a neutral fact. The first administrator's invitation
// is the platform's own (D-123) and takes the invitation tones.

const STATUS_ORDER = 50;

export type TenantFacts = Pick<ConsoleTenant, 'status'>;

export const tenantStatusTone: Record<TenantStatus, PillTone> = {
  active: 'positive',
  deactivated: 'information',
};

const tenantStatusLabel: Record<TenantStatus, MessageKey> = {
  active: 'console.tenants.status.active',
  deactivated: 'console.tenants.status.deactivated',
};

export function presentTenant(tenant: TenantFacts, t: Translate): PresentedPill[] {
  return [{ key: `status:${tenant.status}`, label: t(tenantStatusLabel[tenant.status]), tone: tenantStatusTone[tenant.status], order: STATUS_ORDER }];
}

const firstAdministratorLabel: Record<FirstAdministratorStatus, MessageKey> = {
  pending: 'console.tenants.firstAdmin.pending',
  expired: 'console.tenants.firstAdmin.expired',
  accepted: 'console.tenants.firstAdmin.accepted',
  revoked: 'console.tenants.firstAdmin.revoked',
};

export function presentFirstAdministrator(invitation: Pick<FirstAdministrator, 'status'>, t: Translate): PresentedPill[] {
  return [
    {
      key: `firstAdmin:${invitation.status}`,
      label: t(firstAdministratorLabel[invitation.status]),
      tone: invitationStatusTone[invitation.status],
      order: STATUS_ORDER,
    },
  ];
}

/** Pending and expired invitations can be sent again; accepted and revoked cannot. */
export function canResendFirstAdministrator(invitation: Pick<FirstAdministrator, 'status'>): boolean {
  return invitation.status === 'pending' || invitation.status === 'expired';
}
