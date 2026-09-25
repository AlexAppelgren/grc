'use client';

import { Panel } from '@/components/ui/Panel';
import { useT } from '@/shared/i18n/LocaleProvider';

// The departments section of the organisation screen (TEN-02, TEN-S8): its
// mount point. The departments with their heads land here in their own package.
export function DepartmentsSection() {
  const t = useT();
  return (
    <Panel title={t('admin.org.departments.title')} data-org-section="departments">
      <p className="text-muted">{t('admin.org.departments.lede')}</p>
    </Panel>
  );
}
