'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { SourcesScreen } from '@/components/console/SourcesScreen';

// Sources (ADM-02, WAT-01): the read-only registry of what the agents watch.
// The gate is the registry's own entry; the server's 403 on GET /sources and
// GET /sources/coverage, with `sources.manage` named, stays the enforcer.
export default function ConsoleSourcesPage() {
  return (
    <AdminGate id="console-sources">
      <SourcesScreen />
    </AdminGate>
  );
}
