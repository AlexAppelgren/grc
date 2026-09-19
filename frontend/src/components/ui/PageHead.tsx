import type { ReactNode } from 'react';

// Prototype `.head`: kicker, h1, one optional lede of at most 60 characters,
// actions on the right (playbook 6.5).
export function PageHead({ kicker, title, lede, actions }: { kicker?: string; title: string; lede?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {kicker !== undefined ? <p className="mb-1.5 text-muted">{kicker}</p> : null}
        <h1>{title}</h1>
        {lede !== undefined ? <p className="mt-1.5 max-w-[70ch] text-muted">{lede}</p> : null}
      </div>
      {actions}
    </div>
  );
}
