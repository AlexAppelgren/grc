'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { AgentKeysScreen } from '@/components/console/AgentKeysScreen';

// Agent keys (ADM-02, ID-10, AGT-01): the keys bleqq's own agents run on. The
// gate is the registry's own entry; the server's 403, with
// `agent_definitions.manage` named, and its step-up on creation stay the
// enforcers.
export default function ConsoleAgentKeysPage() {
  return (
    <AdminGate id="console-agent-keys">
      <AgentKeysScreen />
    </AdminGate>
  );
}
