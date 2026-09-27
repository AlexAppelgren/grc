'use client';

import { use } from 'react';

import { AdminGate } from '@/components/admin/AdminGate';
import { AgentDefinitionScreen } from '@/components/console/AgentDefinitionScreen';

// One agent definition (ADM-02, AGT-03): its versions, and for one of bleqq's
// own agents how it runs for every bank and what it ran. The gate is the list's
// registry entry; the server's 403 and its step-up stay the enforcers.
export default function ConsoleAgentDefinitionPage({ params }: { params: Promise<{ agentKey: string }> }) {
  const { agentKey } = use(params);
  return (
    <AdminGate id="console-agents">
      <AgentDefinitionScreen agentKey={agentKey} />
    </AdminGate>
  );
}
