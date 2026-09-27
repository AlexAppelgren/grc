import { AdminGate } from '@/components/admin/AdminGate';
import { SecurityPolicyScreen } from '@/components/admin/SecurityPolicyScreen';

export default function SecurityPage() {
  return (
    <AdminGate id="admin-security">
      <SecurityPolicyScreen />
    </AdminGate>
  );
}
