'use client';

import { AdminGate } from '@/components/admin/AdminGate';
import { EvaluationScreen } from '@/components/console/EvaluationScreen';

// Evaluation (ADM-02, SRC-05): the questions search is scored with, the runs
// and the baseline. The gate is the registry's own entry; the server's 403 on
// every /eval route, with `eval.manage` named, stays the enforcer.
export default function ConsoleEvaluationPage() {
  return (
    <AdminGate id="console-evaluation">
      <EvaluationScreen />
    </AdminGate>
  );
}
