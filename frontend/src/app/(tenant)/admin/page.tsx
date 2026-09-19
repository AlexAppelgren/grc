import { AdminGate } from '@/components/admin/AdminGate';
import { AdminIndexScreen } from '@/components/admin/AdminIndexScreen';

export default function AdminPage() {
  return (
    <AdminGate id="admin">
      <AdminIndexScreen />
    </AdminGate>
  );
}
