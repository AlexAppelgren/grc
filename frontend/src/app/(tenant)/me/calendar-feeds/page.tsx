'use client';

import { CalendarFeedsScreen } from '@/components/account/CalendarFeedsScreen';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /me/calendar-feeds (design/screens/tenant-calendar-feeds.html; HOM-04). The
// client gate is the registry's entry for the destination (playbook 6.2);
// the server's structured 403 is the enforcer.
const CALENDAR_FEEDS = findDestination('me-calendar-feeds');

export default function CalendarFeedsPage() {
  return (
    <RequirePermission anyOf={CALENDAR_FEEDS?.anyOfPermissions ?? []}>
      <CalendarFeedsScreen />
    </RequirePermission>
  );
}
