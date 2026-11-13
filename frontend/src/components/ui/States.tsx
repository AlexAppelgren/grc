'use client';

import type { UseQueryResult } from '@tanstack/react-query';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { Button } from '@/components/ui/Button';
import { useDemoFrame } from '@/features/demo/use-demo-frame';
import { useT } from '@/shared/i18n/LocaleProvider';
import { NETWORK_PROBLEM_CODE, problemFrom } from '@/shared/utils/problem';
import { humaniseKey } from '@/shared/utils/format';

// The states every screen has (playbook 4.4, design/README.md): loading,
// error with retry, not found. The Restricted screen lives in
// require-permission.tsx and the empty state in EmptyState.tsx.

export function LoadingState({ rows = 2 }: { rows?: number }) {
  const t = useT();
  return (
    <div role="status" aria-busy="true" className="grid gap-2" data-loading-state="">
      <span className="sr-only">{t('common.loading')}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-[72px] rounded-card border border-line bg-subtle" aria-hidden="true" />
      ))}
    </div>
  );
}

// In the public page's demo every read is answered from its recordings, so a read
// that fails is one the demo has no recording for: no connection is at fault and a
// retry cannot change it. The not-found and error states say so in the demo's words.

export function ErrorState({ title, onRetry }: { title: string; onRetry?: () => void }) {
  const t = useT();
  const demo = useDemoFrame();
  return (
    <div role="alert" className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-error-state="">
      <h2 className="text-fg">{title}</h2>
      <p className="mx-auto mt-2 max-w-[60ch]">{demo ? t('public.demo.notRecorded') : t('common.errorBody')}</p>
      {onRetry !== undefined && !demo ? (
        <Button variant="outline" size="small" className="mt-4" onClick={onRetry}>
          {t('common.tryAgain')}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * One read's three states: loading while it is pending, the error with a
 * retry when it failed, and its data to `children` once it is there (an
 * empty answer included, which the caller words).
 */
export function QueryState<T>({ query, rows, errorTitle, children }: { query: UseQueryResult<T>; rows?: number; errorTitle: string; children: (data: T) => ReactNode }) {
  if (query.isPending) return <LoadingState rows={rows} />;
  if (query.isError) return <ErrorState title={errorTitle} onRetry={() => void query.refetch()} />;
  return <>{children(query.data)}</>;
}

// 404 for an addressed record that is not there, which includes another
// tenant's record (playbook 4.4): never the Restricted screen.
export function NotFoundScreen({ body, backHref = '/', backLabel }: { body?: string; backHref?: string; backLabel?: string }) {
  const t = useT();
  const demo = useDemoFrame();
  if (demo) {
    return (
      <section className="mx-auto max-w-[60ch] py-16 text-center" data-not-found="">
        <h1>{t('public.demo.notRecorded')}</h1>
        <Link href="/" className="mt-4 inline-block font-medium underline">
          {t('notFound.back')}
        </Link>
      </section>
    );
  }
  return (
    <section className="mx-auto max-w-[60ch] py-16 text-center" data-not-found="">
      <h1>{t('notFound.title')}</h1>
      <p className="mt-3 text-muted">{body ?? t('notFound.body')}</p>
      <Link href={backHref} className="mt-4 inline-block font-medium underline">
        {backLabel ?? t('notFound.back')}
      </Link>
    </section>
  );
}

/**
 * Renders an API error where it happened. The server's `detail` is shown as
 * written; a 403 adds the missing grant in plain words; a code the screen
 * knows (409 last_admin, last_passkey) gets the screen's own sentence.
 */
export function ProblemAlert({ error, codes = {}, className }: { error: unknown; codes?: Readonly<Record<string, string>>; className?: string }) {
  const t = useT();
  if (error === null || error === undefined) return null;
  const problem = problemFrom(error);
  const known = problem === null ? undefined : codes[problem.code];
  let text: string;
  if (problem === null) {
    text = error instanceof Error && error.message.length > 0 ? error.message : t('problem.generic');
  } else if (known !== undefined) {
    text = known;
  } else if (problem.code === NETWORK_PROBLEM_CODE) {
    text = t('problem.network');
  } else if (problem.status === 403) {
    const detail = problem.detail.length > 0 ? problem.detail : t('restricted.body');
    text = problem.requiredPermission === undefined ? detail : `${detail} ${t('restricted.needs', { permission: humaniseKey(problem.requiredPermission) })}`;
  } else {
    text = problem.detail.length > 0 ? problem.detail : t('problem.generic');
  }
  return (
    <p role="alert" className={className ?? 'mt-2.5 text-meta text-negative'} data-problem-code={problem?.code}>
      {text}
    </p>
  );
}

export function StatusLine({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'positive' }) {
  return (
    <p role="status" className={tone === 'positive' ? 'mt-2.5 text-meta text-positive' : 'mt-2.5 text-meta text-muted'}>
      {children}
    </p>
  );
}
