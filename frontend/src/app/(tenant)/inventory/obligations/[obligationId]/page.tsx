import { ObligationScreen } from '@/components/inventory/ObligationScreen';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /inventory/obligations/[obligationId] (INV-03..INV-06). The client gate is
// the inventory's registry entry (playbook 6.2); the server's structured 403
// is the enforcer, and an id this bank may not read answers 404, which the
// screen renders as Not found rather than Restricted.
const INVENTORY = findDestination('inventory');

export default async function ObligationPage({ params }: { params: Promise<{ obligationId: string }> }) {
  const { obligationId } = await params;
  return (
    <RequirePermission anyOf={INVENTORY?.anyOfPermissions ?? []}>
      <ObligationScreen obligationId={obligationId} />
    </RequirePermission>
  );
}
