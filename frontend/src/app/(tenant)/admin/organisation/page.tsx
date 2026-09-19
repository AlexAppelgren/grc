import { AdminGate } from '@/components/admin/AdminGate';
import { OrganisationScreen } from '@/components/admin/OrganisationScreen';

export default function OrganisationPage() {
  return (
    <AdminGate id="admin-organisation">
      <OrganisationScreen />
    </AdminGate>
  );
}
