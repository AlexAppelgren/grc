'use client';

import { Suspense } from 'react';

import { AdminGate } from '@/components/admin/AdminGate';
import { LoadingState } from '@/components/ui/States';
import { WatchFeedScreen } from '@/components/watch/WatchFeedScreen';

// /watch (WAT-02, WAT-03, FP-03). The client gate is the registry's entry for
// the destination (playbook 6.2); the server's structured 403 is the
// enforcer, and the screen renders it as the same Restricted screen. The
// screen reads its tab and filters from the URL, which Next serves through a
// suspense boundary.

export default function WatchPage() {
  return (
    <AdminGate id="watch">
      <Suspense fallback={<LoadingState rows={3} />}>
        <WatchFeedScreen />
      </Suspense>
    </AdminGate>
  );
}
