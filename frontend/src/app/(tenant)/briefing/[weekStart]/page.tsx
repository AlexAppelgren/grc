import { AdminGate } from '@/components/admin/AdminGate';
import { BriefingScreen } from '@/components/home/BriefingScreen';

// /briefing/[weekStart] (design/screens/tenant-briefing.html; HOM-02): one
// past week, read back from its snapshot. Reached from the mailed link and
// the briefing page's own "Previous week" control, never navigated to from
// the rail.

export default async function PastBriefingPage({ params }: { params: Promise<{ weekStart: string }> }) {
  const { weekStart } = await params;
  return (
    <AdminGate id="briefing">
      <BriefingScreen weekStart={weekStart} />
    </AdminGate>
  );
}
