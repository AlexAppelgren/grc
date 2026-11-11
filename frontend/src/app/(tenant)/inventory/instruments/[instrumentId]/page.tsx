import { AdminGate } from '@/components/admin/AdminGate';
import { InstrumentScreen } from '@/components/inventory/InstrumentScreen';

// /inventory/instruments/[instrumentId] (INV-01, INV-06). The client gate is
// the inventory's registry entry (playbook 6.2); the server's structured 403
// is the enforcer, and an id this bank may not read answers 404, which the
// screen renders as Not found rather than Restricted.

export default async function InstrumentPage({ params }: { params: Promise<{ instrumentId: string }> }) {
  const { instrumentId } = await params;
  return (
    <AdminGate id="inventory">
      <InstrumentScreen instrumentId={instrumentId} />
    </AdminGate>
  );
}
