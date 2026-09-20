'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { useT } from '@/shared/i18n/LocaleProvider';

// Change facts (ADM-02, WAT-03): the head and the empty state, so the rail
// entry has somewhere to land. The list that reads GET /console/changes is
// c5-fe-console-change-facts and the confirmation view follows it; both
// replace this file.
export default function ConsoleChangeFactsPage() {
  const t = useT();
  return (
    <AdminGate id="console-change-facts">
      <PageHead title={t('console.changeFacts.title')} lede={t('console.changeFacts.lede')} />
      <EmptyState title={t('console.changeFacts.emptyTitle')} body={t('console.changeFacts.emptyBody')} />
    </AdminGate>
  );
}
