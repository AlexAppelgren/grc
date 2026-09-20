'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { useT } from '@/shared/i18n/LocaleProvider';

// Agent keys (ADM-02, ID-10): the head and the empty state, so the rail
// entry has somewhere to land. The list, the passkey step-up and the
// shown-once secret are c5-fe-console-agent-keys, which replaces this file.
export default function ConsoleAgentKeysPage() {
  const t = useT();
  return (
    <AdminGate id="console-agent-keys">
      <PageHead title={t('console.agentKeys.title')} lede={t('console.agentKeys.lede')} />
      <EmptyState title={t('console.agentKeys.emptyTitle')} body={t('console.agentKeys.emptyBody')} />
    </AdminGate>
  );
}
