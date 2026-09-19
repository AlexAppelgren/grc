import type { ReactNode } from 'react';

import { AppShell } from '@/components/shell/AppShell';
import { SessionGate } from '@/components/shell/SessionGate';

// The tenant route group (playbook 2.1): every tenant screen sits behind the
// session gate and inside the shell. The console group gets its own layout
// when it lands.
export default function TenantLayout({ children }: { children: ReactNode }) {
  return (
    <SessionGate>
      <AppShell surface="tenant">{children}</AppShell>
    </SessionGate>
  );
}
