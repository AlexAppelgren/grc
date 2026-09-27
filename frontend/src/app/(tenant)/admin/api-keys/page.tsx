import { AdminGate } from '@/components/admin/AdminGate';
import { ApiKeysScreen } from '@/features/tenant-admin/api-keys/ApiKeysScreen';

export default function ApiKeysPage() {
  return (
    <AdminGate id="admin-api-keys">
      <ApiKeysScreen />
    </AdminGate>
  );
}
