'use client';

import { Suspense } from 'react';

import { AdminGate } from '@/components/admin/AdminGate';
import { AppliesScreen } from '@/components/applies/AppliesScreen';
import { LoadingState } from '@/components/ui/States';

// /applies (design/screens/tenant-applies.html; REG-01, FP-05). The client gate is the
// registry's entry for the destination, register.read (playbook 6.2); the server's
// structured 403 is the enforcer. The screen reads its company, open regulation and
// filter from the URL, which Next serves through a suspense boundary.

export default function AppliesPage() {
  return (
    <AdminGate id="applies">
      <Suspense fallback={<LoadingState rows={3} />}>
        <AppliesScreen />
      </Suspense>
    </AdminGate>
  );
}
