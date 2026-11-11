import { AdminGate } from '@/components/admin/AdminGate';
import { ChangeScreen } from '@/components/watch/ChangeScreen';

// /watch/[changeId] (WAT-02, WAT-03, WAT-04). The client gate is the
// registry's entry for Watch (playbook 6.2); the server's structured 403 is
// the enforcer, and the screen renders it as the same Restricted screen.

export default async function ChangePage({ params }: { params: Promise<{ changeId: string }> }) {
  const { changeId } = await params;
  return (
    <AdminGate id="watch">
      <ChangeScreen changeId={changeId} />
    </AdminGate>
  );
}
