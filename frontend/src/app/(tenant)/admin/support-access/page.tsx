import { AdminGate } from '@/components/admin/AdminGate';
import { SupportAccessScreen } from '@/components/admin/SupportAccessScreen';

export default function SupportAccessPage() {
  return (
    <AdminGate id="admin-support-access">
      <SupportAccessScreen />
    </AdminGate>
  );
}
