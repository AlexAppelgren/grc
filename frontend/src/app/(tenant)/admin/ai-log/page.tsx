import { AdminGate } from '@/components/admin/AdminGate';
import { AiLogScreen } from '@/components/admin/AiLogScreen';

export default function AiLogPage() {
  return (
    <AdminGate id="admin-ai-log">
      <AiLogScreen />
    </AdminGate>
  );
}
