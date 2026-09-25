import type { ReactNode } from 'react';

import { PrincipalShell } from '@/components/shell/AppShell';
import { SessionGate } from '@/components/shell/SessionGate';

// The tenant route group (playbook 2.1): every tenant screen sits behind the
// session gate and inside the shell. The shell follows the principal, so the
// pages every signed-in person shares (/me, not-found) keep platform staff in
// the console rail; the console group has its own layout.
export default function TenantLayout({ children }: { children: ReactNode }) {
  return (
    <SessionGate>
      <PrincipalShell>{children}</PrincipalShell>
    </SessionGate>
  );
}
