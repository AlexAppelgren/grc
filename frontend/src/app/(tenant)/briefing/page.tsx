'use client';

import { BriefingScreen } from '@/components/home/BriefingScreen';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /briefing (design/screens/tenant-briefing.html; HOM-02). The running week,
// computed live. The client gate is the registry's own `briefing` entry
// (`watch.read`, hidden from the rail: reached from Today's lead card and
// the mailed link, never a nav destination).
const BRIEFING = findDestination('briefing');

export default function BriefingPage() {
  return (
    <RequirePermission anyOf={BRIEFING?.anyOfPermissions ?? []}>
      <BriefingScreen />
    </RequirePermission>
  );
}
