// The security-policy feature's names, aliases over the generated schemas in
// src/types/api.generated.ts (`bash generate-types.sh` regenerates them).

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type SecurityPolicy = Schemas['SecurityPolicyOut'];
export type SecurityPolicyBody = Schemas['SecurityPolicyBody'];
