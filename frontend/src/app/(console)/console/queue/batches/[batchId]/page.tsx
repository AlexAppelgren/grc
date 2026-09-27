import { AdminGate } from '@/components/admin/AdminGate';
import { BatchReviewScreen } from '@/components/console/BatchReviewScreen';

// /console/queue/batches/[batchId] (PRO-04, ADM-02). The client gate is the
// registry's entry for Queue (playbook 6.2); the server's structured 403 is the
// enforcer, and the screen renders it as the same Restricted screen.
export default async function ProposalBatchPage({ params }: { params: Promise<{ batchId: string }> }) {
  const { batchId } = await params;
  return (
    <AdminGate id="console-queue">
      <BatchReviewScreen batchId={batchId} />
    </AdminGate>
  );
}
