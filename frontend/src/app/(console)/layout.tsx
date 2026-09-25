import type { ReactNode } from 'react';

import { AppShell } from '@/components/shell/AppShell';
import { SessionGate } from '@/components/shell/SessionGate';

// The platform console route group (ADM-02, design/screens/console-shell.html):
// the same session gate and shell as the tenant group, with the console's own
// destinations. The shell asks for the session and nothing a tenant holds
// (playbook 6.1); each console screen asks for what it shows, and the
// server's 403 on every console route stays the enforcer.
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    <SessionGate>
      <AppShell surface="console">{children}</AppShell>
    </SessionGate>
  );
}
