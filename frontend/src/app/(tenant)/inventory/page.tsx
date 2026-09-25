'use client';

import { Suspense } from 'react';

import { InventoryScreen } from '@/components/inventory/InventoryScreen';
import { LoadingState } from '@/components/ui/States';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /inventory (INV-03, FP-03). The client gate is the registry's entry for the
// destination (playbook 6.2); the server's structured 403 is the enforcer.
// The screen reads its filters from the URL, which Next serves through a
// suspense boundary.
const INVENTORY = findDestination('inventory');

export default function InventoryPage() {
  return (
    <RequirePermission anyOf={INVENTORY?.anyOfPermissions ?? []}>
      <Suspense fallback={<LoadingState rows={3} />}>
        <InventoryScreen />
      </Suspense>
    </RequirePermission>
  );
}
