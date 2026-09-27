import { AdminGate } from '@/components/admin/AdminGate';
import { EntryScreen } from '@/features/agent-access/EntryScreen';

export default async function AgentAccessEntryPage({ params }: { params: Promise<{ entryId: string }> }) {
  const { entryId } = await params;
  return (
    <AdminGate id="admin-agents-access">
      <EntryScreen entryId={decodeURIComponent(entryId)} />
    </AdminGate>
  );
}
