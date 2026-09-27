import { PrivateProposalScreen } from '@/features/private-records/PrivateProposalScreen';
import { PRIVATE_RECORDS_APPROVE } from '@/features/private-records/types';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /private-records/[proposalId] (OWN-03, PRO-03, INV-07). The client gate is the queue's
// one grant (playbook 6.2); the server's 403 renders the same Restricted screen, and
// another bank's proposal answers 404, which the screen renders as Not found.
export default async function PrivateProposalPage({ params }: { params: Promise<{ proposalId: string }> }) {
  const { proposalId } = await params;
  return (
    <RequirePermission anyOf={[PRIVATE_RECORDS_APPROVE]}>
      <PrivateProposalScreen proposalId={proposalId} />
    </RequirePermission>
  );
}
