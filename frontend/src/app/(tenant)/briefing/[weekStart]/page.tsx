import { BriefingScreen } from '@/components/home/BriefingScreen';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /briefing/[weekStart] (design/screens/tenant-briefing.html; HOM-02): one
// past week, read back from its snapshot. Reached from the mailed link and
// the briefing page's own "Previous week" control, never navigated to from
// the rail.
const BRIEFING = findDestination('briefing');

export default async function PastBriefingPage({ params }: { params: Promise<{ weekStart: string }> }) {
  const { weekStart } = await params;
  return (
    <RequirePermission anyOf={BRIEFING?.anyOfPermissions ?? []}>
      <BriefingScreen weekStart={weekStart} />
    </RequirePermission>
  );
}
