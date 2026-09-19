import type { ReactNode } from 'react';

// Prototype `.head`: kicker (a microlabel), h1, one optional lede of at most
// 60 characters in `meta`, actions on the right (playbook 6.5).
export function PageHead({ kicker, title, lede, actions }: { kicker?: string; title: string; lede?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
      <div>
        {kicker !== undefined ? <p className="microlabel mb-1 text-muted">{kicker}</p> : null}
        <h1>{title}</h1>
        {lede !== undefined ? <p className="mt-1 max-w-[72ch] text-meta text-muted">{lede}</p> : null}
      </div>
      {actions}
    </div>
  );
}
