import { AdminGate } from '@/components/admin/AdminGate';
import { WorkflowPolicyScreen } from '@/features/workflow-policy/WorkflowPolicyScreen';

export default function WorkflowPage() {
  return (
    <AdminGate id="admin-workflow">
      <WorkflowPolicyScreen />
    </AdminGate>
  );
}
