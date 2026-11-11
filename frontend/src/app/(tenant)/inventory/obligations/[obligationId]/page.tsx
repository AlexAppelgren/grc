import { AdminGate } from '@/components/admin/AdminGate';
import { ObligationScreen } from '@/components/inventory/ObligationScreen';

// /inventory/obligations/[obligationId] (INV-03..INV-06). The client gate is
// the inventory's registry entry (playbook 6.2); the server's structured 403
// is the enforcer, and an id this bank may not read answers 404, which the
// screen renders as Not found rather than Restricted.

export default async function ObligationPage({ params }: { params: Promise<{ obligationId: string }> }) {
  const { obligationId } = await params;
  return (
    <AdminGate id="inventory">
      <ObligationScreen obligationId={obligationId} />
    </AdminGate>
  );
}
