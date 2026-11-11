import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import type { ReactNode } from 'react';

import type { Locale } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';

import { queryWrapper } from './api-adapter';

// Test support: a node rendered as the app renders it, inside a fresh query
// client and the locale, and inside the given permissions when the test
// names them (without them, a screen reads the session's own from GET /me).

export function renderWith(node: ReactNode, { permissions, locale = 'en', queryClient }: { permissions?: readonly string[]; locale?: Locale; queryClient?: QueryClient } = {}): RenderResult & { queryClient: QueryClient } {
  const client = queryClient ?? queryWrapper().queryClient;
  const inner = permissions === undefined ? node : <PermissionsProvider permissions={permissions}>{node}</PermissionsProvider>;
  const result = render(
    <QueryClientProvider client={client}>
      <LocaleProvider locale={locale}>{inner}</LocaleProvider>
    </QueryClientProvider>,
  );
  return { ...result, queryClient: client };
}
