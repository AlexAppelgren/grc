'use client';

import { Panel } from '@/components/ui/Panel';
import { useT } from '@/shared/i18n/LocaleProvider';

// The teams section of the organisation screen (TEN-03, TEN-S8): its mount
// point. The teams and who is in them land here in their own package.
export function TeamsSection() {
  const t = useT();
  return (
    <Panel title={t('admin.org.teams.title')} data-org-section="teams">
      <p className="text-muted">{t('admin.org.teams.lede')}</p>
    </Panel>
  );
}
