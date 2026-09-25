'use client';

import type { ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// Prototype `.tabs`: a row of tabs that switch what the panel below shows
// (design/screens/admin-vocabularies.html). Copy comes in from the catalog;
// the panel is the caller's, labelled by the selected tab.

export interface TabDef {
  id: string;
  label: string;
  /** Rendered after the label, e.g. a count. */
  badge?: string;
}

export function Tabs({ tabs, current, onSelect, end }: { tabs: readonly TabDef[]; current: string; onSelect: (id: string) => void; end?: ReactNode }) {
  const list = (
    <div role="tablist" className={cn('flex flex-wrap gap-1', end === undefined ? 'mb-4 border-b border-line' : 'max-lg:w-full max-lg:border-b max-lg:border-line')}>
      {tabs.map((tab) => {
        const selected = tab.id === current;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`panel-${tab.id}`}
            onClick={() => onSelect(tab.id)}
            className={cn('-mb-px border-b-2 px-2.5 py-2 font-medium whitespace-nowrap', selected ? 'border-fg text-fg' : 'border-transparent text-muted hover:text-fg')}
          >
            {tab.label}
            {tab.badge === undefined ? null : <span className="ml-1.5 text-meta text-muted">{tab.badge}</span>}
          </button>
        );
      })}
    </div>
  );
  if (end === undefined) return list;
  // What applies to every tab (the inventory's scope) sits at the end of the tab row,
  // and under the tabs at full width below the rail's breakpoint (foundations.md).
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-x-3 gap-y-3 lg:border-b lg:border-line">
      {list}
      <div className="max-lg:w-full lg:mb-1.5">{end}</div>
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`}>
      {children}
    </div>
  );
}
