'use client';

import * as CheckboxPrimitive from '@radix-ui/react-checkbox';
import type { ComponentProps } from 'react';

import { cn } from '@/shared/utils/cn';

// shadcn/ui's Checkbox on the Radix Checkbox, in our colours (read from
// github.com/shadcn-ui/ui, apps/v4/registry/new-york-v4/ui/checkbox.tsx).
// A 20px box, the height of a line of `body`, so it sits on the first line of
// a row without a nudge: the input boundary (line-strong, 3:1) when empty, the
// neutral primary when ticked or mixed, as `accent-button` draws the native
// ones. 4px corners, shadcn's and the switch thumb's, so the box never reads
// as a 6px button. On a touch screen the target grows to 44px around the box
// and nothing moves. Radix gives the checkbox role, aria-checked with `mixed`,
// and Space to toggle; the focus ring is the global :focus-visible one
// (globals.css). The caller names it: aria-label, aria-labelledby, or a
// <label htmlFor> on `id`.

export type CheckedState = CheckboxPrimitive.CheckedState;

export interface CheckboxProps extends Omit<ComponentProps<typeof CheckboxPrimitive.Root>, 'checked' | 'defaultChecked' | 'onCheckedChange' | 'onClick' | 'children' | 'asChild'> {
  checked: CheckedState;
  /** Called with what a press asks for: ticked from empty or mixed, empty from ticked. */
  onCheckedChange?: (checked: boolean) => void;
}

export function Checkbox({ checked, onCheckedChange, className, ...rest }: CheckboxProps) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      {...rest}
      checked={checked}
      // A press on the box is never a press on the row it sits in. Preventing
      // the default keeps a row that is itself a link from being followed, and
      // tells Radix to leave the change to us; stopping the event keeps it
      // from the row's own click handler.
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onCheckedChange?.(checked !== true);
      }}
      className={cn(
        'relative inline-flex size-5 shrink-0 items-center justify-center rounded-[4px] border disabled:cursor-not-allowed disabled:opacity-50',
        // The touch target: 44px, centred on the box, whatever the box measures.
        'pointer-coarse:after:absolute pointer-coarse:after:top-1/2 pointer-coarse:after:left-1/2 pointer-coarse:after:size-11 pointer-coarse:after:-translate-1/2',
        checked === false ? 'border-line-strong bg-surface' : 'border-button bg-button text-on-button',
        className,
      )}
    >
      <CheckboxPrimitive.Indicator data-slot="checkbox-indicator" className="flex">
        <svg viewBox="0 0 16 16" aria-hidden="true" className="size-4 fill-none stroke-current stroke-2 [stroke-linecap:round] [stroke-linejoin:round]">
          <path d={checked === 'indeterminate' ? 'M4.5 8h7' : 'M4.5 8.2l2.4 2.4 4.6-5'} />
        </svg>
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
