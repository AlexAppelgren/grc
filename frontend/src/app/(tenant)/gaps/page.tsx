'use client';

import { Suspense } from 'react';

import { AdminGate } from '@/components/admin/AdminGate';
import { GapsScreen } from '@/components/register/GapsScreen';
import { LoadingState } from '@/components/ui/States';

// /gaps (design/screens/tenant-gaps.html; REG-03). The client gate is the
// registry's entry for the destination (playbook 6.2); the server's structured
// 403 is the enforcer. The screen reads its filters from the URL, which Next
// serves through a suspense boundary.

export default function GapsPage() {
  return (
    <AdminGate id="gaps">
      <Suspense fallback={<LoadingState rows={3} />}>
        <GapsScreen />
      </Suspense>
    </AdminGate>
  );
}
