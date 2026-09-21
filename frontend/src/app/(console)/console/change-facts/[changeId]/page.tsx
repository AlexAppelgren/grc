'use client';

import { use } from 'react';

import { AdminGate } from '@/components/admin/AdminGate';
import { ChangeFactsDetail } from '@/components/console/ChangeFactsDetail';

// One change in the console (ADM-02, WAT-03): what the agents suggested about
// it, and the corrections a library editor may make. The gate is the queue's
// own registry entry; the server's 403, with `proposals.review` named, stays
// the enforcer.
export default function ConsoleChangeFactsDetailPage({ params }: { params: Promise<{ changeId: string }> }) {
  const { changeId } = use(params);
  return (
    <AdminGate id="console-change-facts">
      <ChangeFactsDetail changeId={changeId} />
    </AdminGate>
  );
}
