'use client';

import { Suspense } from 'react';

import { GapsScreen } from '@/components/register/GapsScreen';
import { LoadingState } from '@/components/ui/States';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /gaps (design/screens/tenant-gaps.html; REG-03). The client gate is the
// registry's entry for the destination (playbook 6.2); the server's structured
// 403 is the enforcer. The screen reads its filters from the URL, which Next
// serves through a suspense boundary.
const GAPS = findDestination('gaps');

export default function GapsPage() {
  return (
    <RequirePermission anyOf={GAPS?.anyOfPermissions ?? []}>
      <Suspense fallback={<LoadingState rows={3} />}>
        <GapsScreen />
      </Suspense>
    </RequirePermission>
  );
}
