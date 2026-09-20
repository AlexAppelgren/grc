'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { useT } from '@/shared/i18n/LocaleProvider';

// Sources (ADM-02, WAT-01): the head and the empty state, so the rail entry
// has somewhere to land. The read-only registry and coverage log are
// c5-fe-console-sources, which replaces this file. The page stays read-only:
// adding, editing and "Check now" are later chunks.
export default function ConsoleSourcesPage() {
  const t = useT();
  return (
    <AdminGate id="console-sources">
      <PageHead title={t('console.sources.title')} lede={t('console.sources.lede')} />
      <EmptyState title={t('console.sources.emptyTitle')} body={t('console.sources.emptyBody')} />
    </AdminGate>
  );
}
