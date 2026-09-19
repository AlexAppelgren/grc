import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// tailwind-merge must know the named type scale (playbook 6.4), or it would
// treat `text-meta` as a colour and drop it when merged with `text-muted`.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': ['text-hero', 'text-display', 'text-title', 'text-body', 'text-meta'],
    },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
