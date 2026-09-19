import { AdminGate } from '@/components/admin/AdminGate';
import { RolesScreen } from '@/components/admin/RolesScreen';

export default function RolesPage() {
  return (
    <AdminGate id="admin-roles">
      <RolesScreen />
    </AdminGate>
  );
}
