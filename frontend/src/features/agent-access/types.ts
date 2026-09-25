// The agent-access feature's names, aliases over the generated schemas in
// src/types/api.generated.ts (`bash generate-types.sh` regenerates them).

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type AccessEntry = Schemas['AgentAccessOut'];
export type AccessEntryPage = Schemas['AgentAccessPage'];
export type AccessEntryInput = Schemas['AgentAccessInput'];
export type AccessEntryUpdate = Schemas['AgentAccessUpdate'];
export type AccessKey = Schemas['AgentAccessKeyOut'];
export type AccessKeyCreated = Schemas['AgentAccessKeyCreated'];
export type AccessKeyInput = Schemas['AgentAccessKeyInput'];
export type AccessCall = Schemas['AgentAccessCallRow'];
export type AccessCallPage = Schemas['AgentAccessCallPage'];
export type TenantReach = Schemas['TenantReachView'];
export type TenantReachRequest = Schemas['TenantReachRequestRow'];
export type OrgUnit = Schemas['TenantOrgUnit'];
export type Product = Schemas['TenantProductOut'];
