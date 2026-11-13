'use client';

import * as Collapsible from '@radix-ui/react-collapsible';
import { useState, type HTMLAttributes, type ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// A labelled disclosure for secondary material inside a card (earlier
// versions, sources, history), on the Radix Collapsible: shadcn/ui's
// Collapsible with its Accordion's trigger row (github.com/shadcn-ui/ui,
// apps/v4/registry/new-york-v4/ui/collapsible.tsx and accordion.tsx), one step
// tighter. A hairline above, as a card's other sections have, then a
// full-width button with the title, a count and a chevron that turns when
// open; the chevron stays on the first line of a title that wraps. Radix gives
// aria-expanded, and aria-controls pointing at the region. Nothing animates
// but the chevron.
//
// Closed, the content is not rendered. `keepMounted` keeps it in the page,
// hidden with the `hidden` attribute, where an end-to-end journey reads text
// inside a closed section. Other attributes (a data- hook) pass through to the
// root element.

export interface FoldProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title: ReactNode;
  /** Shown muted after the title, in parentheses. */
  count?: number;
  defaultOpen?: boolean;
  /** Set it to control the fold; left out, the fold keeps its own state. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  keepMounted?: boolean;
  /** The element around the trigger, so a card keeps its heading outline. The row looks the same in each. */
  as?: 'h2' | 'h3' | 'div';
  children: ReactNode;
}

export function Fold({ title, count, defaultOpen = false, open: controlled, onOpenChange, keepMounted = false, as: Heading = 'div', className, children, ...rest }: FoldProps) {
  // Held here and handed to Radix: the chevron and the `hidden` of kept content read it.
  const [own, setOwn] = useState(defaultOpen);
  const open = controlled ?? own;
  const tally = count === undefined ? null : `(${count})`;
  return (
    <Collapsible.Root
      data-slot="fold"
      open={open}
      onOpenChange={(next) => {
        setOwn(next);
        onOpenChange?.(next);
      }}
      className={cn('border-t border-line', className)}
      {...rest}
    >
      <Heading>
        <Collapsible.Trigger
          data-slot="fold-trigger"
          className="flex w-full items-start justify-between gap-2 py-3 text-left text-body font-medium tracking-normal underline-offset-[3px] hover:underline"
        >
          <span className="min-w-0">
            {title}
            {tally === null ? null : (
              <>
                {' '}
                <span className="font-normal text-muted">{tally}</span>
              </>
            )}
          </span>
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className={cn('mt-0.5 size-4 shrink-0 fill-none stroke-current stroke-[1.75] text-muted [stroke-linecap:round] [stroke-linejoin:round] motion-safe:transition-transform', open && 'rotate-180')}
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </Collapsible.Trigger>
      </Heading>
      <Collapsible.Content data-slot="fold-content" forceMount={keepMounted || undefined} hidden={!open} className="pb-3">
        {children}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
