'use client';

import { useSyncExternalStore } from 'react';

import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { formatLongDate } from '@/shared/utils/format';

// The Today shell (HOM-01 in Phase 1). Phase 0 renders the head and the
// empty state; no API call is made yet, so the smoke journey needs no backend.

function subscribeNever(): () => void {
  return () => undefined;
}

// The visitor's local calendar day as YYYY-MM-DD. Read through
// useSyncExternalStore so the server renders no kicker and the client fills
// it in after hydration, keeping the markup identical across timezones.
function localDayKey(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function serverDayKey(): null {
  return null;
}

export function TodayScreen() {
  const t = useT();
  const locale = useLocale();
  const day = useSyncExternalStore(subscribeNever, localDayKey, serverDayKey);
  const kicker = day === null ? undefined : formatLongDate(day, { locale, timeZone: 'UTC' });

  return (
    <>
      <PageHead kicker={kicker} title={t('today.title')} />
      <EmptyState
        title={t('today.empty.title')}
        body={t('today.empty.body')}
        action={{ label: t('today.empty.action'), href: '/admin' }}
      />
    </>
  );
}
