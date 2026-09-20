import { describe, expect, it } from 'vitest';

import { t } from '@/shared/i18n';

import { presentTenant, tenantStatusTone } from './tenants-presentation';

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
});
