'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { AgentDefinitionsScreen } from '@/components/console/AgentDefinitionsScreen';

// Agent definitions (ADM-02, AGT-03): the agents bleqq ships and their
// versions. The gate is the registry's own entry; the server's 403, with
// `agent_definitions.manage` named, and its step-up on every write stay the
// enforcers.
export default function ConsoleAgentsPage() {
  return (
    <AdminGate id="console-agents">
      <AgentDefinitionsScreen />
    </AdminGate>
  );
}
