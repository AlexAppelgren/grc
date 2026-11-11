'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { CalendarFeedsScreen } from '@/components/account/CalendarFeedsScreen';

// /me/calendar-feeds (design/screens/tenant-calendar-feeds.html; HOM-04). The
// client gate is the registry's entry for the destination (playbook 6.2);
// the server's structured 403 is the enforcer.

export default function CalendarFeedsPage() {
  return (
    <AdminGate id="me-calendar-feeds">
      <CalendarFeedsScreen />
    </AdminGate>
  );
}
