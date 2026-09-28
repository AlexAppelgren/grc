import { PrincipalShell } from '@/components/shell/AppShell';
import { SessionGate } from '@/components/shell/SessionGate';
import { NotFoundScreen } from '@/components/ui/States';

// An address that is not there, drawn as the tenant group draws it: inside the
// shell and behind the session gate, so a signed-in person keeps their
// navigation and an anonymous visitor goes to the public page
// (design/system/navigation.md 15). Never the Restricted screen (playbook 4.4).
export default function MissingNotFound() {
  return (
    <SessionGate>
      <PrincipalShell>
        <NotFoundScreen />
      </PrincipalShell>
    </SessionGate>
  );
}
