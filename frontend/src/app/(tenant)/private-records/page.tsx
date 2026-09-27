import { PrivateRecordsScreen } from '@/features/private-records/PrivateRecordsScreen';
import { PRIVATE_RECORDS_APPROVE } from '@/features/private-records/types';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /private-records (OWN-03, PRO-03, INV-07). The client gate is the queue's one grant
// (playbook 6.2); the server's structured 403 is the enforcer, and the screen renders it
// as the same Restricted screen.
export default function PrivateRecordsPage() {
  return (
    <RequirePermission anyOf={[PRIVATE_RECORDS_APPROVE]}>
      <PrivateRecordsScreen />
    </RequirePermission>
  );
}
