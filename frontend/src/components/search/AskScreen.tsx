'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { AskPanel } from '@/components/search/AskPanel';
import { TextInput } from '@/components/ui/Field';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';

// /ask (design/screens/tenant-ask.html; SRC-03, AC-SRC2, J-7, D-9x). Ask has
// its own page since search moved into the inventory's search bar. The "as of"
// date travels in the URL; the question is the bank's own words and never
// does, so "Search the inventory" opens the inventory without it.

export function AskScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const router = useRouter();
  const pathname = usePathname();
  const asOf = useSearchParams().get('asOf') ?? '';
  const hrefFor = (date: string) => (date === '' ? pathname : `${pathname}?${new URLSearchParams({ asOf: date }).toString()}`);

  return (
    <>
      <PageHead title={t('search.ask.title')} lede={t('search.ask.lede')} />
      <div className="mb-3 flex">
        <span className="ml-auto flex items-center gap-2 text-meta text-muted">
          <span aria-hidden="true">{t('search.filter.asOf')}</span>
          <TextInput type="date" className="w-auto" aria-label={t('search.filter.asOf')} value={asOf} onChange={(event) => router.replace(hrefFor(event.target.value))} />
        </span>
      </div>
      {asOf === '' ? null : (
        <Notice className="flex flex-wrap items-center gap-2">
          <span>{t('search.asOfBanner', { date: formatDate(asOf, ctx) })}</span>
          <Link href={pathname} className="font-medium underline">
            {t('search.asOfBanner.back')}
          </Link>
        </Notice>
      )}
      <AskPanel asOf={asOf} onSearchInstead={() => router.push('/inventory')} />
    </>
  );
}
