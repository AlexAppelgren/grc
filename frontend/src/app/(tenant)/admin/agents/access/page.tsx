import { AdminGate } from '@/components/admin/AdminGate';
import { AccessScreen } from '@/features/agent-access/AccessScreen';

export default function AgentAccessPage() {
  return (
    <AdminGate id="admin-agents-access">
      <AccessScreen />
    </AdminGate>
  );
}
