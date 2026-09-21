import { ChangeScreen } from '@/components/watch/ChangeScreen';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /watch/[changeId] (WAT-02, WAT-03, WAT-04). The client gate is the
// registry's entry for Watch (playbook 6.2); the server's structured 403 is
// the enforcer, and the screen renders it as the same Restricted screen.
const WATCH = findDestination('watch');

export default async function ChangePage({ params }: { params: Promise<{ changeId: string }> }) {
  const { changeId } = await params;
  return (
    <RequirePermission anyOf={WATCH?.anyOfPermissions ?? []}>
      <ChangeScreen changeId={changeId} />
    </RequirePermission>
  );
}
