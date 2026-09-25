import { NotFoundScreen } from '@/components/ui/States';

// An address that is not there, inside the shell and behind the session gate:
// a signed-in person keeps their navigation, an anonymous visitor goes to
// sign in. Never the Restricted screen (playbook 4.4).
export default function TenantNotFound() {
  return <NotFoundScreen />;
}
