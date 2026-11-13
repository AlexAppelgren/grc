import { AdminGate } from '@/components/admin/AdminGate';
import { LicencesScreen } from '@/components/admin/LicencesScreen';

export default function LicencesPage() {
  return (
    <AdminGate id="admin-licences">
      <LicencesScreen />
    </AdminGate>
  );
}
