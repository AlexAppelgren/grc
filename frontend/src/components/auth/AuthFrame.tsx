import type { ReactNode } from 'react';

import { Logo } from '@/components/shell/Logo';

// The auth surface (design/screens/auth-*.html): no side rail, the wordmark
// above one centred panel of at most 440px.
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen justify-items-center px-4 pt-7 pb-20 md:pt-12">
      <div className="w-full max-w-[440px]">
        <Logo className="mx-auto mb-7 block h-auto w-[150px] text-fg" />
        {children}
      </div>
    </div>
  );
}

export function AuthPanel({ children, ...rest }: { children: ReactNode } & React.HTMLAttributes<HTMLElement>) {
  return (
    <section className="rounded-card border border-line bg-surface p-6" {...rest}>
      {children}
    </section>
  );
}

export function StepKicker({ children }: { children: ReactNode }) {
  return <p className="microlabel mb-1.5 text-muted">{children}</p>;
}
