import type { ReactNode } from 'react';

import { AppShell } from '@/components/shell/AppShell';

// The tenant route group (playbook 2.1): every tenant screen sits inside the
// shell. The console group gets its own layout when it lands.
export default function TenantLayout({ children }: { children: ReactNode }) {
  return <AppShell surface="tenant">{children}</AppShell>;
}
