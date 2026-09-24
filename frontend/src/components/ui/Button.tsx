import { cva, type VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// foundations.md "Button" (shadcn's Button on Green's colours): 36px, 16px
// sides, 6px radius, `body` at 500 in sentence case, 8px icon gap. Primary is
// neutral, never brand green. Hover on outline and ghost is Green's
// state-neutral-05 overlay (`hover-fill`, theme.css); danger hovers on
// `negative-hover`, a fill that goes one step deeper in dark so the label
// keeps AA on it (theme.css).
// Exported for links that look like buttons (the public page's calls to action).
export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-control border text-body font-medium whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:size-4',
  {
    variants: {
      variant: {
        primary: 'border-button bg-button text-on-button enabled:hover:bg-[color-mix(in_srgb,var(--color-button)_88%,var(--color-page))]',
        outline: 'border-line-control bg-surface text-fg enabled:hover:hover-fill',
        ghost: 'border-transparent bg-transparent text-fg enabled:hover:hover-fill',
        danger: 'border-line-control bg-surface text-negative enabled:hover:bg-negative-hover',
      },
      size: {
        default: 'h-9 px-4',
        small: 'h-8 px-3',
      },
    },
    defaultVariants: { variant: 'primary', size: 'default' },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  children: ReactNode;
}

export function Button({ variant, size, className, type = 'button', children, ...rest }: ButtonProps) {
  return (
    <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...rest}>
      {children}
    </button>
  );
}

// Prototype `.bar`: actions on the right; on phones two buttons share one
// row, never stacked, the primary last in DOM order and so on the right
// (playbook 6.8).
export function ButtonBar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mt-4 flex flex-nowrap items-center justify-end gap-2', className)}>{children}</div>;
}
