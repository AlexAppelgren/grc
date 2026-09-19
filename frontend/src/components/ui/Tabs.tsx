'use client';

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

export function Tabs({ tabs, current, onSelect }: { tabs: readonly TabDef[]; current: string; onSelect: (id: string) => void }) {
  return (
    <div role="tablist" className="mb-5 flex flex-wrap gap-1 border-b border-line">
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
            className={cn('-mb-px border-b-2 px-3.5 py-2.5 font-semibold whitespace-nowrap', selected ? 'border-fg text-fg' : 'border-transparent text-muted hover:text-fg')}
          >
            {tab.label}
            {tab.badge === undefined ? null : <span className="ml-1.5 text-meta text-muted">{tab.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`}>
      {children}
    </div>
  );
}
