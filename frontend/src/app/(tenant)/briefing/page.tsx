'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { BriefingScreen } from '@/components/home/BriefingScreen';

// /briefing (design/screens/tenant-briefing.html; HOM-02). The running week,
// computed live. The client gate is the registry's own `briefing` entry
// (`watch.read`, hidden from the rail: reached from Today's lead card and
// the mailed link, never a nav destination).

export default function BriefingPage() {
  return (
    <AdminGate id="briefing">
      <BriefingScreen />
    </AdminGate>
  );
}
