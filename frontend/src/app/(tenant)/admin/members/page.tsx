import { AdminGate } from '@/components/admin/AdminGate';
import { MembersScreen } from '@/components/admin/MembersScreen';

export default function MembersPage() {
  return (
    <AdminGate id="admin-members">
      <MembersScreen />
    </AdminGate>
  );
}
