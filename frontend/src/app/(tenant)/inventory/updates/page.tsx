'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { LibraryUpdatesScreen } from '@/components/inventory/LibraryUpdatesScreen';

// /inventory/updates (PRO-03, INV-04). Reached from the Inventory screen's
// own "Library updates" link, so it is gated with Inventory's own
// destination (library.read) rather than a registry entry of its own.

export default function LibraryUpdatesPage() {
  return (
    <AdminGate id="inventory">
      <LibraryUpdatesScreen />
    </AdminGate>
  );
}
