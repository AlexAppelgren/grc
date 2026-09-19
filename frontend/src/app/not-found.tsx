import { NotFoundScreen } from '@/components/ui/States';

// An address that is not there, which includes another tenant's record
// (playbook 4.4): never the Restricted screen.
export default function NotFound() {
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-8">
      <NotFoundScreen />
    </div>
  );
}
