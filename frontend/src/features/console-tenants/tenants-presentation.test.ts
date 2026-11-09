import { describe, expect, it } from 'vitest';

import { t } from '@/shared/i18n';

import { canResendFirstAdministrator, presentFirstAdministrator, presentTenant, tenantStatusTone } from './tenants-presentation';

// Tone comes from the kind, never from a person, and the label comes from the
// catalog (playbook 6.7).

describe('tenant presentation', () => {
  it('names the live state and the ended one, each in its own tone', () => {
    expect(presentTenant({ status: 'active' }, t)).toEqual([{ key: 'status:active', label: 'Active', tone: 'positive', order: 50 }]);
    expect(presentTenant({ status: 'deactivated' }, t)).toEqual([{ key: 'status:deactivated', label: 'Deactivated', tone: 'information', order: 50 }]);
  });

  it('maps every tenant status to one of the six tones', () => {
    expect(Object.keys(tenantStatusTone).sort()).toEqual(['active', 'deactivated']);
  });

  it('presents the first administrator in the invitation tones, and offers a resend only while nobody joined', () => {
    expect(presentFirstAdministrator({ status: 'pending' }, t)).toEqual([{ key: 'firstAdmin:pending', label: 'Invitation pending', tone: 'warning', order: 50 }]);
    expect(presentFirstAdministrator({ status: 'accepted' }, t)).toEqual([{ key: 'firstAdmin:accepted', label: 'Joined', tone: 'positive', order: 50 }]);
    expect(presentFirstAdministrator({ status: 'expired' }, t)[0]?.tone).toBe('information');
    expect(presentFirstAdministrator({ status: 'revoked' }, t)[0]?.tone).toBe('information');
    expect(['pending', 'expired', 'accepted', 'revoked'].filter((status) => canResendFirstAdministrator({ status: status as 'pending' }))).toEqual(['pending', 'expired']);
  });
});
