import type { PillTone } from '@/components/ui/pill-tones';
import type { ConsoleTenant, TenantStatus } from '@/features/console-tenants/types';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { MessageKey, Translate } from '@/shared/i18n';

// The pill of a tenant row in the platform console (ADM-02). Status is a kind
// without a severity scale, so the tone comes from the kind the same way an
// invitation's does (members-presentation.ts): the live state reads positive
// and the ended one is a neutral fact. The row carries nothing from inside
// the bank, so there is nothing else to present.

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
