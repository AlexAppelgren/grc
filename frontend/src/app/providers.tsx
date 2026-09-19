'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from 'next-themes';
import { useState, type ReactNode } from 'react';

import { StepUpProvider } from '@/components/auth/StepUpProvider';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import type { Locale } from '@/shared/i18n';
import { PermissionsProvider } from '@/shared/navigation/require-permission';

// Theme via next-themes on the class attribute, system default (playbook
// 6.3). TanStack Query for server state; no global store (playbook 6.1).
// Permissions are `null` here; the tenant layout's SessionGate provides the
// signed-in person's list. The step-up prompt sits above everything so any
// screen's 403 step_up_required can open it.
export function Providers({ locale, children }: { locale: Locale; children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
      }),
  );
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <LocaleProvider locale={locale}>
          <StepUpProvider>
            <PermissionsProvider permissions={null}>{children}</PermissionsProvider>
          </StepUpProvider>
        </LocaleProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
