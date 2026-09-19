'use client';

import Link from 'next/link';
import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { TabPanel, Tabs } from '@/components/ui/Tabs';
import { useVocabularies } from '@/features/vocabularies/hooks';
import { listLabel, presentListSummary } from '@/features/vocabularies/vocabulary-presentation';
import type { VocabularyListSummary } from '@/features/vocabularies/types';
import { useT } from '@/shared/i18n/LocaleProvider';

// /admin/vocabularies: the list of lists
// (design/screens/admin-vocabularies.html; VOC-01, VOC-02, VOC-07, ADM-03).
// One generic screen renders every list. A row's leading pills are the real
// pills of that list, so an admin sees the tone before opening it. The tenant
// group is editable; the shared library group is read here and changed only
// through a proposal.

const OURS = 'ours';
const LIBRARY = 'library';

// Roles are a vocabulary, but they are managed on their own screen because a
// role carries permissions (ID-09). The row links there instead.
const ROLES_LIST = 'tenant_role';

function href(list: string): string {
  return list === ROLES_LIST ? '/admin/roles' : `/admin/vocabularies/${encodeURIComponent(list)}`;
}

function ListRow({ summary }: { summary: VocabularyListSummary }) {
  const t = useT();
  return (
    <Link
      href={href(summary.list)}
      className="block rounded-card border border-line bg-surface px-4 py-3 no-underline hover:hover-fill"
      data-vocabulary-list={summary.list}
      data-vocabulary-tier={summary.tier}
    >
      <PillRow pills={presentListSummary(summary, t)} />
      <h3 className="mt-2 mb-1 font-semibold">{listLabel(summary.list, t)}</h3>
      <Meta>
        <span>{t('admin.vocabularies.active', { count: summary.count })}</span>
        {summary.retiredCount > 0 ? <span>{t('admin.vocabularies.retiredCount', { count: summary.retiredCount })}</span> : null}
        {summary.list === ROLES_LIST ? <span>{t('admin.vocabularies.managedUnderRoles')}</span> : null}
      </Meta>
    </Link>
  );
}

function ListGroup({ id, summaries, lede }: { id: string; summaries: readonly VocabularyListSummary[]; lede?: string }) {
  const t = useT();
  if (summaries.length === 0) {
    return (
      <TabPanel id={id}>
        <EmptyState title={t('admin.vocabularies.emptyTitle')} body={t('admin.vocabularies.emptyBody')} />
      </TabPanel>
    );
  }
  return (
    <TabPanel id={id}>
      {lede === undefined ? null : <p className="mb-3.5 max-w-[70ch] text-muted">{lede}</p>}
      <Rows data-vocabulary-lists={id}>
        {summaries.map((summary) => (
          <ListRow key={summary.list} summary={summary} />
        ))}
      </Rows>
    </TabPanel>
  );
}

export function VocabulariesScreen() {
  const t = useT();
  const lists = useVocabularies();
  const [tab, setTab] = useState(OURS);

  if (lists.isPending) return <LoadingState rows={3} />;
  if (lists.isError) return <ErrorState title={t('admin.vocabularies.errorTitle')} onRetry={() => void lists.refetch()} />;

  const ours = lists.data.filter((summary) => summary.tier === 'tenant');
  const library = lists.data.filter((summary) => summary.tier === 'library');

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.vocabularies.title')} lede={t('admin.vocabularies.lede')} />
      <Tabs
        current={tab}
        onSelect={setTab}
        tabs={[
          { id: OURS, label: t('admin.vocabularies.tabOurs') },
          { id: LIBRARY, label: t('admin.vocabularies.tabLibrary') },
        ]}
      />
      {tab === OURS ? <ListGroup id={OURS} summaries={ours} /> : <ListGroup id={LIBRARY} summaries={library} lede={t('admin.vocabularies.libraryLede')} />}
    </>
  );
}
