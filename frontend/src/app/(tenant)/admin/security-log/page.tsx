import { AdminGate } from '@/components/admin/AdminGate';
import { SecurityLogScreen } from '@/components/admin/SecurityLogScreen';

export default function SecurityLogPage() {
  return (
    <AdminGate id="admin-security-log">
      <SecurityLogScreen />
    </AdminGate>
  );
}
