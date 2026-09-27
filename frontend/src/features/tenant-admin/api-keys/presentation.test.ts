import { describe, expect, it } from 'vitest';

import { readsAs } from '@/features/tenant-admin/api-keys/presentation';
import type { Translate } from '@/shared/i18n';

// Who each credential on the API keys list reads as (admin-api-keys.html, ACC-03).

const t = ((key: string, values?: Record<string, string>) => `${key} ${JSON.stringify(values ?? {})}`) as Translate;
const entry = { id: 'e1', name: 'Trading platform coding agent' };
const person = { id: 'u1', name: 'Anna Berg' };

describe('readsAs', () => {
  it('names an integration key, an entry key, a token and a token within an entry', () => {
    expect(readsAs({ agentAccess: null, person: null }, t)).toBe('admin.credentials.forIntegration {}');
    expect(readsAs({ agentAccess: entry, person: null }, t)).toBe('admin.credentials.readsAs {"entry":"Trading platform coding agent"}');
    expect(readsAs({ agentAccess: null, person }, t)).toBe('admin.credentials.actsAs {"person":"Anna Berg"}');
    expect(readsAs({ agentAccess: entry, person }, t)).toBe('admin.credentials.actsAsWithin {"person":"Anna Berg","entry":"Trading platform coding agent"}');
  });
});
