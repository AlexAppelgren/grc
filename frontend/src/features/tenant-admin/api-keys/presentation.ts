import type { ApiKey } from '@/features/tenant-admin/types';
import type { Translate } from '@/shared/i18n';

// Who a credential on the API keys list reads as (design/screens/admin-api-keys.html,
// ACC-03): an integration, an agent access entry, or a person, within the entry
// the token names. Its pills are an entry credential's (agent-access presentation).
export function readsAs(key: Pick<ApiKey, 'agentAccess' | 'person'>, t: Translate): string {
  if (key.person !== null) {
    return key.agentAccess === null ? t('admin.credentials.actsAs', { person: key.person.name }) : t('admin.credentials.actsAsWithin', { person: key.person.name, entry: key.agentAccess.name });
  }
  return key.agentAccess === null ? t('admin.credentials.forIntegration') : t('admin.credentials.readsAs', { entry: key.agentAccess.name });
}
