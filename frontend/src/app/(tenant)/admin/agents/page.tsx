import { AdminGate } from '@/components/admin/AdminGate';
import { AgentsScreen } from '@/components/admin/AgentsScreen';

export default function AgentsPage() {
  return (
    <AdminGate id="admin-agents">
      <AgentsScreen />
    </AdminGate>
  );
}
