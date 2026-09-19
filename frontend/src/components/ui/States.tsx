'use client';

import Link from 'next/link';

import { Button } from '@/components/ui/Button';
import { useT } from '@/shared/i18n/LocaleProvider';
import { NETWORK_PROBLEM_CODE, problemFrom } from '@/shared/utils/problem';
import { humanisePermission } from '@/shared/navigation/require-permission';

// The states every screen has (playbook 4.4, design/README.md): loading,
// error with retry, not found. The Restricted screen lives in
// require-permission.tsx and the empty state in EmptyState.tsx.

export function LoadingState({ rows = 2 }: { rows?: number }) {
  const t = useT();
  return (
    <div role="status" aria-busy="true" className="grid gap-2.5" data-loading-state="">
      <span className="sr-only">{t('common.loading')}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-[84px] rounded-m border border-line bg-surface-2" aria-hidden="true" />
      ))}
    </div>
  );
}

export function ErrorState({ title, onRetry }: { title: string; onRetry?: () => void }) {
  const t = useT();
  return (
    <div role="alert" className="rounded-m border border-dashed border-line-strong p-7 text-center text-muted" data-error-state="">
      <h2 className="text-fg">{title}</h2>
      <p className="mx-auto mt-2 max-w-[60ch]">{t('common.errorBody')}</p>
      {onRetry !== undefined ? (
        <Button variant="ghost" size="small" className="mt-4" onClick={onRetry}>
          {t('common.tryAgain')}
        </Button>
      ) : null}
    </div>
  );
}

// 404 for an addressed record that is not there, which includes another
// tenant's record (playbook 4.4): never the Restricted screen.
export function NotFoundScreen({ body, backHref = '/', backLabel }: { body?: string; backHref?: string; backLabel?: string }) {
  const t = useT();
  return (
    <section className="mx-auto max-w-[60ch] py-16 text-center" data-not-found="">
      <h1>{t('notFound.title')}</h1>
      <p className="mt-3 text-muted">{body ?? t('notFound.body')}</p>
      <Link href={backHref} className="mt-4 inline-block font-semibold underline">
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
    text = problem.requiredPermission === undefined ? detail : `${detail} ${t('restricted.needs', { permission: humanisePermission(problem.requiredPermission) })}`;
  } else {
    text = problem.detail.length > 0 ? problem.detail : t('problem.generic');
  }
  return (
    <p role="alert" className={className ?? 'mt-2.5 text-meta text-negative'} data-problem-code={problem?.code}>
      {text}
    </p>
  );
}

export function StatusLine({ children, tone = 'muted' }: { children: React.ReactNode; tone?: 'muted' | 'positive' }) {
  return (
    <p role="status" className={tone === 'positive' ? 'mt-2.5 text-meta text-positive' : 'mt-2.5 text-meta text-muted'}>
      {children}
    </p>
  );
}
