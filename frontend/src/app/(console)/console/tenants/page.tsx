import { AdminGate } from '@/components/admin/AdminGate';
import { TenantsScreen } from '@/components/console/TenantsScreen';

// The banks on the platform (ADM-02): the list, and creating one with its
// first administrator invited.
export default function ConsoleTenantsPage() {
  return (
    <AdminGate id="console-tenants">
      <TenantsScreen />
    </AdminGate>
  );
}
