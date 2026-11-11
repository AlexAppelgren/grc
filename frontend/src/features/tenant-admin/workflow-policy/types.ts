// The workflow policy's names (COL-02, TEN-01): aliases over the generated
// schemas in src/types/api.generated.ts. The policy is read from GET /tenant
// (`workflow`, beside the platform defaults in `workflowDefaults`) and changed
// with PATCH /tenant/workflow.

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type WorkflowPolicy = Schemas['TenantWorkflow'];
export type WorkflowPolicyPatch = Schemas['TenantWorkflowPatch'];
