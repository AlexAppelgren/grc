import { AdminGate } from '@/components/admin/AdminGate';
import { ProposalDetailScreen } from '@/components/console/ProposalDetailScreen';

// /console/queue/[proposalId] (PRO-01, PRO-02, AC-PRO2). The client gate is
// the registry's entry for Queue (playbook 6.2); the server's structured 403
// is the enforcer, and the screen renders it as the same Restricted screen.
export default async function ProposalPage({ params }: { params: Promise<{ proposalId: string }> }) {
  const { proposalId } = await params;
  return (
    <AdminGate id="console-queue">
      <ProposalDetailScreen proposalId={proposalId} />
    </AdminGate>
  );
}
