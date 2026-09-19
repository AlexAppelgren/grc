import { AdminGate } from '@/components/admin/AdminGate';
import { AuditLogScreen } from '@/components/admin/AuditLogScreen';

export default function AuditLogPage() {
  return (
    <AdminGate id="admin-audit-log">
      <AuditLogScreen />
    </AdminGate>
  );
}
