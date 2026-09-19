import { cva, type VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// Prototype `.btn`, `.btn.ghost`, `.btn.danger`, `.btn.small`: fully rounded,
// 44px tall, 600 weight. Colours are the token pairs from theme.css.
const button = cva('inline-flex items-center justify-center rounded-full border font-semibold whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-45', {
  variants: {
    variant: {
      primary: 'border-button bg-button text-on-button',
      ghost: 'border-line-strong bg-transparent text-fg hover:border-fg',
      danger: 'border-negative bg-transparent text-negative',
    },
    size: {
      default: 'min-h-11 px-5 py-2.5',
      small: 'min-h-9 px-3.5 py-1.5 text-meta',
    },
  },
  defaultVariants: { variant: 'primary', size: 'default' },
});

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {
  children: ReactNode;
}

export function Button({ variant, size, className, type = 'button', children, ...rest }: ButtonProps) {
  return (
    <button type={type} className={cn(button({ variant, size }), className)} {...rest}>
      {children}
    </button>
  );
}

// Prototype `.bar`: actions on the right; on phones two buttons share one
// row, never stacked, the primary last in DOM order and so on the right
// (playbook 6.8).
export function ButtonBar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mt-3.5 flex flex-nowrap items-center justify-end gap-2', className)}>{children}</div>;
}
