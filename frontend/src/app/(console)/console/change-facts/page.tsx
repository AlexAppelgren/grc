'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { ChangeFactsScreen } from '@/components/console/ChangeFactsScreen';

// Change facts (ADM-02, WAT-03): the queue a library editor works. The gate is
// the registry's own entry; the server's 403 on `GET /console/changes`, with
// `proposals.review` named, stays the enforcer.
export default function ConsoleChangeFactsPage() {
  return (
    <AdminGate id="console-change-facts">
      <ChangeFactsScreen />
    </AdminGate>
  );
}
