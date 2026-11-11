'use client';

import { useState, type ReactNode } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { StatusLine } from '@/components/ui/States';
import { useT } from '@/shared/i18n/LocaleProvider';

// A secret the server shows once (an API key, a personal token, an agent's
// key, a calendar address): it lives in the caller's state for the one
// render and reaches no storage, URL, log line or query cache. Copy puts it
// on the clipboard; Done is the only way on, and nothing can show it again.

export function SecretOnce({
  secret,
  copyLabel,
  address = false,
  onDone,
  children,
}: {
  secret: string;
  copyLabel: string;
  /** A calendar feed's address rather than a key: the journeys read it under its own marker. */
  address?: boolean;
  onDone: () => void;
  children?: ReactNode;
}) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <>
      <pre className="m-0 mb-3 rounded-control border border-line bg-subtle p-3 font-mono break-all whitespace-pre-wrap" {...(address ? { 'data-feed-address': '' } : { 'data-plain-key': '' })}>
        {secret}
      </pre>
      {children}
      {copied ? <StatusLine tone="positive">{t('common.copied')}</StatusLine> : null}
      <ButtonBar>
        <Button variant="outline" size="small" onClick={onDone}>
          {t('common.done')}
        </Button>
        <Button size="small" onClick={() => void copy()}>
          {copyLabel}
        </Button>
      </ButtonBar>
    </>
  );
}
