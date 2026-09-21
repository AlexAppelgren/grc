'use client';

import { Suspense } from 'react';

import { AdminGate } from '@/components/admin/AdminGate';
import { QueueScreen } from '@/components/console/QueueScreen';
import { LoadingState } from '@/components/ui/States';

// /console/queue (PRO-01, PRO-02, PRO-03). The client gate is the registry's
// entry for the destination (playbook 6.2); the server's structured 403 is
// the enforcer. The screen reads its tab and filters from the URL, which
// Next serves through a suspense boundary.
export default function ConsoleQueuePage() {
  return (
    <AdminGate id="console-queue">
      <Suspense fallback={<LoadingState rows={3} />}>
        <QueueScreen />
      </Suspense>
    </AdminGate>
  );
}
