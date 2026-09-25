import { AdminGate } from '@/components/admin/AdminGate';
import { ConsoleSupportAccessScreen } from '@/components/console/ConsoleSupportAccessScreen';

// Support access, the platform side (TEN-06): ask a bank to let you read,
// see your own requests, and enter an approved one read-only.
export default function ConsoleSupportAccessPage() {
  return (
    <AdminGate id="console-support-access">
      <ConsoleSupportAccessScreen />
    </AdminGate>
  );
}
