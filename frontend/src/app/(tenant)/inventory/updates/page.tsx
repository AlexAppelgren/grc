'use client';

import { LibraryUpdatesScreen } from '@/components/inventory/LibraryUpdatesScreen';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /inventory/updates (PRO-03, INV-04). Reached from the Inventory screen's
// own "Library updates" link, so it is gated with Inventory's own
// destination (library.read) rather than a registry entry of its own.
const INVENTORY = findDestination('inventory');

export default function LibraryUpdatesPage() {
  return (
    <RequirePermission anyOf={INVENTORY?.anyOfPermissions ?? []}>
      <LibraryUpdatesScreen />
    </RequirePermission>
  );
}
