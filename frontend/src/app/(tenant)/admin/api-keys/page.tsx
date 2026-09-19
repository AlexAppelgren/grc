import { AdminGate } from '@/components/admin/AdminGate';
import { ApiKeysScreen } from '@/components/admin/ApiKeysScreen';

export default function ApiKeysPage() {
  return (
    <AdminGate id="admin-api-keys">
      <ApiKeysScreen />
    </AdminGate>
  );
}
